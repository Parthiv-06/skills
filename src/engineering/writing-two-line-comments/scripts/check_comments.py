"""Gate for the two-line comment rule: flags long comment blocks, missing file headers, and noise.
Exit 1 lists every violation; in --hook mode it exits 2 so Claude Code shows the list to the agent."""
import ast
import inspect
import io
import json
import os
import re
import subprocess
import sys
import tokenize

USAGE = """Usage:
  check_comments.py FILE [FILE ...]   check these files
  check_comments.py --changed [DIR]   check files changed or added in the git repo at DIR (default .)
  check_comments.py --hook            read a Claude Code PostToolUse event on stdin and check its file

Rules (each reported as path:line: RULE):
  BLOCK      a comment or docstring has more than 2 lines of text
  LONG       a comment line is over 100 characters (no cramming a paragraph onto one line)
  NO-HEADER  a code file has no comment or docstring at the top
  CODE       commented-out code
  HISTORY    change-log wording ("fixed", "previously", "now handles", "as requested")
  BANNER     decorative divider lines (=====, -----, #####)
Not counted: shebangs, encoding lines, license/SPDX headers, and tool directives (noqa, eslint-disable, ...).
Skipped: files marked @generated or DO NOT EDIT, and vendored or build folders."""

MAX_LINES, MAX_CHARS = 2, 100
SLASH = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go", ".c", ".h", ".cc", ".cpp", ".hpp",
         ".cs", ".swift", ".kt", ".kts", ".rs", ".scala", ".php", ".dart", ".css", ".scss", ".less"}
HASH = {".sh", ".bash", ".zsh", ".rb", ".pl", ".r", ".yaml", ".yml", ".toml", ".tf", ".ex", ".exs"}
DASH = {".sql", ".lua", ".hs"}
NO_HEADER_NEEDED = {".yaml", ".yml", ".toml", ".css", ".scss", ".less", ".sql", ".tf"}
SKIP_DIRS = re.compile(r"(^|/)(node_modules|vendor|dist|build|\.venv|venv|__pycache__|\.git|\.next|target)(/|$)")

DIRECTIVE = re.compile(
    r"^\s*(!|-\*-|vim?:|noqa|type:|pragma|pylint:|mypy:|fmt:|isort:|ruff:|pyright:|eslint|prettier-ignore|"
    r"@ts-|istanbul|c8 |nolint|go:|\+build|#?region|#?endregion|swiftlint|rubocop|shellcheck|jshint|"
    r"biome-ignore|deno-|@jsx|/ <reference|SPDX-License-Identifier)", re.I)
LICENSE = re.compile(r"copyright|spdx-license|licensed under|all rights reserved", re.I)
CODE = [re.compile(p) for p in (
    r"^(import |from \S+ import |def |class |return\b|elif |else:|try:|except\b|raise |print\(|assert )",
    r"^(const|let|var|function|await|async|export|console\.|this\.|self\.)\b",
    r"^(if|for|while|with) .*:$", r";\s*$", r"[{}]\s*$", r"^\w[\w.\[\]]*\s*(=|\+=|-=)\s*[^=\s]",
    r"^\w[\w.]*\(.*\)$")]
HISTORY = re.compile(
    r"^(fixed|added|updated|changed|removed|refactored|renamed|moved|replaced|reverted)\b|"
    r"\b(previously (this|we|it|the code)|used to (be|do|return|call)|no longer|as requested|per (the )?review|was changed|"
    r"now (handles|uses|returns|supports|works))\b", re.I)
BANNER = re.compile(r"([=\-#*~_+/])\1{4,}")


def comment_lines_python(src):
    """Yield (line, text, kind) for every # comment and docstring line; kind groups lines into blocks.
    Docstring lines share one block per docstring; # comments group by adjacency later."""
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                full = not tok.line[:tok.start[1]].strip()
                yield tok.start[0], tok.string.lstrip("#").strip(), "full" if full else "trail"
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    for node in [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]:
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc = body[0]
            text = [ln for ln in inspect.cleandoc(doc.value.value).splitlines() if ln.strip()]
            yield doc.lineno, text, "doc"


def comment_lines_generic(src, ext):
    """Scan C-style, hash, or SQL-style sources for comments while skipping string literals.
    A /* */ block comes back as one 'doc' entry of its text lines, minus the star decoration."""
    line_marker = "//" if ext in SLASH else ("--" if ext in DASH else "#")
    has_block = ext in SLASH or ext == ".sql"
    i, n, line, quote = 0, len(src), 1, None
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'`" and not (ext in HASH and c == "`"):
            quote = c
            i += 1
            continue
        if has_block and src.startswith("/*", i):
            end = src.find("*/", i + 2)
            end = n if end < 0 else end
            body = src[i + 2:end]
            text = [re.sub(r"^\s*\*+\s?", "", ln).strip() for ln in body.lstrip("*").splitlines()]
            yield line, [t for t in text if t], "doc"
            line += body.count("\n")
            i = end + 2
            continue
        if src.startswith(line_marker, i) and (line_marker != "#" or i == 0 or src[i - 1] in " \t\n"):
            end = src.find("\n", i)
            end = n if end < 0 else end
            start_of_line = src.rfind("\n", 0, i) + 1
            full = not src[start_of_line:i].strip()
            yield line, src[i + len(line_marker):end].lstrip("/#-! ").strip(), "full" if full else "trail"
            i = end
            continue
        i += 1


def check_text(path, src):
    ext = os.path.splitext(path)[1].lower()
    head = "\n".join(src.splitlines()[:5])
    if re.search(r"@generated|DO NOT EDIT|auto-generated", head, re.I) or SKIP_DIRS.search(path.replace(os.sep, "/")):
        return []
    if ext == ".py":
        entries = list(comment_lines_python(src))
    elif ext in SLASH | HASH | DASH:
        entries = list(comment_lines_generic(src, ext))
    else:
        return []
    out = []
    lines = src.splitlines()
    first_code = first_code_line(src, lines, ext)
    if lines and lines[0].startswith("#!"):
        entries = [e for e in entries if e[0] != 1]

    blocks, current, last = [], [], None
    for ln, text, kind in sorted(entries, key=lambda e: e[0]):
        if kind == "doc":
            blocks.append((ln, [t for t in text if not DIRECTIVE.match(t)], "doc"))
            continue
        if DIRECTIVE.match(text):
            continue
        if kind == "full" and current and last == ln - 1 and current[-1][2] == "full":
            current.append((ln, text, kind))
        else:
            if current:
                blocks.append((current[0][0], [t for _, t, _ in current], "line"))
            current = [(ln, text, kind)]
        last = ln
    if current:
        blocks.append((current[0][0], [t for _, t, _ in current], "line"))
    blocks.sort(key=lambda b: b[0])
    # A license block above the code is legal boilerplate, so it is exempt from every rule.
    if blocks and (first_code is None or blocks[0][0] < first_code) and LICENSE.search(" ".join(blocks[0][1])):
        blocks = blocks[1:]

    for ln, texts, kind in blocks:
        if len(texts) > MAX_LINES:
            out.append((ln, "BLOCK", f"{len(texts)} lines; cut to 2: what it is, then what to watch"))
        for k, t in enumerate(texts):
            if len(t) > MAX_CHARS:
                out.append((ln + k, "LONG", f"{len(t)} chars; keep each line under {MAX_CHARS}"))
            if BANNER.search(t):
                out.append((ln + k, "BANNER", "decorative divider; delete it"))
            elif HISTORY.search(t):
                out.append((ln + k, "HISTORY", f"change-log wording belongs in the commit message: {t[:60]!r}"))
            elif kind == "line" and any(p.search(t) for p in CODE) and not t.endswith((".", "?", "!")):
                out.append((ln + k, "CODE", f"looks like commented-out code; delete it: {t[:60]!r}"))

    needs_header = ext not in NO_HEADER_NEEDED and sum(1 for ln in lines if ln.strip()) >= 3
    if needs_header and first_code is not None:
        if not [ln for ln, texts, _ in blocks if ln < first_code and texts]:
            out.append((1, "NO-HEADER", "add a 2-line header: what this file is, then what to watch"))
    return sorted(set(out))


def first_code_line(src, lines, ext):
    """Line number of the first real statement; for Python, the first one after the module docstring."""
    if ext == ".py":
        try:
            body = ast.parse(src).body
        except SyntaxError:
            body = []
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
            body = body[1:]
        return body[0].lineno if body else None
    return next((k + 1 for k, ln in enumerate(lines) if is_code_line(ln, ext)), None)


def is_code_line(ln, ext):
    """A line that is real code: not blank, not a comment, not a shebang or 'use strict'-style directive."""
    s = ln.strip()
    if not s or s.startswith(("#!", "//", "/*", "*", "*/")) or re.match(r"^['\"]use \w+['\"];?$", s):
        return False
    if ext == ".py":
        return not s.startswith(("#", '"""', "'''", 'r"""'))
    if ext in HASH:
        return not s.startswith("#")
    if ext in DASH:
        return not s.startswith("--")
    return True


def changed_files(root):
    """Files modified, staged, or untracked in the git repo at root."""
    run = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True).stdout.split("\n")
    names = run("diff", "--name-only", "HEAD") + run("ls-files", "--others", "--exclude-standard")
    return [os.path.join(root, f) for f in dict.fromkeys(names) if f and os.path.isfile(os.path.join(root, f))]


def report(paths):
    problems = []
    for p in paths:
        try:
            src = open(p, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        problems += [f"{p}:{ln}: {rule}: {msg}" for ln, rule, msg in check_text(p, src)]
    return problems


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if args[0] == "--hook":
        try:
            event = json.load(sys.stdin)
        except json.JSONDecodeError:
            return 0
        path = (event.get("tool_input") or {}).get("file_path")
        problems = report([path]) if path and os.path.isfile(path) else []
        if problems:
            print("Two-line comment rule: fix these before moving on (see the writing-two-line-comments skill):\n"
                  + "\n".join(problems), file=sys.stderr)
            return 2
        return 0
    paths = changed_files(args[1] if len(args) > 1 else ".") if args[0] == "--changed" else args
    problems = report(paths)
    print("\n".join(problems) if problems else f"OK: {len(paths)} file(s) follow the two-line comment rule")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
