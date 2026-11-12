"""A fake Anthropic Messages API for tests and the worked example. No network, no key.

It plays a scripted model for the example's bug-triage task:
  read_file("bugs.json") -> search_logs("timeout") (repeated until 3 results, or until the
  agent answers "Duplicate ...") -> final answer.
The final answer is prose (not JSON) for the first two identical requests, then JSON, which is
what makes a retry storm visible. A user message containing "Convert to JSON" gets JSON at once.
The answer is long if the system prompt asks for detail.

Usage is computed from the request (chars / 4), with prompt caching simulated: a request that
marks cache_control and repeats a seen system+tools prefix is billed as cache_read.
Model "fail-500" returns HTTP 500.

Run standalone: python3 fake_api.py [PORT]
"""
import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def est(obj):
    return round(len(obj if isinstance(obj, str) else json.dumps(obj)) / 4)


def blocks(content):
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


LONG_ANSWER = ("Here is a detailed summary of every open bug, grouped by component, with background, "
               "reproduction notes, impact analysis, and a recommended next step for each one. ") * 30


class FakeAPI(BaseHTTPRequestHandler):
    seen_prefixes = set()
    seen_requests = {}
    lock = threading.Lock()

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if body.get("model") == "fail-500":
            data = b'{"type":"error","error":{"type":"api_error","message":"boom"}}'
            self.send_response(500)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        content, stop = self.decide(body)
        usage = self.usage(body, content)
        if body.get("stream"):
            self.stream(body, content, stop, usage)
            return
        data = json.dumps({"id": "msg_fake", "type": "message", "role": "assistant", "model": body["model"],
                           "content": content, "stop_reason": stop, "usage": usage}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def decide(self, body):
        msgs = body.get("messages", [])
        last = msgs[-1] if msgs else {"content": ""}
        last_text = " ".join(b.get("text", "") for b in blocks(last["content"]) if b.get("type") == "text")
        if "Convert to JSON" in last_text:
            return [{"type": "text", "text": '{"summary": "3 open bugs, all caused by the DB timeout"}'}], "end_turn"

        names, results = {}, []
        for m in msgs:
            for b in blocks(m["content"]):
                if b.get("type") == "tool_use":
                    names[b["id"]] = b["name"]
                elif b.get("type") == "tool_result":
                    c = b.get("content")
                    text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [])
                    results.append((names.get(b["tool_use_id"]), text))
        n = sum(1 for m in msgs for b in blocks(m["content"]) if b.get("type") == "tool_use")
        if not any(name == "read_file" for name, _ in results):
            return [{"type": "tool_use", "id": f"toolu_{n}", "name": "read_file", "input": {"path": "bugs.json"}}], "tool_use"
        searches = [t for name, t in results if name == "search_logs"]
        if not searches or (len(searches) < 3 and not searches[-1].startswith("Duplicate")):
            return [{"type": "tool_use", "id": f"toolu_{n}", "name": "search_logs", "input": {"query": "timeout"}}], "tool_use"

        key = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with self.lock:
            self.seen_requests[key] = self.seen_requests.get(key, 0) + 1
            attempt = self.seen_requests[key]
        system = json.dumps(body.get("system", ""))
        prose = LONG_ANSWER if "in detail" in system else "Three open bugs, all caused by the DB timeout."
        if attempt < 3:
            return [{"type": "text", "text": prose}], "end_turn"
        return [{"type": "text", "text": json.dumps({"summary": prose})}], "end_turn"

    def usage(self, body, content):
        prefix = {"system": body.get("system"), "tools": body.get("tools")}
        p, rest = est(prefix), est(body.get("messages", []))
        u = {"input_tokens": p + rest, "output_tokens": est(content),
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        if "cache_control" in json.dumps(prefix):
            h = hashlib.sha1(json.dumps(prefix, sort_keys=True).encode()).hexdigest()
            with self.lock:
                hit = h in self.seen_prefixes
                self.seen_prefixes.add(h)
            u["input_tokens"] = rest
            u["cache_read_input_tokens" if hit else "cache_creation_input_tokens"] = p
        return u

    def stream(self, body, content, stop, usage):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()

        def ev(kind, data):
            data["type"] = kind
            self.wfile.write(f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()

        start_usage = dict(usage, output_tokens=1)
        ev("message_start", {"message": {"id": "msg_fake", "type": "message", "role": "assistant", "model": body["model"],
                                         "content": [], "stop_reason": None, "usage": start_usage}})
        for i, b in enumerate(content):
            if b["type"] == "text":
                ev("content_block_start", {"index": i, "content_block": {"type": "text", "text": ""}})
                ev("content_block_delta", {"index": i, "delta": {"type": "text_delta", "text": b["text"]}})
            else:
                ev("content_block_start", {"index": i, "content_block": {"type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}})
                raw = json.dumps(b["input"])
                for part in (raw[: len(raw) // 2], raw[len(raw) // 2:]):
                    ev("content_block_delta", {"index": i, "delta": {"type": "input_json_delta", "partial_json": part}})
            ev("content_block_stop", {"index": i})
        ev("message_delta", {"delta": {"stop_reason": stop}, "usage": {"output_tokens": usage["output_tokens"]}})
        ev("message_stop", {})


def serve(port=0):
    """Start the fake API in a background thread. Returns the server; its port is server.server_address[1]."""
    FakeAPI.seen_prefixes = set()
    FakeAPI.seen_requests = {}
    server = ThreadingHTTPServer(("127.0.0.1", port), FakeAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    s = serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8790)
    print(f"fake API on http://127.0.0.1:{s.server_address[1]}")
    threading.Event().wait()
