"""Check a demo JSON file against the page contract in ../SKILL.md and fill the HTML template.
Exits non-zero listing every missing or malformed field, so no half-filled page gets built."""
import html
import json
import os
import sys

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "demo-template.html")


def check(d):
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    for k in ("feature", "oneLiner", "audience"):
        need(isinstance(d.get(k), str) and d[k].strip(), f"{k}: required string")
    need(len(str(d.get("oneLiner", "")).split()) <= 20, "oneLiner: 20 words max; move caveats to questions or notFor")
    p = d.get("problem") or {}
    need(p.get("before") and p.get("after"), "problem: needs non-empty before and after lists")

    flow = d.get("flow") or {}
    ids = {n.get("id") for n in flow.get("nodes", [])}
    need(3 <= len(ids) <= 6, "flow.nodes: 3-6 nodes")
    for e in flow.get("edges", []):
        need(e.get("from") in ids and e.get("to") in ids, f"flow.edges: unknown node in {e}")

    uc = d.get("useCases") or []
    need(len(uc) >= 3, "useCases: at least 3")
    for i, u in enumerate(uc):
        for k in ("group", "title", "situation", "action", "result"):
            need(u.get(k), f"useCases[{i}].{k}: required")

    ex = d.get("explanations") or []
    need(len(ex) >= 3, "explanations: at least 3")
    for i, x in enumerate(ex):
        need(x.get("style") and x.get("text"), f"explanations[{i}]: needs style and text")

    sc = d.get("script") or {}
    steps = sc.get("steps") or []
    need(sc.get("setup"), "script.setup: required list")
    need(steps, "script.steps: required list")
    for i, s in enumerate(steps):
        need(s.get("time") and s.get("do") and s.get("say"), f"script.steps[{i}]: needs time, do, say")
    need(sum(1 for s in steps if s.get("wow")) == 1, "script.steps: exactly one step with wow: true")

    need(4 <= len(d.get("questions") or []) <= 8, "questions: 4-8 items")
    need(d.get("notFor"), "notFor: required list")
    need(d.get("sources"), "sources: required list")
    return errs


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 build_demo.py demo.json out.html")
    with open(sys.argv[1]) as f:
        d = json.load(f)
    errs = check(d)
    if errs:
        sys.exit("Demo JSON is incomplete:\n  " + "\n  ".join(errs))
    with open(TEMPLATE) as f:
        page = f.read()
    # "</" inside a <script> block would end it early; JSON allows the escaped form.
    data = json.dumps(d, indent=1, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("{{TITLE}}", html.escape(d["feature"])).replace("{{DEMO_JSON}}", data)
    with open(sys.argv[2], "w") as f:
        f.write(page)
    print(f"Wrote {sys.argv[2]}")


if __name__ == "__main__":
    main()
