"""Scan a Python repo for which service reads and writes which table, with file:line evidence.
Follows calls into shared libraries, so a repo function lands only on the services that call it."""
USAGE = """Usage:
  python3 scan_access.py REPO_DIR access.json

Services come from docker-compose (name, build dir, DATABASE_URL), then any folder with a Dockerfile,
then Alembic folders (as "migrations"). Code outside every service is a library; its reads and writes
go to each service that calls into it. Tests are skipped.

Recognized: SQL in strings and in .sql files the code loads; SQLAlchemy (select, query, get, add,
merge, delete, insert/update/delete, changing a loaded object); Django (Model.objects..., save,
delete); pandas (read_sql*, to_sql); BigQuery client (load_table_*, insert_rows*, copy_table,
QueryJobConfig destination); Alembic op.* (as schema changes). f-string SQL whose table is a
function argument is resolved from call sites that pass a constant; anything else is unresolved."""
import ast
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlscan import looks_like_sql, split_name, tables as sql_tables  # noqa: E402

SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", "build", "dist", ".tox", ".mypy_cache",
             ".pytest_cache", "site-packages"}
READ_METHODS = {"filter", "get", "all", "exclude", "values", "values_list", "count", "exists", "first", "last",
                "aggregate", "annotate", "select_related", "prefetch_related", "order_by", "in_bulk", "iterator",
                "only", "defer", "raw", "distinct", "latest", "earliest"}
WRITE_METHODS = {"create": "INSERT", "bulk_create": "INSERT", "update": "UPDATE", "bulk_update": "UPDATE",
                 "delete": "DELETE", "get_or_create": "UPSERT", "update_or_create": "UPSERT"}
BQ_WRITES = {"load_table_from_dataframe": (1, "LOAD"), "load_table_from_uri": (1, "LOAD"),
             "load_table_from_file": (1, "LOAD"), "load_table_from_json": (1, "LOAD"), "insert_rows": (0, "INSERT"),
             "insert_rows_json": (0, "INSERT"), "insert_rows_from_dataframe": (0, "INSERT")}
ALEMBIC = {"create_table": 0, "drop_table": 0, "add_column": 0, "drop_column": 0, "alter_column": 0,
           "rename_table": 0, "create_index": 1, "create_unique_constraint": 1, "create_foreign_key": 1,
           "drop_constraint": 1, "batch_alter_table": 0, "bulk_insert": 0}


def is_test(rel):
    parts = rel.split(os.sep)
    return bool({"tests", "test", "testing"} & set(parts[:-1])) or parts[-1].startswith("test_") or \
        parts[-1].endswith("_test.py") or parts[-1] == "conftest.py"


def mini_yaml(text):
    """Enough YAML for docker-compose: nested maps, lists of scalars, and 'KEY=VAL' env lists."""
    root = {}
    stack = [(-1, root, None, None)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = re.sub(r"\s+#.*$", "", raw.rstrip())
        indent = len(line) - len(line.lstrip())
        s = line.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        _, cont, owner, key = stack[-1]
        if s.startswith("- "):
            if isinstance(cont, dict) and not cont and owner is not None:
                cont = owner[key] = []
                stack[-1] = (stack[-1][0], cont, owner, key)
            if isinstance(cont, list):
                cont.append(s[2:].strip().strip("'\""))
            continue
        m = re.match(r"([^:]+):\s*(.*)$", s)
        if not m or not isinstance(cont, dict):
            continue
        k, v = m.group(1).strip().strip("'\""), m.group(2).strip().strip("'\"")
        if v:
            cont[k] = v
        else:
            cont[k] = {}
            stack.append((indent, cont[k], cont, k))
    return root


def parse_db_url(url):
    m = re.match(r"(\w+)(?:\+\w+)?://(?:([^:@/]+)(?::[^@]*)?@)?[^/]*/([\w-]+)", url or "")
    if not m:
        return None
    return {"engine": {"postgresql": "postgres", "postgres": "postgres"}.get(m.group(1), m.group(1)),
            "db": m.group(3), "role": m.group(2)}


def find_services(root):
    services = []
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        for svc, spec in (mini_yaml(open(path).read()).get("services") or {}).items():
            if not isinstance(spec, dict):
                continue
            build = spec.get("build")
            build = build.get("context") if isinstance(build, dict) else build
            env = spec.get("environment") or {}
            if isinstance(env, list):
                env = dict(e.split("=", 1) for e in env if "=" in e)
            if build:
                services.append({"name": svc, "root": os.path.normpath(build).lstrip("./") or ".", "env": env,
                                 "kind": "service", "found_by": name})
    known = {s["root"] for s in services}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        rel = os.path.relpath(d, root)
        if "Dockerfile" in files and rel not in known and rel != ".":
            services.append({"name": os.path.basename(d).replace("_", "-"), "root": rel, "env": {},
                             "kind": "service", "found_by": "Dockerfile"})
            known.add(rel)
        if "alembic.ini" in files:
            ini = open(os.path.join(d, "alembic.ini")).read()
            loc = re.search(r"script_location\s*=\s*(\S+)", ini)
            target = os.path.normpath(loc.group(1)) if loc and not loc.group(1).startswith("%") else rel
            services.append({"name": "migrations", "root": target, "env": {}, "kind": "migrations",
                             "found_by": "alembic.ini"})
    for s in services:
        url = next((v for k, v in s["env"].items() if re.search(r"(DATABASE|DB|PG|POSTGRES|MYSQL)_?(URL|URI|DSN)",
                                                                  k, re.I)), None)
        s["db"] = parse_db_url(url)
        s["bigquery"] = sorted({v for k, v in s["env"].items() if re.search(r"BQ|BIGQUERY|DATASET", k, re.I)
                                and re.fullmatch(r"[\w-]+\.[\w-]+", v)})
    dbs = [s["db"]["db"] for s in services if s["db"]]
    for s in services:
        if not s["db"] and dbs and len(set(dbs)) == 1:
            s["db"] = {"engine": "same as the other services", "db": dbs[0], "role": None}
    return services


class FileScan:
    def __init__(self, root, rel):
        self.root, self.rel = root, rel
        self.dir = os.path.dirname(os.path.join(root, rel))
        self.module = rel[:-3].replace(os.sep, ".").removesuffix(".__init__")
        self.tree = ast.parse(open(os.path.join(root, rel), encoding="utf-8", errors="replace").read())
        self.imports, self.consts, self.models, self.funcs, self.classes = {}, {}, {}, {}, set()
        self.docstrings = set()
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body \
                    and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                self.docstrings.add(id(node.body[0].value))
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.imports[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = self.module.split(".")[:-node.level] if not rel.endswith("__init__.py") else \
                        self.module.split(".")[:len(self.module.split(".")) - node.level + 1]
                    base = ".".join(parts + ([node.module] if node.module else []))
                for a in node.names:
                    self.imports[a.asname or a.name] = f"{base}.{a.name}"
        for node in self.tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self.consts[node.targets[0].id] = node.value
            elif isinstance(node, ast.ClassDef):
                self.classes.add(node.name)
                table = self.model_table(node)
                if table:
                    self.models[node.name] = table

    def model_table(self, cls):
        for st in cls.body:
            if isinstance(st, ast.Assign) and any(getattr(t, "id", "") == "__tablename__" for t in st.targets) \
                    and isinstance(st.value, ast.Constant):
                return st.value.value
            if isinstance(st, ast.ClassDef) and st.name == "Meta":
                for m in st.body:
                    if isinstance(m, ast.Assign) and any(getattr(t, "id", "") == "db_table" for t in m.targets) \
                            and isinstance(m.value, ast.Constant):
                        return m.value.value
        bases = [ast.unparse(b) for b in cls.bases]
        if any(b.endswith("models.Model") for b in bases):
            return f"{os.path.basename(self.dir)}_{cls.name.lower()}"
        return None

    def dotted(self, node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        head = self.imports.get(node.id) or (f"{self.module}.{node.id}" if node.id in self.classes or
                                             node.id in self.funcs else None)
        return ".".join([head] + parts[::-1]) if head else None


def str_value(fs, node, local):
    """Literal text of a string expression; f-string slots become {} and their names are returned."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, []
    if isinstance(node, ast.Name):
        src = local.get(node.id) or fs.consts.get(node.id)
        return str_value(fs, src, {}) if src is not None and src is not node else (None, [])
    if isinstance(node, ast.JoinedStr):
        text, names = "", []
        for v in node.values:
            if isinstance(v, ast.Constant):
                text += str(v.value)
            else:
                text += "{}"
                names.append(ast.unparse(v.value))
        return text, names
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, na = str_value(fs, node.left, local)
        b, nb = str_value(fs, node.right, local)
        return (a + b, na + nb) if a is not None and b is not None else (None, [])
    if isinstance(node, ast.Call):
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name == "text" and node.args:
            return str_value(fs, node.args[0], local)
        if name in ("read_text", "read"):
            return sql_file(fs, node)
    return None, []


def sql_file(fs, call):
    """Contents of a .sql file loaded with Path(...).read_text() or open(...).read()."""
    consts = [n.value for n in ast.walk(call) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    if not any(c.endswith(".sql") for c in consts):
        return None, []
    cand = os.path.join(fs.dir, *[c for c in consts if not c.startswith(("r", "w")) or c.endswith(".sql")])
    if not os.path.exists(cand):
        base = next(c for c in consts if c.endswith(".sql"))
        hits = [os.path.join(d, base) for d, _, fs_ in os.walk(fs.root) if base in fs_]
        cand = hits[0] if hits else None
    if cand and os.path.exists(cand):
        fs.loaded_sql = os.path.relpath(cand, fs.root)
        return open(cand).read(), []
    return None, []


def scan_function(fs, key, body, params, registry, out_calls, out_access, out_unresolved):
    local, types = {}, {}
    nodes = []
    stack = list(body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        nodes.append(n)
        stack.extend(ast.iter_child_nodes(n))
    nodes.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))

    def model(node):
        if isinstance(node, ast.Attribute) and not isinstance(node.value, ast.Call):
            inner = model(node.value)
            if inner:
                return inner
        d = fs.dotted(node) if isinstance(node, (ast.Name, ast.Attribute)) else None
        return registry["models"].get(d) if d else None

    def access(table, kind, op, line, how, db=None):
        if db == "bq" and table.count(".") >= 2:
            db, table = split_name(table)
        if kind == "ddl" and key.endswith(".downgrade"):
            return
        out_access.append({"key": key, "file": fs.rel, "line": line, "table": table, "db": db, "kind": kind,
                           "op": op, "how": how})

    def sql_access(text, names, line, how):
        found = sql_tables(text)
        for db, table, kind, op in found:
            if "{}" in table:
                out_unresolved.append({"key": key, "file": fs.rel, "line": line, "op": op, "kind": kind,
                                       "sql": " ".join(text.split())[:140], "slots": names, "params": params})
            else:
                access(table, kind, op, line, how, db)

    def table_arg(node):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "get_table" and node.args:
            node = node.args[0]
        text, names = str_value(fs, node, local)
        return text if text and not names else None

    for n in nodes:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            var, v = n.targets[0].id, n.value
            local[var] = v
            if isinstance(v, ast.Call):
                m = model(v.func)
                if m:
                    types[var] = ("new", m)
                    continue
                chain = [c for c in ast.walk(v) if isinstance(c, ast.Call)]
                for c in chain:
                    fname = getattr(c.func, "attr", getattr(c.func, "id", ""))
                    if fname in ("get", "query", "select") and c.args and model(c.args[0]):
                        types[var] = ("loaded", model(c.args[0]))
                    elif isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Attribute) and \
                            c.func.value.attr == "objects" and model(c.func.value.value):
                        types[var] = ("loaded", model(c.func.value.value))
                d = fs.dotted(v.func)
                if d and d in registry["classes"]:
                    types[var] = ("obj", d)
        line = getattr(n, "lineno", 0)
        if isinstance(n, (ast.Constant, ast.JoinedStr)) and id(n) not in fs.docstrings:
            text, names = str_value(fs, n, {})
            if text and looks_like_sql(text):
                sql_access(text, names, line, "SQL string")
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and \
                        types.get(t.value.id, ("",))[0] == "loaded":
                    access(types[t.value.id][1], "write", "UPDATE", line, f"changes a loaded {t.value.id}")
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        meth = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        d = fs.dotted(f) or ""
        if meth in ("read_text", "read"):
            text, _ = sql_file(fs, n)
            if text:
                sql_access(text, [], line, f"SQL file {getattr(fs, 'loaded_sql', '')}")
        if d.startswith("sqlalchemy.") and meth in ("insert", "update", "delete") and n.args and model(n.args[0]):
            access(model(n.args[0]), "write", meth.upper(), line, f"sqlalchemy {meth}()")
        elif meth in ("select", "query") and (d.startswith("sqlalchemy") or meth == "query"):
            for a in n.args:
                if model(a):
                    access(model(a), "read", "SELECT", line, f"{meth}({ast.unparse(a).split('.')[0]})")
        elif meth == "get" and isinstance(f, ast.Attribute) and n.args and model(n.args[0]) and \
                not (isinstance(f.value, ast.Attribute) and f.value.attr == "objects"):
            access(model(n.args[0]), "read", "SELECT", line, "session.get()")
        elif meth in ("add", "merge", "add_all", "bulk_save_objects"):
            items = n.args[0].elts if n.args and isinstance(n.args[0], (ast.List, ast.Tuple)) else n.args[:1]
            for a in items:
                if isinstance(a, ast.Call) and model(a.func):
                    access(model(a.func), "write", "INSERT", line, f"session.{meth}(new object)")
                elif isinstance(a, ast.Name) and a.id in types and types[a.id][0] in ("new", "loaded"):
                    op = "INSERT" if types[a.id][0] == "new" else "UPDATE"
                    access(types[a.id][1], "write", op, line, f"session.{meth}({a.id})")
        elif meth == "delete" and isinstance(f, ast.Attribute) and n.args and isinstance(n.args[0], ast.Name) and \
                n.args[0].id in types and types[n.args[0].id][0] != "obj":
            access(types[n.args[0].id][1], "write", "DELETE", line, "session.delete()")
        elif meth in ("bulk_insert_mappings", "bulk_update_mappings") and n.args and model(n.args[0]):
            access(model(n.args[0]), "write", "INSERT" if "insert" in meth else "UPDATE", line, meth)
        elif meth in ("save", "delete") and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and \
                types.get(f.value.id, ("",))[0] in ("new", "loaded"):
            kind, table = types[f.value.id]
            op = "DELETE" if meth == "delete" else ("INSERT" if kind == "new" else "UPDATE")
            access(table, "write", op, line, f"{f.value.id}.{meth}()")
        if isinstance(f, ast.Attribute):
            chain, node = [], f
            while isinstance(node, ast.Attribute):
                chain.append(node.attr)
                node = node.value.func if isinstance(node.value, ast.Call) else node.value
            if "objects" in chain:
                owner = f
                while isinstance(owner, ast.Attribute) and owner.attr != "objects":
                    owner = owner.value.func if isinstance(owner.value, ast.Call) else owner.value
                m = model(owner.value) if isinstance(owner, ast.Attribute) else None
                if m and chain[0] in WRITE_METHODS:
                    access(m, "write", WRITE_METHODS[chain[0]], line, f"objects.{chain[0]}()")
                elif m and chain[0] in READ_METHODS:
                    access(m, "read", "SELECT", line, f"objects.{chain[0]}()")
        if meth in ("read_sql", "read_sql_query", "read_sql_table") and n.args:
            text, _ = str_value(fs, n.args[0], local)
            if text and not looks_like_sql(text) and re.fullmatch(r"[\w.]+", text):
                access(text, "read", "SELECT", line, f"pandas {meth}()")
        if meth == "to_sql" and n.args:
            name = table_arg(n.args[0])
            if name:
                access(name, "write", "INSERT", line, "pandas to_sql()")
        if meth in BQ_WRITES:
            pos, op = BQ_WRITES[meth]
            arg = next((k.value for k in n.keywords if k.arg in ("destination", "table")), None) or \
                (n.args[pos] if len(n.args) > pos else None)
            name = table_arg(arg) if arg is not None else None
            if name:
                access(name, "write", op, line, f"bigquery {meth}()", "bq")
            elif arg is not None:
                out_unresolved.append({"key": key, "file": fs.rel, "line": line, "op": op, "kind": "write",
                                       "sql": ast.unparse(n)[:140], "slots": [ast.unparse(arg)], "params": params})
        if meth == "copy_table" and len(n.args) >= 2:
            src, dst = table_arg(n.args[0]), table_arg(n.args[1])
            if src:
                access(src, "read", "SELECT", line, "bigquery copy_table()", "bq")
            if dst:
                access(dst, "write", "COPY", line, "bigquery copy_table()", "bq")
        for k in n.keywords:
            if k.arg == "destination" and meth == "QueryJobConfig":
                name = table_arg(k.value)
                if name:
                    access(name, "write", "QUERY RESULT", line, "QueryJobConfig(destination=)", "bq")
        if d.startswith("alembic.op.") and meth in ALEMBIC:
            pos = ALEMBIC[meth]
            arg = next((k.value for k in n.keywords if k.arg in ("table_name", "source_table")), None) or \
                (n.args[pos] if len(n.args) > pos else None)
            name = table_arg(arg) if arg is not None else None
            if name:
                access(name, "ddl", meth.upper().replace("_", " "), line, f"alembic op.{meth}()")
        target = None
        if isinstance(f, ast.Name):
            target = fs.dotted(f)
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            if f.value.id in types and types[f.value.id][0] == "obj":
                target = f"{types[f.value.id][1]}.{f.attr}"
            elif f.value.id == "self" and "." in key:
                target = f"{key.rsplit('.', 1)[0]}.{f.attr}"
            else:
                target = fs.dotted(f)
        if target:
            consts = {i: a.value for i, a in enumerate(n.args) if isinstance(a, ast.Constant)}
            consts.update({k.arg: k.value.value for k in n.keywords if isinstance(k.value, ast.Constant)})
            out_calls.append((key, target, fs.rel, line, consts))


def scan(root):
    services = find_services(root)
    files = []
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            rel = os.path.relpath(os.path.join(d, n), root)
            if n.endswith(".py") and not is_test(rel):
                try:
                    files.append(FileScan(root, rel))
                except SyntaxError:
                    pass
    registry = {"models": {}, "classes": set()}
    for fs in files:
        for cls, table in fs.models.items():
            registry["models"][f"{fs.module}.{cls}"] = table
        registry["classes"] |= {f"{fs.module}.{c}" for c in fs.classes}
        for node in fs.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fs.funcs[node.name] = node
    calls, accesses, unresolved, funcs = [], [], [], {}
    for fs in files:
        units = [(f"{fs.module}.<module>", [n for n in fs.tree.body if not isinstance(
            n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], [])]
        for node in fs.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                units.append((f"{fs.module}.{node.name}", node.body, [a.arg for a in node.args.args]))
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        units.append((f"{fs.module}.{node.name}.{sub.name}", sub.body,
                                      [a.arg for a in sub.args.args]))
        for key, body, params in units:
            funcs[key] = fs.rel
            scan_function(fs, key, body, params, registry, calls, accesses, unresolved)

    for u in list(unresolved):
        for slot in u["slots"]:
            if slot in u["params"]:
                idx = u["params"].index(slot)
                for caller, target, rel, line, consts in calls:
                    value = consts.get(idx, consts.get(slot))
                    if target == u["key"] and isinstance(value, str):
                        sql = u["sql"].replace("{}", value, 1)
                        for db, table, kind, op in sql_tables(sql):
                            accesses.append({"key": u["key"], "file": u["file"], "line": u["line"], "table": table,
                                             "db": db, "kind": kind, "op": op,
                                             "how": f"f-string; {slot}='{value}' passed at {rel}:{line}"})
                        u["resolved_by"] = f"{rel}:{line}"

    def owner(rel):
        best = None
        for s in services:
            if s["root"] == "." or rel.startswith(s["root"].rstrip("/") + os.sep):
                if not best or len(s["root"]) > len(best["root"]):
                    best = s
        return best

    edges = defaultdict(list)
    for caller, target, rel, line, _ in calls:
        if target in funcs:
            edges[caller].append((target, rel, line))
        elif target.rsplit(".", 1)[0] in registry["classes"] or target in registry["classes"]:
            init = target if target in funcs else f"{target}.__init__"
            if init in funcs:
                edges[caller].append((init, rel, line))
    module_of = {k: k.rsplit(".", 1)[0] if not k.endswith("<module>") else k[:-9] for k in funcs}
    by_key = defaultdict(list)
    for a in accesses:
        by_key[a["key"]].append(a)
    rows, reached_lib = [], set()
    for s in services:
        starts = [k for k, rel in funcs.items() if owner(rel) is s]
        seen, queue, via = set(starts), list(starts), {k: None for k in starts}
        while queue:
            k = queue.pop()
            nexts = list(edges.get(k, []))
            mod = module_of[k].rsplit(".", 1)[0] if "." in module_of[k] else module_of[k]
            for cand in (f"{module_of[k]}.<module>", f"{mod}.<module>"):
                if cand in funcs and cand not in seen and owner(funcs[cand]) is None:
                    nexts.append((cand, funcs[k], 0))
            for target, rel, line in nexts:
                if target not in seen:
                    seen.add(target)
                    via[target] = via[k] or f"{rel}:{line}"
                    queue.append(target)
        for k in seen:
            lib = owner(funcs[k]) is None
            if lib:
                reached_lib.add(k)
            for a in by_key.get(k, []):
                db = resolve_db(a, s)
                rows.append({"service": s["name"], "database": db, "table": a["table"], "kind": a["kind"],
                             "op": a["op"], "file": a["file"], "line": a["line"], "how": a["how"],
                             "via": f"called from {via[k]}" if lib and via[k] else None})
    unused = sorted({f"{a['file']}:{a['line']} {a['kind']} {a['table']}" for a in accesses
                     if owner(funcs[a["key"]]) is None and a["key"] not in reached_lib})
    unres = [dict(service=(owner(u["file"]) or {}).get("name"), **{k: u[k] for k in ("file", "line", "op", "sql")},
                  resolved_by=u.get("resolved_by")) for u in unresolved]
    return {"root": os.path.abspath(root), "services": [
        {k: s[k] for k in ("name", "root", "kind", "found_by", "db", "bigquery")} for s in services],
        "accesses": sorted(rows, key=lambda r: (r["service"], r["database"], r["table"], r["kind"], r["line"])),
        "unresolved": unres, "unused_library": unused}


def resolve_db(a, s):
    """Which database a table lives in: BigQuery names carry it; otherwise the service's DATABASE_URL."""
    table, db = a["table"], a["db"]
    if db and db != "bq":
        return db
    parts = table.split(".")
    if len(parts) == 2:
        match = [d for d in s["bigquery"] if d.split(".")[-1] == parts[0]]
        if match:
            a["table"] = parts[1]
            return match[0]
    if db == "bq":
        return s["bigquery"][0] if s["bigquery"] else "bigquery"
    return (s["db"] or {}).get("db") or "default"


def main():
    a = sys.argv[1:]
    if len(a) != 2 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    result = scan(a[0])
    with open(a[1], "w") as f:
        json.dump(result, f, indent=1)
    print(f"{len(result['services'])} services, {len(result['accesses'])} accesses, "
          f"{len(result['unresolved'])} unresolved\n")
    for s in result["services"]:
        rows = [r for r in result["accesses"] if r["service"] == s["name"]]
        db = s["db"] or {}
        print(f"## {s['name']} ({s['root']}; {db.get('engine', '?')} {db.get('db', '')} as {db.get('role', '?')}"
              f"{'; bigquery ' + ', '.join(s['bigquery']) if s['bigquery'] else ''})")
        for kind in ("write", "read", "ddl"):
            items = sorted({f"{r['database']}.{r['table']} {r['op']}" if kind != "read" else
                            f"{r['database']}.{r['table']}" for r in rows if r["kind"] == kind})
            if items:
                print(f"  {kind}: " + ", ".join(items))
    for u in result["unresolved"]:
        print(f"UNRESOLVED {u['file']}:{u['line']} {u['op']}: {u['sql']}"
              + (f" (resolved from {u['resolved_by']})" if u["resolved_by"] else ""))
    for u in result["unused_library"]:
        print(f"LIBRARY, NO CALLER {u}")


if __name__ == "__main__":
    main()
