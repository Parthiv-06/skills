"""Check an audit JSON file against the report contract and fill the HTML template.

Usage: python3 build_report.py token-audit.json report.html

Exits non-zero and lists every problem if a required field is missing or malformed.
The schema is the "Audit JSON" table in ../SKILL.md. Issues are re-ranked by tokensWasted.
"""
import html
import json
import os
import sys

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "report-template.html")
LABELS = {"measured", "counted", "estimated"}


def check(d):
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    def is_int(v):
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0

    need(isinstance(d.get("agent"), str) and d["agent"].strip(), "agent: required string")
    need(isinstance((d.get("task") or {}).get("name"), str), "task.name: required string")
    predict_only = bool(d.get("predictOnly"))
    num = d.get("numbers") or {}
    for k in ("ideal", "predicted"):
        need(is_int(num.get(k)), f"numbers.{k}: required non-negative integer")
    if predict_only:
        need(num.get("actual") is None, "numbers.actual: must be null when predictOnly is true")
    else:
        need(is_int(num.get("actual")), "numbers.actual: required integer (or set predictOnly: true)")
        need(is_int(num.get("runs")) and num["runs"] >= 3,
             f"numbers.runs: at least 3 runs (got {num.get('runs')}); run more or set predictOnly: true")
    for k, v in (num.get("labels") or {}).items():
        need(v in LABELS, f"numbers.labels.{k}: one of {sorted(LABELS)}")

    cost = d.get("cost")
    if cost is not None:
        for k in ("perTask", "per1k"):
            need(isinstance(cost.get(k), (int, float)), f"cost.{k}: required number")
        for k in ("pricingSource", "pricingDate"):
            need(cost.get(k), f"cost.{k}: required (prices change; say where and when they came from)")

    src = d.get("sources") or []
    need(src, "sources: required non-empty list")
    for i, s in enumerate(src):
        need(s.get("source") and is_int(s.get("tokens")), f"sources[{i}]: needs source and integer tokens")

    for i, c in enumerate(d.get("calls") or []):
        need(is_int(c.get("call")), f"calls[{i}].call: required integer")

    for i, x in enumerate(d.get("issues") if isinstance(d.get("issues"), list) else [None]):
        if x is None:
            errs.append("issues: required list (empty if nothing was found)")
            break
        for k in ("id", "title", "category", "fix"):
            need(isinstance(x.get(k), str) and x[k].strip(), f"issues[{i}].{k}: required string")
        need(x.get("severity") in ("high", "medium", "low"), f"issues[{i}].severity: high, medium, or low")
        need(is_int(x.get("tokensWasted")), f"issues[{i}].tokensWasted: required non-negative integer")
        need(x.get("confidence") in ("measured", "estimated"), f"issues[{i}].confidence: measured or estimated")
        need(x.get("risk") in ("safe", "behavior-affecting"), f"issues[{i}].risk: safe or behavior-affecting")
        ev = x.get("evidence") or {}
        need(ev.get("code") or ev.get("trace"), f"issues[{i}].evidence: needs code locations or trace evidence")
        for j, c in enumerate(ev.get("code") or []):
            need(c.get("file"), f"issues[{i}].evidence.code[{j}].file: required")

    m = d.get("map")
    if m:
        ids = {x.get("id") for x in m.get("nodes", [])}
        for e in m.get("edges", []):
            need(e.get("from") in ids and e.get("to") in ids, f"map.edges: unknown node in {e}")

    a = d.get("afterFix")
    if a:
        need(is_int(a.get("count")) and a["count"] >= 1, "afterFix.count: required integer >= 1")
        need(is_int(a.get("tokens")), "afterFix.tokens: required integer")
    return errs


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as f:
        d = json.load(f)
    errs = check(d)
    if errs:
        sys.exit("Audit JSON is incomplete:\n  " + "\n  ".join(errs))
    d["issues"].sort(key=lambda x: -x["tokensWasted"])
    with open(TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    # "</" inside a <script> block would end it early; JSON allows the escaped form.
    data = json.dumps(d, indent=1, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("{{TITLE}}", html.escape(d["agent"] + " token audit")).replace("{{AUDIT_JSON}}", data)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {sys.argv[2]}")


if __name__ == "__main__":
    main()
