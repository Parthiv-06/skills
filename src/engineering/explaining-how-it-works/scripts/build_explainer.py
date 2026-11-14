"""Checks an explainer JSON, draws every diagram, and builds the page (contract: SKILL.md).
Usage: build_explainer.py EXPLAINER.json OUT_DIR -> OUT_DIR/index.html and OUT_DIR/diagrams/."""
import html
import json
import os
import re
import sys

sys.dont_write_bytecode = True  # never leave __pycache__ in the skill folder or the user's repo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_plain import check_plain, plain_texts  # noqa: E402
from diagrams import SpecError, render, step_key  # noqa: E402

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "explainer-template.html")
STATUS = {"verified", "observed", "inferred"}
CARD = ("name", "purpose", "interface", "auth", "sends", "limits", "whenDown")


def check(d):
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    for k in ("question", "subject", "answer", "summary"):
        need(isinstance(d.get(k), str) and d[k].strip(), f"{k}: required string")
    need(len(str(d.get("answer", "")).split()) <= 30, "answer: one sentence, 30 words max")
    scope = d.get("scope") or {}
    need(scope.get("start") and scope.get("end"), "scope: needs start and end (where the path begins and ends)")

    trace = d.get("trace") or []
    need(trace, "trace: required; one row per hop")
    steps = []
    for i, t in enumerate(trace):
        for k in ("step", "from", "to", "how", "data"):
            need(str(t.get(k, "")).strip(), f"trace[{i}].{k}: required")
        need(step_key(t.get("step", "")) is not None, f"trace[{i}].step: like '3' or '3a'")
        need(t.get("status") in STATUS, f"trace[{i}].status: verified, observed, or inferred")
        need(t.get("where") or t.get("status") == "inferred", f"trace[{i}].where: file:line required unless status is inferred")
        steps.append(str(t.get("step")))
    need(len(set(steps)) == len(steps), "trace: step labels must be unique")
    keys = [step_key(s) for s in steps]
    need(None in keys or keys == sorted(keys), "trace: rows must be in step order")

    plain = d.get("plain") or {}
    ps = plain.get("steps") or []
    need(5 <= len(ps) <= 9, f"plain.steps: 5-9 steps (got {len(ps)})")
    for i, s in enumerate(ps):
        need(str(s.get("n")) == str(i + 1), f"plain.steps[{i}].n: must be {i + 1}")
        for k in ("title", "see", "behind"):
            need(str(s.get(k, "")).strip(), f"plain.steps[{i}].{k}: required")
        tech = s.get("tech") or []
        need(tech, f"plain.steps[{i}].tech: list the trace steps this plain step covers")
        for t in tech:
            need(str(t) in steps, f"plain.steps[{i}].tech: {t!r} is not a trace step")
    covered = {str(t) for s in ps for t in s.get("tech") or []}
    need(not set(steps) - covered, f"trace steps not covered by any plain step: {sorted(set(steps) - covered)}")
    for p in check_plain(plain_texts(plain) + [d.get("answer", "")], [t.get("term", "") for t in plain.get("terms") or []]):
        errs.append("plain English: " + p)

    diagrams = d.get("diagrams") or []
    views = [g.get("view") for g in diagrams]
    need("context" in views, "diagrams: a context view is required")
    need("sequence" in views, "diagrams: a sequence view is required")
    need(len(set(views)) == len(views), "diagrams: one diagram per view; a second view at the same level adds nothing")
    seq_steps = set()
    for g in diagrams:
        if g.get("view") == "sequence":
            seq_steps |= {str(m["step"]) for m in g.get("messages") or [] if m.get("step") is not None}
    need(not set(steps) - seq_steps, f"trace steps missing from the sequence diagram: {sorted(set(steps) - seq_steps)}")
    need(not seq_steps - set(steps), f"sequence steps missing from the trace: {sorted(seq_steps - set(steps))}")

    ext_ids = {e["id"] for g in diagrams for e in (g.get("elements") or []) + (g.get("participants") or [])
               if e.get("kind") == "external"}
    cards = {c.get("id"): c for c in d.get("external") or []}
    for x in sorted(ext_ids - set(cards)):
        errs.append(f"external: no card for external system {x!r} (every external element needs one)")
    for cid, c in cards.items():
        for k in CARD:
            need(str(c.get(k, "")).strip(), f"external[{cid}].{k}: required (write 'unknown: <why>' if the code can't tell)")
        need(c.get("evidence"), f"external[{cid}].evidence: file:line or docs URL")

    need(d.get("failures"), "failures: at least one failure mode")
    for i, f in enumerate(d.get("failures") or []):
        for k in ("what", "userSees", "codeDoes"):
            need(f.get(k), f"failures[{i}].{k}: required")
    need(d.get("sources"), "sources: list the files and URLs you read")
    return errs


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    with open(argv[0], encoding="utf-8") as f:
        d = json.load(f)
    errs = check(d)
    out_dir = argv[1]
    os.makedirs(os.path.join(out_dir, "diagrams"), exist_ok=True)
    warnings = []
    for g in d.get("diagrams") or []:
        try:
            svg, exc, warn = render(g)
        except SpecError as e:
            errs.append(str(e))
            continue
        except (KeyError, TypeError) as e:
            errs.append(f"diagram {g.get('title', g.get('view'))!r}: malformed spec ({e})")
            continue
        g["svg"] = svg
        warnings += [f"{g['view']}: {w}" for w in warn]
        with open(os.path.join(out_dir, "diagrams", g["view"] + ".excalidraw"), "w", encoding="utf-8") as f:
            json.dump(exc, f, indent=1)
        with open(os.path.join(out_dir, "diagrams", g["view"] + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    if errs:
        sys.exit("Explainer is not ready:\n  " + "\n  ".join(errs))
    for w in warnings:
        print("warning:", w)
    order = ["context", "containers", "components", "sequence", "state", "data", "deployment"]
    d["diagrams"].sort(key=lambda g: order.index(g["view"]))
    with open(TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    # "</" inside a <script> block would end it early; JSON allows the escaped form.
    data = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("{{TITLE}}", html.escape(re.sub(r"\s+", " ", d["subject"]).strip())).replace("{{EXPLAINER_JSON}}", data)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {os.path.join(out_dir, 'index.html')} and {len(d['diagrams'])} diagrams in {os.path.join(out_dir, 'diagrams')}")


if __name__ == "__main__":
    main(sys.argv[1:])
