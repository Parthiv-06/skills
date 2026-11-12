import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import fake_api  # noqa: E402
import usage_proxy  # noqa: E402

SECRET = "sk-ant-secret-should-never-be-logged"


def post(port, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/messages", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "x-api-key": SECRET,
                                          "anthropic-version": "2023-06-01"})
    return urllib.request.urlopen(req, timeout=10)


def body(**kw):
    b = {"model": "claude-test", "max_tokens": 100, "system": "You triage bugs.",
         "tools": [{"name": "read_file", "description": "Read a file", "input_schema": {"type": "object"}}],
         "messages": [{"role": "user", "content": "Summarize the open bugs."}]}
    b.update(kw)
    return b


class ProxyTest(unittest.TestCase):
    def setUp(self):
        self.api = fake_api.serve()
        self.trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name
        self.proxy = None

    def start(self, budget=0):
        self.proxy = usage_proxy.serve("anthropic", f"http://127.0.0.1:{self.api.server_address[1]}", 0, self.trace, budget)
        return self.proxy.server_address[1]

    def tearDown(self):
        for s in (self.api, self.proxy):
            if s:
                s.shutdown()
                s.server_close()
        os.unlink(self.trace)

    def records(self):
        with open(self.trace) as f:
            return [json.loads(line) for line in f]

    def test_non_stream_usage_matches_api(self):
        port = self.start()
        resp = json.load(post(port, body()))
        [rec] = self.records()
        u = resp["usage"]
        self.assertEqual(rec["usage"], {"input": u["input_tokens"], "output": u["output_tokens"],
                                        "cache_write": 0, "cache_read": 0, "reasoning": None})
        self.assertEqual(rec["tool_calls"][0]["name"], "read_file")
        self.assertEqual(rec["tool_names"], ["read_file"])
        self.assertEqual(rec["status"], 200)

    def test_stream_usage_matches_sse(self):
        port = self.start()
        raw = post(port, body(stream=True)).read().decode()
        events = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ")]
        start = next(e for e in events if e["type"] == "message_start")["message"]["usage"]
        delta = next(e for e in events if e["type"] == "message_delta")["usage"]
        [rec] = self.records()
        self.assertTrue(rec["stream"])
        self.assertEqual(rec["usage"]["input"], start["input_tokens"])
        self.assertEqual(rec["usage"]["output"], delta["output_tokens"])
        self.assertEqual(rec["tool_calls"][0]["name"], "read_file")
        self.assertEqual(rec["tool_calls"][0]["args_hash"], usage_proxy.args_hash({"path": "bugs.json"}))

    def test_upstream_error_passes_through(self):
        port = self.start()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            post(port, body(model="fail-500"))
        self.assertEqual(cm.exception.code, 500)
        [rec] = self.records()
        self.assertEqual(rec["status"], 500)
        self.assertIsNone(rec["usage"])

    def test_budget_cap_blocks_with_400(self):
        port = self.start(budget=1)
        post(port, body())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            post(port, body())
        self.assertEqual(cm.exception.code, 400)
        recs = self.records()
        self.assertEqual([r["blocked"] for r in recs], [False, True])

    def test_api_key_never_written(self):
        port = self.start()
        post(port, body())
        post(port, body(stream=True)).read()
        with open(self.trace) as f:
            self.assertNotIn(SECRET, f.read())


class OpenAIParsingTest(unittest.TestCase):
    def test_chat_completions_usage_and_tools(self):
        usage, stop, calls = usage_proxy.parse_response("openai", {
            "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
                {"function": {"name": "search", "arguments": '{"q": "x"}'}}]}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 50, "prompt_tokens_details": {"cached_tokens": 800},
                      "completion_tokens_details": {"reasoning_tokens": 20}}})
        self.assertEqual(usage, {"input": 200, "output": 50, "cache_write": 0, "cache_read": 800, "reasoning": 20})
        self.assertEqual((stop, calls[0]["name"], calls[0]["args_hash"]), ("tool_calls", "search", usage_proxy.args_hash({"q": "x"})))

    def test_responses_api_usage_tools_and_blocks(self):
        usage, stop, calls = usage_proxy.parse_response("openai", {
            "status": "completed", "output": [{"type": "function_call", "name": "search", "arguments": '{"q": "x"}'}],
            "usage": {"input_tokens": 900, "output_tokens": 40, "input_tokens_details": {"cached_tokens": 600},
                      "output_tokens_details": {"reasoning_tokens": 10}}})
        self.assertEqual(usage, {"input": 300, "output": 40, "cache_write": 0, "cache_read": 600, "reasoning": 10})
        self.assertEqual(calls[0]["name"], "search")
        info = usage_proxy.analyze_request("openai", {"model": "m", "instructions": "Be brief.", "input": [
            {"role": "user", "content": "hi"}, {"type": "function_call", "name": "search", "arguments": "{}"},
            {"type": "function_call_output", "output": "result " * 50}]})
        self.assertGreater(info["blocks"]["system"], 0)
        self.assertGreater(info["blocks"]["tool_results"], 0)
        self.assertGreater(info["blocks"]["history"], 0)

    def test_responses_stream_completed_event(self):
        st = usage_proxy.StreamState("openai")
        st.feed('data: ' + json.dumps({"type": "response.completed", "response": {"status": "completed",
                "output": [], "usage": {"input_tokens": 10, "output_tokens": 5}}}))
        self.assertEqual((st.usage["input"], st.usage["output"], st.stop), (10, 5, "completed"))


if __name__ == "__main__":
    unittest.main()
