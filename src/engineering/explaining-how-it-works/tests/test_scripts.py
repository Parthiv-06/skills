"""Tests for the diagram generator, the plain-English gate, and the explainer build checks.
The worked example in test/example-how-it-works must always build; the doc examples must render."""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import build_explainer  # noqa: E402
import diagrams  # noqa: E402
from check_plain import check_plain  # noqa: E402

EXAMPLE = os.path.join(SKILL, "..", "..", "..", "test", "example-how-it-works", "explainer.json")


def example():
    with open(EXAMPLE, encoding="utf-8") as f:
        return json.load(f)


def view(d, name):
    return next(g for g in d["diagrams"] if g["view"] == name)


class DiagramTest(unittest.TestCase):
    def test_doc_examples_render(self):
        with open(os.path.join(SKILL, "references", "diagram-style.md"), encoding="utf-8") as f:
            blocks = re.findall(r"```json\n(.*?)```", f.read(), re.S)
        self.assertEqual(len(blocks), 2)
        for b in blocks:
            svg, exc, _ = diagrams.render(json.loads(b))
            self.assertTrue(svg.startswith("<svg"))
            self.assertTrue(exc["elements"])

    def test_architect_style(self):
        _, exc, _ = diagrams.render(view(example(), "containers"))
        self.assertEqual({e["roughness"] for e in exc["elements"]}, {0})
        self.assertEqual({e["fontFamily"] for e in exc["elements"] if e["type"] == "text"}, {2})
        colors = {e["strokeColor"] for e in exc["elements"]} | {e["backgroundColor"] for e in exc["elements"]}
        self.assertLessEqual(colors, {diagrams.INK, diagrams.GRAY, diagrams.WHITE, "transparent", "#f8f9fa"})

    def test_arrows_bind_to_boxes(self):
        spec = view(example(), "containers")
        _, exc, _ = diagrams.render(spec)
        ids = {e["id"] for e in exc["elements"]}
        bound = [e for e in exc["elements"] if e["type"] == "arrow" and e["startBinding"]]  # legend samples are unbound
        self.assertEqual(len(bound), len(spec["links"]))
        for a in bound:
            self.assertEqual({a["startBinding"]["elementId"], a["endBinding"]["elementId"]} <= ids, True)
            box = next(e for e in exc["elements"] if e["id"] == a["startBinding"]["elementId"])
            self.assertIn({"type": "arrow", "id": a["id"]}, box["boundElements"])

    def test_rejects_bad_specs(self):
        good = view(example(), "containers")
        cases = {
            "every arrow needs a label": lambda s: s["links"][0].update(label=""),
            "elements[0].kind": lambda s: s["elements"][0].update(kind="cloud"),
            "too many": lambda s: s["elements"].extend({"id": f"x{i}", "kind": "service", "name": "x"} for i in range(10)),
            "unknown element": lambda s: s["links"][0].update(to="nowhere"),
            "title: required": lambda s: s.update(title=""),
            "overlap": lambda s: [e.update(col=0) for e in s["elements"] if e["zone"] == "anthropic"],
        }
        for msg, mutate in cases.items():
            s = copy.deepcopy(good)
            mutate(s)
            with self.assertRaises(diagrams.SpecError, msg=msg) as cm:
                diagrams.render(s)
            self.assertIn(msg, str(cm.exception))

    def test_sequence_rules(self):
        seq = view(example(), "sequence")
        s = copy.deepcopy(seq)
        s["frames"] = [{"type": "alt", "label": "x", "start": 0, "end": 1}]
        with self.assertRaisesRegex(diagrams.SpecError, "use opt"):
            diagrams.render(s)
        s = copy.deepcopy(seq)
        s["messages"][0]["step"] = "9"
        with self.assertRaisesRegex(diagrams.SpecError, "must not go backwards"):
            diagrams.render(s)

    def test_no_shared_arrow_ports(self):
        prims, _ = diagrams.layout(view(example(), "components"))
        ends = [tuple(round(v) for v in p["points"][0]) for p in prims if p["t"] == "arrow" and p.get("src")]
        self.assertEqual(len(ends), len(set(ends)), "two arrows leave the same point")


    def test_fan_out_and_pairs_do_not_cross_or_stack(self):
        spec = {"view": "containers", "title": "t", "caption": "c",
                "elements": [{"id": "a", "kind": "service", "name": "A", "col": 0, "row": 0},
                             {"id": "b", "kind": "service", "name": "B", "col": 1, "row": 0},
                             {"id": "c", "kind": "service", "name": "C", "col": 2, "row": 1},
                             {"id": "d", "kind": "service", "name": "D", "col": 2, "row": 2},
                             {"id": "e", "kind": "service", "name": "E", "col": 2, "row": 3}],
                "links": [{"from": "a", "to": "b", "label": "call"}, {"from": "b", "to": "a", "label": "reply"},
                          {"from": "b", "to": "c", "label": "x"}, {"from": "b", "to": "d", "label": "y"},
                          {"from": "b", "to": "e", "label": "z"}]}
        prims, _ = diagrams.layout(spec)
        arrows = [p for p in prims if p["t"] == "arrow" and p.get("src")]
        segs = [[(p, q) for p, q in zip(a["points"], a["points"][1:])] for a in arrows]

        def cross(s, t):  # a vertical and a horizontal segment strictly crossing
            (a, b), (c, d) = s, t
            if a[0] == b[0] and c[1] == d[1]:
                return min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1])
            return False
        for i in range(len(segs)):
            for j in range(len(segs)):
                if i != j:
                    self.assertFalse(any(cross(s, t) for s in segs[i] for t in segs[j]), f"arrows {i} and {j} cross")
        spots = {diagrams.label_anchor(a["points"], a.get("lane"))[:2] for a in arrows[:2]}
        self.assertEqual(len(spots), 2, "paired arrows share a label spot")


class PlainTest(unittest.TestCase):
    def test_flags_jargon_and_allows_defined_terms(self):
        probs = check_plain(["The webhook hits our API endpoint."])
        self.assertTrue(any("webhook" in p for p in probs) and any("api" in p for p in probs))
        self.assertEqual(check_plain(["Each answer counts the tokens used."], ["token"]), [])

    def test_sentence_length(self):
        long = " ".join(["word"] * 40) + "."
        self.assertTrue(any("too long" in p for p in check_plain([long])))


class BuildTest(unittest.TestCase):
    def test_example_builds(self):
        with tempfile.TemporaryDirectory() as out:
            p = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "build_explainer.py"), EXAMPLE, out],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(sorted(os.listdir(os.path.join(out, "diagrams"))),
                             sorted(f"{v}.{x}" for v in ("context", "containers", "components", "sequence") for x in ("svg", "excalidraw")))

    def test_cross_links_are_enforced(self):
        cases = {
            "not a trace step": lambda d: d["plain"]["steps"][0]["tech"].append("42"),
            "not covered by any plain step": lambda d: d["plain"]["steps"][-1].update(tech=["8"]),
            "no card for external system": lambda d: d.update(external=[]),
            "missing from the sequence diagram": lambda d: d["trace"].append(dict(d["trace"][-1], step="10")),
            "a context view is required": lambda d: d.update(diagrams=[g for g in d["diagrams"] if g["view"] != "context"]),
            "one diagram per view": lambda d: d["diagrams"].append(copy.deepcopy(view(d, "containers"))),
            "plain English": lambda d: d["plain"]["steps"][0].update(behind="The SDK calls the endpoint."),
            "file:line required": lambda d: d["trace"][0].update(where=""),
            "5-9 steps": lambda d: d["plain"].update(steps=d["plain"]["steps"][:3]),
        }
        for msg, mutate in cases.items():
            d = example()
            mutate(d)
            errs = build_explainer.check(d)
            self.assertTrue(any(msg in e for e in errs), f"{msg!r} not in {errs}")


if __name__ == "__main__":
    unittest.main()
