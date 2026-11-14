"""Map a Python repo for packaging: duplicate code worth extracting, and dependencies used wrongly.
Every row is a lead to read, not a verdict; nothing is imported or run. See --help for flags."""
USAGE = """Usage:
  python3 scan_packages.py ROOT [--json] [--min-nodes N]

Reads every .py file under ROOT (skipping venvs, build and VCS dirs) plus the dependency lists in
pyproject.toml and requirements*.txt. Standard library only. --min-nodes (default 25 AST nodes,
about one real expression) sets the smallest function compared; tests are never compared.

Duplicate code (package candidates):
  EXACT        function bodies identical once local variable names are renamed
  NEAR         same shape but different constants, globals, or attributes; the Differs column
               lists them, and they are often the reason the copies must stay apart

Dependencies:
  UNUSED       declared, never imported (UNUSED? = often used without an import: CLI, driver, plugin)
  UNDECLARED   imported, not declared
  MISPLACED    dev tool or test-only library in runtime deps, or prod code importing a dev-only dep
  HEAVY        large library used at 3 or fewer places
  OVERLAP      two libraries that do the same job

Code:
  BLOCKING     blocking call inside async def (stalls every task on the event loop)
  NO-TIMEOUT   requests call without timeout= (can hang forever)
  PRIVATE      imports a library's private _module or _name (breaks on minor upgrades)
  PATCH        assigns onto a library's attribute: the library lacks something
  RETRY-LOOP   hand-written retry loop (sleep inside a loop with try)
  VENDORED     third-party code copied into the repo

Structure:
  HOLLOW       shared module or package used by one file or none, or one that only re-exports
  LEAKY        shared code imports app code, or a module imports another package's _private name
  CYCLE        local packages that import each other
  UNREFERENCED top-level function or class in shared code that nothing names"""
import ast
import copy
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

try:
    import tomllib
except ImportError:
    tomllib = None

SKIP_DIRS = {".git", ".hg", ".venv", "venv", "env", "node_modules", "build", "dist", "__pycache__", ".tox",
             ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages", ".eggs"}
SHARED = {"common", "shared", "utils", "util", "lib", "libs", "core", "helpers", "packages", "pkg"}
VENDOR = {"vendor", "_vendor", "vendored", "third_party", "thirdparty"}
DEV_TOOLS = re.compile(r"^(pytest(-.*)?|black|ruff|mypy|flake8.*|isort|coverage|tox|nox|pre-commit|pylint|"
                       r"ipython|ipdb|hypothesis|bandit|pyright|types-.*|.*-stubs)$")
DEV_GROUP = re.compile(r"(^|[-_.])(dev|tests?|lint|docs?|typing|types|ci|check)([-_.]|$)", re.I)
INDIRECT = re.compile(r"^(uvicorn|gunicorn|hypercorn|daphne|psycopg2(-binary)?|psycopg(-binary)?|pymysql|"
                      r"mysqlclient|setuptools|wheel|pip|gevent|eventlet|whitenoise|certifi|django-.*|"
                      r"pytest-.*|flake8-.*|types-.*|.*-stubs)$")
HEAVY = {"pandas", "numpy", "scipy", "matplotlib", "torch", "tensorflow", "scikit-learn", "polars", "pyspark",
         "boto3", "sqlalchemy", "selenium", "playwright", "transformers", "opencv-python"}
IMPORT_TO_DIST = {
    "yaml": "pyyaml", "PIL": "pillow", "bs4": "beautifulsoup4", "sklearn": "scikit-learn",
    "cv2": "opencv-python", "dateutil": "python-dateutil", "jwt": "pyjwt", "dotenv": "python-dotenv",
    "attr": "attrs", "Crypto": "pycryptodome", "magic": "python-magic", "serial": "pyserial", "zmq": "pyzmq",
    "docx": "python-docx", "pptx": "python-pptx", "fitz": "pymupdf", "git": "gitpython",
    "MySQLdb": "mysqlclient", "psycopg2": ["psycopg2", "psycopg2-binary"], "slack_sdk": "slack-sdk",
    "jose": "python-jose", "multipart": "python-multipart", "OpenSSL": "pyopenssl", "nacl": "pynacl",
    "ruamel": "ruamel-yaml", "kafka": "kafka-python", "websocket": "websocket-client",
    "pkg_resources": "setuptools", "google": ["protobuf"], "telegram": "python-telegram-bot",
}
OVERLAP = [
    ("HTTP clients", {"requests", "httpx", "aiohttp", "urllib3", "pycurl"}),
    ("retry", {"tenacity", "backoff", "retrying", "stamina"}),
    ("JSON", {"orjson", "ujson", "simplejson", "python-rapidjson"}),
    ("dates", {"arrow", "pendulum", "python-dateutil", "maya"}),
    ("CLI", {"click", "typer", "fire", "docopt"}),
    ("validation", {"pydantic", "marshmallow", "cerberus", "voluptuous"}),
    ("logging", {"loguru", "structlog"}),
    ("YAML", {"pyyaml", "ruamel-yaml"}),
    ("dataframes", {"pandas", "polars"}),
    ("env config", {"python-dotenv", "environs", "python-decouple"}),
    ("Postgres drivers", {"psycopg2", "psycopg2-binary", "psycopg"}),
]
HTTP_VERBS = r"(get|post|put|patch|delete|head|options|request)"
BLOCKING = re.compile(rf"^(requests\.{HTTP_VERBS}|httpx\.{HTTP_VERBS}|time\.sleep|urllib\.request\.urlopen|"
                      r"subprocess\.(run|call|check_call|check_output)|socket\.create_connection)$")
REQUESTS_CALL = re.compile(rf"^requests\.{HTTP_VERBS}$")
SLEEPS = {"time.sleep", "asyncio.sleep"}
RETRY_LIBS = {"tenacity", "backoff", "stamina", "retrying"}
STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def is_test(rel):
    parts = rel.split(os.sep)
    base = parts[-1]
    return bool({"tests", "test"} & set(parts[:-1])) or base.startswith("test_") or base.endswith("_test.py") \
        or base == "conftest.py"


def module_name(rel):
    parts = rel[:-3].split(os.sep)
    if parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def walk(root, want):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.endswith(".egg-info"))
        for f in sorted(files):
            if want(f):
                yield os.path.join(d, f)


class Mod:
    def __init__(self, root, path):
        self.rel = os.path.relpath(path, root)
        self.name = module_name(self.rel)
        self.is_pkg = self.rel.endswith("__init__.py")
        self.test = is_test(self.rel)
        self.vendored = bool(VENDOR & set(self.rel.split(os.sep)[:-1]))
        with open(path, encoding="utf-8", errors="replace") as f:
            self.src = f.read()
        self.lines = self.src.count("\n")
        self.tree = ast.parse(self.src)
        self.aliases = {}
        self.imports = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.imports.append((a.name, [], node.lineno))
                    key = a.asname or a.name.split(".")[0]
                    self.aliases[key] = a.name if a.asname else key
            elif isinstance(node, ast.ImportFrom):
                base = self.resolve_from(node)
                self.imports.append((base, [a.name for a in node.names], node.lineno))
                for a in node.names:
                    if a.name != "*":
                        self.aliases[a.asname or a.name] = f"{base}.{a.name}"

    def resolve_from(self, node):
        if not node.level:
            return node.module or ""
        pkg = self.name.split(".") if self.is_pkg else self.name.split(".")[:-1]
        base = pkg[:len(pkg) - (node.level - 1)]
        return ".".join(base + ([node.module] if node.module else []))

    def dotted(self, node):
        """'requests.get' for a call target, resolved through this file's import aliases.
        None when the root name is not an import (a local variable or attribute of one)."""
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name) or node.id not in self.aliases:
            return None
        return ".".join([self.aliases[node.id]] + parts[::-1])


def local_names(fn):
    names = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
    return names


class Shape(ast.NodeTransformer):
    """Renames locals to v0, v1...; in loose mode also blanks globals, attributes, and constants.
    Records every non-local token in visit order so two loose matches can show what differs."""

    def __init__(self, local, loose):
        self.local, self.loose, self.ids, self.tokens = local, loose, {}, []

    def _n(self, name):
        if name in self.local:
            return self.ids.setdefault(name, f"v{len(self.ids)}")
        self.tokens.append(name)
        return "_" if self.loose else name

    def visit_Name(self, node):
        node.id = self._n(node.id)
        return node

    def visit_arg(self, node):
        node.arg = self._n(node.arg)
        node.annotation = None
        return node

    def visit_ExceptHandler(self, node):
        if node.name:
            node.name = self._n(node.name)
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        self.tokens.append(node.attr)
        if self.loose:
            node.attr = "_"
        return node

    def visit_Constant(self, node):
        self.tokens.append(repr(node.value))
        if self.loose:
            node.value = None
        return node


def fingerprint(fn, loose):
    fn = copy.deepcopy(fn)
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    fn.body, fn.name, fn.decorator_list, fn.returns = body or [ast.Pass()], "f", [], None
    shape = Shape(local_names(fn), loose)
    shape.visit(fn)
    return hashlib.sha1(ast.dump(fn).encode()).hexdigest()[:12], shape.tokens


def functions(mod):
    for node in mod.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{node.name}.{sub.name}", sub


def duplicates(mods, min_nodes):
    fns = []
    for m in mods:
        if m.test or m.vendored:
            continue
        for qual, fn in functions(m):
            size = fn.end_lineno - fn.lineno + 1
            if sum(1 for _ in ast.walk(fn)) >= min_nodes:
                exact, _ = fingerprint(fn, False)
                loose, tokens = fingerprint(fn, True)
                fns.append({"where": f"{m.rel}:{fn.lineno}", "name": qual, "lines": size,
                            "exact": exact, "loose": loose, "tokens": tokens})
    groups = []
    by_exact, by_loose = defaultdict(list), defaultdict(list)
    for f in fns:
        by_exact[f["exact"]].append(f)
        by_loose[f["loose"]].append(f)
    for members in by_exact.values():
        if len(members) > 1:
            groups.append(("EXACT", members, []))
    for members in by_loose.values():
        if len(members) > 1 and len({f["exact"] for f in members}) > 1:
            diffs = []
            first = members[0]["tokens"]
            for other in members[1:]:
                for a, b in zip(first, other["tokens"]):
                    if a != b and f"{a} vs {b}" not in diffs:
                        diffs.append(f"{a} vs {b}")
            groups.append(("NEAR", members, diffs[:4]))
    rows = []
    for kind, members, diffs in groups:
        lines = min(f["lines"] for f in members)
        rows.append({"kind": kind, "copies": len(members), "lines": lines, "saves": lines * (len(members) - 1),
                     "where": [f"{f['where']} {f['name']}" for f in members], "differs": diffs})
    return sorted(rows, key=lambda r: (r["kind"] != "EXACT", -r["saves"]))


def declared_deps(root):
    out = {}

    def add(spec, group, where):
        m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
        if m and norm(m.group(1)) != "python":
            out.setdefault(norm(m.group(1)), {"group": group, "where": where})

    def grp(name, prefix):
        return "dev" if DEV_GROUP.search(name) else f"{prefix}:{name}"

    py = os.path.join(root, "pyproject.toml")
    if os.path.exists(py) and tomllib:
        with open(py, "rb") as f:
            data = tomllib.load(f)
        proj = data.get("project", {})
        for s in proj.get("dependencies", []):
            add(s, "runtime", "pyproject.toml")
        for g, specs in proj.get("optional-dependencies", {}).items():
            for s in specs:
                add(s, grp(g, "extra"), "pyproject.toml")
        for g, specs in data.get("dependency-groups", {}).items():
            for s in specs:
                if isinstance(s, str):
                    add(s, grp(g, "group"), "pyproject.toml")
        poetry = data.get("tool", {}).get("poetry", {})
        for n in poetry.get("dependencies", {}):
            add(n, "runtime", "pyproject.toml")
        for n in poetry.get("dev-dependencies", {}):
            add(n, "dev", "pyproject.toml")
        for g, gd in poetry.get("group", {}).items():
            for n in gd.get("dependencies", {}):
                add(n, grp(g, "group"), "pyproject.toml")
    reqs = glob.glob(os.path.join(root, "requirements*.txt")) + glob.glob(os.path.join(root, "requirements", "*.txt"))
    for path in sorted(reqs):
        group = "dev" if DEV_GROUP.search(os.path.basename(path)[:-4]) else "runtime"
        with open(path) as f:
            for line in f:
                if line.strip() and not line.lstrip().startswith(("#", "-")):
                    add(line, group, os.path.relpath(path, root))
    return out


def installed_map():
    try:
        from importlib.metadata import packages_distributions
        return packages_distributions()
    except Exception:
        return {}


def dists_for(top, installed):
    extra = IMPORT_TO_DIST.get(top, [])
    names = {norm(top)} | {norm(x) for x in ([extra] if isinstance(extra, str) else extra)}
    return names | {norm(d) for d in installed.get(top, [])}


def mentioned_outside_code(root, names):
    """True if a deploy or config file (Procfile, Dockerfile, *.ini, *.yml...) names the package.
    Catches servers and drivers that run without an import; dependency lists themselves are skipped."""
    want = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)
    for path in walk(root, lambda f: f in ("Procfile", "Makefile") or f.startswith("Dockerfile")
                     or f.endswith((".cfg", ".ini", ".yml", ".yaml", ".sh", ".toml"))):
        if os.path.basename(path) == "pyproject.toml" or os.path.getsize(path) > 500_000:
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            if want.search(f.read()):
                return os.path.relpath(path, root)
    return None


def dependency_findings(root, mods, local_tops):
    declared = declared_deps(root)
    installed = installed_map()
    usage = defaultdict(lambda: {"prod": set(), "test": set(), "sites": []})
    undeclared = defaultdict(set)
    for m in mods:
        if m.vendored:
            continue
        value_names = {id(n.value) for n in ast.walk(m.tree) if isinstance(n, ast.Attribute)}
        tops = {}
        for target, _, line in m.imports:
            top = target.split(".")[0]
            if top and top not in STDLIB and top not in local_tops:
                tops[top] = line
        for top, line in tops.items():
            hits = dists_for(top, installed) & set(declared)
            if not hits:
                undeclared[top].add(f"{m.rel}:{line}")
            for d in hits or {norm(top)}:
                usage[d]["test" if m.test else "prod"].add(m.rel)
        for n in ast.walk(m.tree):
            label = None
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in m.aliases:
                label = f"{m.aliases[n.value.id]}.{n.attr}"
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and id(n) not in value_names \
                    and n.id in m.aliases and "." in m.aliases[n.id]:
                label = m.aliases[n.id]
            if label and label.split(".")[0] in tops:
                for d in dists_for(label.split(".")[0], installed):
                    usage[d]["sites"].append(f"{label} ({m.rel}:{n.lineno})")
    out = []
    for name, info in sorted(declared.items()):
        u = usage.get(name)
        group = info["group"]
        if group != "dev" and DEV_TOOLS.match(name):
            out.append(("MISPLACED", name, f"dev tool declared as {group} in {info['where']}"))
            continue
        if not u or not (u["prod"] or u["test"]):
            if group == "dev":
                continue
            seen = mentioned_outside_code(root, {name, name.replace("-", "_")})
            if INDIRECT.match(name) or seen:
                out.append(("UNUSED?", name, f"{group} in {info['where']}; no import"
                            + (f", but named in {seen}" if seen else "; often used without one")))
            else:
                out.append(("UNUSED", name, f"{group} in {info['where']}; nothing imports it"))
            continue
        if group != "dev" and not u["prod"]:
            out.append(("MISPLACED", name, f"declared as {group} but only tests import it"))
        elif group == "dev" and u["prod"]:
            out.append(("MISPLACED", name, f"dev-only, but prod code imports it: {sorted(u['prod'])[0]}"))
        if name in HEAVY and len(u["sites"]) <= 3:
            out.append(("HEAVY", name, f"{len(u['sites'])} use(s): " + "; ".join(u["sites"]) or "import only"))
    for top, wheres in sorted(undeclared.items()):
        out.append(("UNDECLARED", top, ", ".join(sorted(wheres))))
    present = set(declared) | {d for d, u in usage.items() if u["prod"] or u["test"]}
    for job, members in OVERLAP:
        both = sorted(members & present)
        if len(both) > 1:
            parts = [f"{d} ({len(usage[d]['prod'] | usage[d]['test'])} files)" for d in both]
            out.append(("OVERLAP", " + ".join(both), f"{job}: " + ", ".join(parts)))
    return [{"flag": f, "package": p, "detail": d} for f, p, d in out], declared


def body_calls(mod, fn):
    """Calls made directly by fn, including inside lambdas, but not inside nested defs or classes.
    Yields (resolved dotted name or bare local name, line)."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(n, ast.Call):
            name = mod.dotted(n.func) or (n.func.id if isinstance(n.func, ast.Name) else None)
            if name:
                yield name, n.lineno, n
        stack.extend(ast.iter_child_nodes(n))


def code_findings(mods, local_tops, declared):
    out = []
    retry_libs = sorted(RETRY_LIBS & set(declared))
    for m in mods:
        if m.vendored:
            continue
        sync_blocking = {}
        for qual, fn in functions(m):
            if isinstance(fn, ast.FunctionDef):
                for name, line, _ in body_calls(m, fn):
                    if BLOCKING.match(name):
                        sync_blocking.setdefault(qual, name)
        for qual, fn in functions(m):
            if isinstance(fn, ast.AsyncFunctionDef):
                for name, line, _ in body_calls(m, fn):
                    if BLOCKING.match(name):
                        out.append(("BLOCKING", f"{m.rel}:{line}", f"{name}() inside async {qual}()"))
                    elif name in sync_blocking:
                        out.append(("BLOCKING", f"{m.rel}:{line}",
                                    f"async {qual}() calls {name}(), which calls {sync_blocking[name]}()"))
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Call):
                name = m.dotted(node.func) or ""
                if REQUESTS_CALL.match(name):
                    kws = {k.arg for k in node.keywords}
                    if "timeout" not in kws and None not in kws:
                        out.append(("NO-TIMEOUT", f"{m.rel}:{node.lineno}", f"{name}() has no timeout="))
                if name == "setattr" and node.args:
                    target = m.dotted(node.args[0])
                    if target and target.split(".")[0] not in local_tops:
                        out.append(("PATCH", f"{m.rel}:{node.lineno}", f"setattr on {target}"))
            elif isinstance(node, (ast.Assign, ast.AugAssign)):
                for t in node.targets if isinstance(node, ast.Assign) else [node.target]:
                    if isinstance(t, ast.Attribute):
                        target = m.dotted(t)
                        if target and target.split(".")[0] not in local_tops:
                            out.append(("PATCH", f"{m.rel}:{node.lineno}", f"assigns {target}"))
            elif isinstance(node, (ast.For, ast.While)):
                inner = list(ast.walk(node))
                has_try = any(isinstance(x, ast.Try) for x in inner)
                sleeps = any(isinstance(x, ast.Call) and (m.dotted(x.func) or "") in SLEEPS for x in inner)
                if has_try and sleeps:
                    note = f"; {', '.join(retry_libs)} already declared" if retry_libs else ""
                    out.append(("RETRY-LOOP", f"{m.rel}:{node.lineno}", "sleep-and-retry loop" + note))
        for target, names, line in m.imports:
            top = target.split(".")[0]
            if top in local_tops or not top:
                continue
            private = [p for p in target.split(".")[1:] + names if p.startswith("_") and not p.startswith("__")]
            if private:
                out.append(("PRIVATE", f"{m.rel}:{line}", f"imports {target} {', '.join(names)}".strip()))
    vendored = sorted({os.path.dirname(m.rel) for m in mods if m.vendored})
    out += [("VENDORED", d, "third-party code copied in; it gets no upgrades or fixes") for d in vendored]
    return [{"flag": f, "where": w, "detail": d} for f, w, d in out]


def shared_unit(name):
    parts = name.split(".")
    for i, p in enumerate(parts):
        if p in SHARED:
            return ".".join(parts[:i + 2])
    return None


def node_of(name):
    return shared_unit(name) or ".".join(name.split(".")[:2])


def structure_findings(mods):
    names = {m.name for m in mods}
    out = []
    edges = defaultdict(dict)
    importers = defaultdict(set)
    for m in mods:
        for target, imported, line in m.imports:
            hits = [f"{target}.{n}" for n in imported if f"{target}.{n}" in names] or \
                   ([target] if target in names else [])
            for hit in hits:
                if m.test:
                    continue
                importers[hit].add(m.rel)
                a, b = node_of(m.name), node_of(hit)
                if a != b:
                    edges[a].setdefault(b, f"{m.rel}:{line} -> {hit}")
                    mine, theirs = shared_unit(m.name), shared_unit(hit)
                    if mine and not theirs:
                        out.append(("LEAKY", f"{m.rel}:{line}", f"shared code imports app code {hit}"))
                for n in imported:
                    if n.startswith("_") and not n.startswith("__") and a != b:
                        out.append(("LEAKY", f"{m.rel}:{line}", f"imports private {target}.{n}"))
    units = defaultdict(list)
    for m in mods:
        u = shared_unit(m.name)
        if u and not m.test and m.tree.body:
            units[u].append(m)
    referenced = defaultdict(int)
    for m in mods:
        for n in ast.walk(m.tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                referenced[n.id] += 1
            elif isinstance(n, ast.Attribute):
                referenced[n.attr] += 1
        for _, imported, _ in m.imports:
            for n in imported:
                referenced[n] += 1
    for unit, members in sorted(units.items()):
        users = set()
        for m in members:
            users |= {r for r in importers.get(m.name, set()) if not any(r == x.rel for x in members)}
        defs = [n for m in members for n in m.tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef,
                                                                          ast.AsyncFunctionDef))]
        reexport = [m.rel for m in members if m.tree.body and all(
            isinstance(s, (ast.Import, ast.ImportFrom)) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
            or (isinstance(s, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in s.targets))
            for s in m.tree.body) and any(isinstance(s, (ast.Import, ast.ImportFrom)) for s in m.tree.body)]
        if len(users) <= 1 or (reexport and len(defs) <= 2):
            detail = f"{len(users)} importing file(s){': ' + ', '.join(sorted(users)) if users else ''}; " \
                     f"{len(defs)} def(s)"
            if reexport:
                detail += f"; only re-exports: {', '.join(reexport)}"
            out.append(("HOLLOW", unit, detail))
        for m in members:
            for d in m.tree.body:
                if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not d.decorator_list \
                        and referenced[d.name] == 0:
                    out.append(("UNREFERENCED", f"{m.rel}:{d.lineno}", f"{d.name} is never named anywhere"))
    for cycle in cycles(edges):
        path = "; ".join(edges[a][b] for a, b in zip(cycle, cycle[1:] + cycle[:1]) if b in edges[a])
        out.append(("CYCLE", " <-> ".join(cycle), path))
    return [{"flag": f, "where": w, "detail": d} for f, w, d in out]


def cycles(edges):
    """Strongly connected groups of 2+ nodes (Tarjan), each listed in a stable order."""
    index, low, stack, on, found, counter = {}, {}, [], set(), [], [0]

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in edges.get(v, {}):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            group = []
            while True:
                w = stack.pop()
                on.discard(w)
                group.append(w)
                if w == v:
                    break
            if len(group) > 1:
                found.append(sorted(group))

    for v in sorted(edges):
        if v not in index:
            visit(v)
    return found


def scan(root, min_nodes):
    mods, unparsed = [], []
    for path in walk(root, lambda f: f.endswith(".py")):
        try:
            mods.append(Mod(root, path))
        except (SyntaxError, ValueError) as e:
            unparsed.append(f"{os.path.relpath(path, root)}: {e}")
    local_tops = {m.name.split(".")[0] for m in mods if m.name}
    deps, declared = dependency_findings(root, mods, local_tops)
    return {
        "root": root, "checked": dt.date.today().isoformat(), "files": len(mods),
        "lines": sum(m.lines for m in mods), "declared": len(declared),
        "duplicates": duplicates(mods, min_nodes), "dependencies": deps,
        "code": code_findings(mods, local_tops, declared), "structure": structure_findings(mods),
        "unparsed": unparsed,
    }


def table(header, rows):
    if not rows:
        return "none\n"
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(USAGE)
    min_nodes = 25
    if "--min-nodes" in args:
        i = args.index("--min-nodes")
        min_nodes = int(args[i + 1])
        del args[i:i + 2]
    r = scan(os.path.abspath([a for a in args if not a.startswith("--")][0]), min_nodes)
    if "--json" in args:
        print(json.dumps(r, indent=1))
        return
    print(f"Scanned {os.path.basename(r['root'])}: {r['files']} files, {r['lines']} lines, "
          f"{r['declared']} declared dependencies ({r['checked']})")
    print("Every row is a lead: open the code before acting on it.\n")
    saves = sum(d["saves"] for d in r["duplicates"] if d["kind"] == "EXACT")
    print(f"## Duplicate code (exact copies alone: ~{saves} lines)")
    print(table(["Kind", "Copies", "Lines", "Saves", "Where", "Differs"],
                [[d["kind"], d["copies"], d["lines"], d["saves"], "<br>".join(d["where"]),
                  ", ".join(d["differs"]) or "-"] for d in r["duplicates"]]))
    print("## Dependencies")
    print(table(["Flag", "Package", "Evidence"], [[f["flag"], f["package"], f["detail"]] for f in r["dependencies"]]))
    print("## Code")
    print(table(["Flag", "Where", "Detail"], [[f["flag"], f["where"], f["detail"]] for f in r["code"]]))
    print("## Structure")
    print(table(["Flag", "Where", "Detail"], [[f["flag"], f["where"], f["detail"]] for f in r["structure"]]))
    if r["unparsed"]:
        print("Could not parse: " + "; ".join(r["unparsed"]))


if __name__ == "__main__":
    main()
