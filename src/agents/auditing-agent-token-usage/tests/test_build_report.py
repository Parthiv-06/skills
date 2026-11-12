import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "build_report.py")

VALID = {
    "agent": "Triage bot", "task": {"name": "Summarize open bugs"}, "model": "claude-sonnet-5-5", "date": "2026-11-13",
    "numbers": {"ideal": 1900, "predicted": 150000, "actual": 168068, "actualRange": [168068, 168068], "runs": 3,
                "labels": {"ideal": "estimated", "predicted": "estimated", "actual": "measured"}},
    "cost": None,
    "sources": [{"source": "History resent", "tokens": 134291}],
    "issues": [{"id": "huge-tool-result", "title": "A tool returns a 40 KB file", "category": "Context", "severity": "high",
                "tokensWasted": 120000, "confidence": "measured", "risk": "safe", "fix": "Truncate to 1,500 chars.",
                "evidence": {"trace": "calls 2-8 carry an 18.7k-token block"}}],
}


def build(data):
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "a.json"), os.path.join(tmp, "a.html")
        with open(src, "w") as f:
            json.dump(data, f)
        p = subprocess.run([sys.executable, SCRIPT, src, out], capture_output=True, text=True)
        html = open(out).read() if os.path.exists(out) else None
        return p, html


class BuildReportTest(unittest.TestCase):
    def test_valid_file_builds(self):
        p, html = build(VALID)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("<title>Triage bot token audit</title>", html)
        self.assertNotIn("{{AUDIT_JSON}}", html)

    def test_missing_fix_is_named(self):
        bad = copy.deepcopy(VALID)
        del bad["issues"][0]["fix"]
        p, html = build(bad)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("issues[0].fix", p.stderr)
        self.assertIsNone(html)

    def test_fewer_than_three_runs_rejected_unless_predict_only(self):
        bad = copy.deepcopy(VALID)
        bad["numbers"]["runs"] = 1
        p, _ = build(bad)
        self.assertIn("numbers.runs", p.stderr)
        ok = copy.deepcopy(VALID)
        ok.update(predictOnly=True)
        ok["numbers"].update(actual=None, runs=0)
        self.assertEqual(build(ok)[0].returncode, 0)

    def test_script_close_tag_is_escaped(self):
        data = copy.deepcopy(VALID)
        data["issues"][0]["fix"] = "Remove </script><script>alert(1)</script> from the prompt"
        p, html = build(data)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("</script><script>alert(1)", html)

    def test_issues_are_ranked_by_waste(self):
        data = copy.deepcopy(VALID)
        small = dict(data["issues"][0], id="small", tokensWasted=10)
        data["issues"].insert(0, small)
        p, html = build(data)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertLess(html.index('"huge-tool-result"'), html.index('"small"'))


if __name__ == "__main__":
    unittest.main()
