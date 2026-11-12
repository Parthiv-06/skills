"""Measure an agent prompt and, given a compressed version, check nothing exact was lost.

Usage:
  python3 prompt_check.py original.md                  # stats + redundancy report
  python3 prompt_check.py original.md compressed.md    # adds savings + protected-token gate

Protected tokens are strings an agent may depend on verbatim: `code spans`, "quoted strings",
{placeholders}, <xml_tags>, URLs, file paths, numbers, snake_case / camelCase / ALL_CAPS
identifiers, and fenced code blocks. Exit code 1 if any are missing from the compressed prompt.
Token counts are estimates (chars / 4).
"""
import difflib
import re
import sys

EMPHASIS = {"IMPORTANT", "MUST", "NEVER", "ALWAYS", "CRITICAL", "NOT", "DO", "ONLY", "NO", "YOU", "NOTE"}
FILLER = [
    "please", "make sure to", "make sure that", "be sure to", "it is important that",
    "it is important to", "it's important to", "it is crucial", "you should always",
    "try to", "in order to", "basically", "very", "really", "note that", "keep in mind",
    "remember to", "as an ai", "as a helpful assistant", "feel free to", "at all times",
    "in any case", "of course", "obviously", "simply", "just", "you are able to",
]
PROTECTED = [
    re.compile(r"`[^`\n]+`"),
    re.compile(r"\"[^\"\n]{1,80}\""),
    re.compile(r"\{\{?[A-Za-z_][\w.]*\}?\}"),
    re.compile(r"</?[A-Za-z_][\w-]*>"),
    re.compile(r"https?://\S+"),
    re.compile(r"(?:\.{0,2}/)?[\w-]+(?:/[\w.-]+)+|\b[\w-]+\.(?:md|json|py|ts|js|yaml|yml|txt|html|csv)\b"),
    re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?\s?(?:%|ms|s|chars?|tokens?|words?|lines?|days?|hours?|minutes?)?(?![\w.])"),
    re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b|\b[a-z]+(?:[A-Z][a-z0-9]+)+\b|\b[A-Z]{3,}(?:_[A-Z0-9]+)*\b|\b[A-Z0-9]+(?:_[A-Z0-9]+)+\b"),
]
FENCE = re.compile(r"```.*?```", re.S)


def est_tokens(text):
    return round(len(text) / 4)


def sentences(text):
    prose = FENCE.sub(" ", text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", prose)
    return [p.strip(" -*#>\t") for p in parts if len(p.strip(" -*#>\t").split()) >= 4]


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def protected_tokens(text):
    found = set()
    for block in FENCE.findall(text):
        found.add(("code block", " ".join(block.split())))
    prose = FENCE.sub(" ", text)
    for pat in PROTECTED:
        for m in pat.findall(prose):
            tok = m.strip()
            if tok and tok.strip("_") and tok not in EMPHASIS:
                found.add(("token", tok))
    return found


def stats(name, text):
    print(f"{name}: {len(text)} chars, {len(text.split())} words, {text.count(chr(10)) + 1} lines, ~{est_tokens(text)} tokens")


def redundancy(text):
    sents = sentences(text)
    print("\nRepeated or near-repeated sentences:")
    seen, hits = {}, 0
    for i, s in enumerate(sents):
        n = norm(s)
        if n in seen:
            print(f"  exact   : \"{s[:90]}\"")
            hits += 1
            continue
        for j, prev in seen.items():
            if difflib.SequenceMatcher(None, n, j).ratio() >= 0.8:
                print(f"  similar : \"{s[:90]}\"\n         ~ \"{prev[:90]}\"")
                hits += 1
                break
        seen[n] = s
    if not hits:
        print("  none by text match (same meaning in different words is found in the inventory step)")

    low = text.lower()
    counts = [(f, len(re.findall(r"\b" + re.escape(f) + r"\b", low))) for f in FILLER]
    counts = [(f, c) for f, c in counts if c]
    print("\nFiller phrases:", ", ".join(f"\"{f}\" x{c}" for f, c in sorted(counts, key=lambda x: -x[1])) or "none")
    caps = re.findall(r"\b(?:" + "|".join(EMPHASIS) + r")\b", text)
    print(f"Shouted emphasis words: {len(caps)}" + (" (stacked emphasis dilutes itself; keep it for the 1-3 rules that truly need it)" if len(caps) > 5 else ""))


def compare(orig, comp):
    a, b = len(orig), len(comp)
    print(f"\nSaved: {a - b} chars ({(a - b) / a:.0%}), ~{est_tokens(orig) - est_tokens(comp)} tokens")
    comp_norm = " ".join(comp.split())
    missing = []
    for kind, tok in sorted(protected_tokens(orig)):
        haystack = comp if kind == "token" else comp_norm
        if tok not in haystack:
            missing.append((kind, tok))
    print("\nProtected-token gate:", "PASS" if not missing else f"FAIL ({len(missing)} missing)")
    for kind, tok in missing:
        print(f"  missing {kind}: {tok[:100]}")
    if missing:
        print("  Restore each one, or record in the ledger why the compressed prompt no longer needs it.")
    return not missing


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    original = open(sys.argv[1], encoding="utf-8").read()
    stats("Original  ", original)
    if len(sys.argv) == 2:
        redundancy(original)
        sys.exit(0)
    compressed = open(sys.argv[2], encoding="utf-8").read()
    stats("Compressed", compressed)
    sys.exit(0 if compare(original, compressed) else 1)
