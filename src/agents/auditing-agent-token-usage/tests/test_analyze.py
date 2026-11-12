import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import analyze_trace  # noqa: E402
import harness  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "..", "..", "..", "test", "example-token-audit")
PLANTED = {"history-growth", "huge-tool-result", "no-cache", "repeated-tool-call", "retry-storm", "verbose-output"}


class AnalyzeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.wasteful = analyze_trace.analyze(harness.run(os.path.join(EXAMPLE, "wasteful_agent.py"), 3, cls.tmp))
        cls.clean = analyze_trace.analyze(harness.run(os.path.join(EXAMPLE, "clean_agent.py"), 3, cls.tmp))

    def test_finds_every_planted_issue(self):
        ids = {f["id"] for f in self.wasteful["findings"]}
        self.assertTrue(PLANTED <= ids, f"missing {PLANTED - ids}")

    def test_finds_nothing_that_was_not_planted(self):
        ids = {f["id"] for f in self.wasteful["findings"]}
        # unstable-prefix is part of planted issue 3 (the timestamp in the system prompt).
        self.assertEqual(ids - PLANTED, {"unstable-prefix"})

    def test_clean_agent_has_no_high_findings(self):
        high = [f["id"] for f in self.clean["findings"] if f["severity"] == "high"]
        self.assertEqual(high, [])

    def test_clean_agent_uses_far_fewer_tokens(self):
        self.assertLess(self.clean["tokens"]["total"]["median"] * 10, self.wasteful["tokens"]["total"]["median"])

    def test_attribution_matches_measured_input(self):
        a = self.wasteful["attribution"]
        measured = sum(c["input"] + c["cache_read"] + c["cache_write"] for c in self.wasteful["per_call"])
        self.assertAlmostEqual(sum(v for k, v in a.items() if k != "output"), measured, delta=len(self.wasteful["per_call"]))

    def test_empty_and_single_call_traces(self):
        self.assertEqual(analyze_trace.analyze([])["runs"], 0)
        path = os.path.join(self.tmp, "one.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"call": 1, "status": 200, "request_hash": "a", "prefix_hash": "p", "model": "m",
                                "usage": {"input": 10, "output": 5, "cache_write": 0, "cache_read": 0, "reasoning": None},
                                "blocks": {"system": 5, "tools": 0, "history": 0, "current": 5, "tool_results": 0, "media": 0},
                                "big_blocks": [], "tool_calls": [], "stop_reason": "end_turn"}) + "\n")
        out = analyze_trace.analyze([path])
        self.assertEqual((out["runs"], out["findings"]), (1, []))


if __name__ == "__main__":
    unittest.main()
