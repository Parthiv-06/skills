"""Logging proxy between an agent and the LLM API. Records real token usage per call; changes nothing.

Usage:
  python3 usage_proxy.py --provider anthropic|openai --trace run1.jsonl [--port 8788]
                         [--upstream URL] [--budget TOKENS]
Then run the agent with its base URL pointed here:
  ANTHROPIC_BASE_URL=http://127.0.0.1:8788      (Anthropic SDKs)
  OPENAI_BASE_URL=http://127.0.0.1:8788/v1      (OpenAI SDKs)

One JSON line per model call: usage exactly as the API reported it, plus estimated block sizes
(system, tools, history, current, tool_results, media), tool calls, and hashes for detectors.
API keys and message content are never written. Streaming (SSE) is passed through as it arrives.
--budget refuses calls once this many tokens (input + cache + output) have been spent, with
HTTP 400 so SDKs do not retry. For OpenAI streams it adds stream_options.include_usage so the
final chunk carries usage.
"""
import hashlib
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = {"anthropic": "https://api.anthropic.com", "openai": "https://api.openai.com"}
BIG_BLOCK = 500  # estimated tokens; smaller blocks are not tracked individually
SKIP_REQ = {"host", "content-length", "accept-encoding", "connection"}
SKIP_RESP = {"content-length", "transfer-encoding", "connection", "content-encoding"}
FLAGS = {
    "traceback": re.compile(r"Traceback \(most recent call last\)|\n\s+at \S+ \(\S+:\d+:\d+\)"),
    "object_repr": re.compile(r"<[\w.]+ object at 0x[0-9a-f]+>"),
}


def est(obj):
    if obj is None:
        return 0
    return round(len(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)) / 4)


def digest(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def args_hash(args):
    return digest(args if args is not None else {})


def _text_of(block):
    if isinstance(block, str):
        return block
    c = block.get("text") or block.get("content") or ""
    return c if isinstance(c, str) else " ".join(_text_of(x) for x in c)


def _parts(content):
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content or []


# ---------- request analysis ----------

def analyze_request(provider, body):
    sizes = {"system": 0, "tools": 0, "history": 0, "current": 0, "tool_results": 0, "media": 0}
    big = []

    def track(block, source):
        n = est(block)
        if n >= BIG_BLOCK:
            text = _text_of(block)
            big.append({"hash": digest(block if source == "media" else text), "source": source, "tokens": n,
                        "flags": [k for k, rx in FLAGS.items() if rx.search(text)]})
        return n

    msgs = body.get("messages") or []
    tools = body.get("tools") or []
    if provider == "anthropic":
        system = body.get("system")
        tool_names = [t.get("name") for t in tools]
    else:
        if "input" in body and "messages" not in body:  # OpenAI Responses API
            inp = body["input"]
            msgs = [{"role": "user", "content": inp}] if isinstance(inp, str) else [
                {"role": "tool", "content": m.get("output")} if m.get("type") == "function_call_output"
                else {"role": "assistant", "content": [], "tool_calls": [m]} if m.get("type") == "function_call"
                else m for m in inp]
        system = ([{"role": "system", "content": body["instructions"]}] if body.get("instructions") else []) + \
            [m for m in msgs if m.get("role") in ("system", "developer")]
        msgs = [m for m in msgs if m.get("role") not in ("system", "developer")]
        tool_names = [(t.get("function") or t).get("name") for t in tools]
    sizes["system"], sizes["tools"] = est(system), est(tools)

    for i, m in enumerate(msgs):
        last = i == len(msgs) - 1
        if provider == "openai" and m.get("role") == "tool":
            sizes["tool_results" if last else "history"] += track(m, "tool_result")
            continue
        for b in _parts(m.get("content")):
            kind = b.get("type")
            if kind in ("image", "document", "image_url", "input_image", "file"):
                sizes["media"] += track(b, "media")
            elif kind == "tool_result":
                sizes["tool_results" if last else "history"] += track(b, "tool_result")
            else:
                sizes["current" if last else "history"] += track(b, "text")
        if provider == "openai" and m.get("tool_calls"):
            sizes["current" if last else "history"] += est(m["tool_calls"])

    hashes = [b["hash"] for b in big]
    thinking = body.get("thinking") or {}
    return {
        "model": body.get("model"),
        "stream": bool(body.get("stream")),
        "max_tokens": body.get("max_tokens") or body.get("max_completion_tokens"),
        "thinking_budget": thinking.get("budget_tokens"),
        "blocks": sizes,
        "tool_names": tool_names,
        "request_hash": digest(body),
        "prefix_hash": digest({"system": system, "tools": tools}),
        "big_blocks": big,
        "dup_in_call": sorted({h for h in hashes if hashes.count(h) > 1}),
    }


# ---------- response parsing ----------

def _usage_anthropic(u):
    return {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
            "cache_write": u.get("cache_creation_input_tokens") or 0,
            "cache_read": u.get("cache_read_input_tokens") or 0, "reasoning": None}


def _usage_openai(u):
    """Chat Completions (prompt_/completion_tokens) and Responses API (input_/output_tokens). Input includes cached."""
    chat = "prompt_tokens" in u
    cached = (u.get("prompt_tokens_details" if chat else "input_tokens_details") or {}).get("cached_tokens") or 0
    return {"input": u.get("prompt_tokens" if chat else "input_tokens", 0) - cached,
            "output": u.get("completion_tokens" if chat else "output_tokens", 0),
            "cache_write": 0, "cache_read": cached,
            "reasoning": (u.get("completion_tokens_details" if chat else "output_tokens_details") or {}).get("reasoning_tokens")}


def _loads(raw):
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return raw


def parse_response(provider, data):
    if provider == "anthropic":
        calls = [{"name": b["name"], "args_hash": args_hash(b.get("input"))}
                 for b in data.get("content", []) if b.get("type") == "tool_use"]
        u = data.get("usage")
        return (_usage_anthropic(u) if u else None), data.get("stop_reason"), calls
    if "output" in data and "choices" not in data:  # Responses API
        calls = [{"name": o.get("name"), "args_hash": args_hash(_loads(o.get("arguments")))}
                 for o in data.get("output") or [] if o.get("type") == "function_call"]
        u = data.get("usage")
        return (_usage_openai(u) if u else None), data.get("status"), calls
    choice = (data.get("choices") or [{}])[0]
    calls = []
    for tc in (choice.get("message") or {}).get("tool_calls") or []:
        f = tc.get("function", {})
        try:
            a = json.loads(f.get("arguments") or "{}")
        except ValueError:
            a = f.get("arguments")
        calls.append({"name": f.get("name"), "args_hash": args_hash(a)})
    u = data.get("usage")
    return (_usage_openai(u) if u else None), choice.get("finish_reason"), calls


class StreamState:
    """Accumulates usage, stop reason, and tool calls from SSE events as they pass through."""

    def __init__(self, provider):
        self.provider, self.usage, self.stop = provider, None, None
        self.tools = {}  # index -> [name, partial_json]

    def feed(self, line):
        if not line.startswith("data:"):
            return
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            return
        try:
            ev = json.loads(payload)
        except ValueError:
            return
        if self.provider == "anthropic":
            t = ev.get("type")
            if t == "message_start":
                self.usage = _usage_anthropic(ev["message"].get("usage") or {})
            elif t == "content_block_start" and ev["content_block"].get("type") == "tool_use":
                self.tools[ev["index"]] = [ev["content_block"]["name"], ""]
            elif t == "content_block_delta" and ev["delta"].get("type") == "input_json_delta":
                self.tools[ev["index"]][1] += ev["delta"].get("partial_json", "")
            elif t == "message_delta":
                self.stop = (ev.get("delta") or {}).get("stop_reason") or self.stop
                later = _usage_anthropic(ev.get("usage") or {})
                self.usage = self.usage or later
                self.usage["output"] = later["output"] or self.usage["output"]
                for k in ("input", "cache_write", "cache_read"):
                    if (ev.get("usage") or {}).get({"input": "input_tokens", "cache_write": "cache_creation_input_tokens",
                                                    "cache_read": "cache_read_input_tokens"}[k]) is not None:
                        self.usage[k] = later[k]
        elif str(ev.get("type", "")).startswith("response."):  # Responses API stream
            if ev["type"] == "response.completed":
                r = ev.get("response") or {}
                self.stop = r.get("status")
                if r.get("usage"):
                    self.usage = _usage_openai(r["usage"])
                for o in r.get("output") or []:
                    if o.get("type") == "function_call":
                        self.tools[len(self.tools)] = [o.get("name"), o.get("arguments") or ""]
        else:
            for ch in ev.get("choices") or []:
                self.stop = ch.get("finish_reason") or self.stop
                for tc in (ch.get("delta") or {}).get("tool_calls") or []:
                    slot = self.tools.setdefault(tc.get("index", 0), ["", ""])
                    f = tc.get("function") or {}
                    slot[0] = f.get("name") or slot[0]
                    slot[1] += f.get("arguments") or ""
            if ev.get("usage"):
                self.usage = _usage_openai(ev["usage"])

    def calls(self):
        out = []
        for _, (name, raw) in sorted(self.tools.items()):
            try:
                a = json.loads(raw or "{}")
            except ValueError:
                a = raw
            out.append({"name": name, "args_hash": args_hash(a)})
        return out


# ---------- server ----------

class Recorder:
    def __init__(self, path, budget):
        self.path, self.budget, self.spent, self.n = path, budget, 0, 0
        self.lock = threading.Lock()

    def over_budget(self):
        return self.budget and self.spent >= self.budget

    def write(self, rec):
        with self.lock:
            self.n += 1
            rec["call"] = self.n
            u = rec.get("usage")
            if u:
                self.spent += u["input"] + u["output"] + u["cache_write"] + u["cache_read"]
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")


def make_handler(provider, upstream, rec):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _forward(self, data):
            headers = {k: v for k, v in self.headers.items() if k.lower() not in SKIP_REQ}
            headers["Accept-Encoding"] = "identity"
            req = urllib.request.Request(upstream.rstrip("/") + self.path, data=data, headers=headers, method=self.command)
            try:
                return urllib.request.urlopen(req, timeout=600)
            except urllib.error.HTTPError as e:
                return e

        def _send_head(self, resp, length=None):
            self.send_response(resp.status if hasattr(resp, "status") else resp.code)
            for k, v in resp.headers.items():
                if k.lower() not in SKIP_RESP:
                    self.send_header(k, v)
            if length is not None:
                self.send_header("Content-Length", str(length))
            else:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()

        def do_GET(self):
            resp = self._forward(None)
            data = resp.read()
            self._send_head(resp, len(data))
            self.wfile.write(data)

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("content-length") or 0))
            try:
                body = json.loads(raw)
            except ValueError:
                body = None
            if not isinstance(body, dict) or not ("messages" in body or "input" in body):
                resp = self._forward(raw)  # not a model call (e.g. count_tokens is still a POST, but fine to pass)
                data = resp.read()
                self._send_head(resp, len(data))
                self.wfile.write(data)
                return

            info = analyze_request(provider, body)
            base = {"ts": round(time.time(), 3), "provider": provider, "path": self.path.split("?")[0], **info}
            if rec.over_budget():
                rec.write({**base, "status": 400, "blocked": True, "latency_ms": 0, "usage": None,
                           "stop_reason": None, "tool_calls": []})
                msg = json.dumps({"type": "error", "error": {"type": "budget_exceeded",
                                  "message": f"usage_proxy budget of {rec.budget} tokens reached"}}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                return

            if provider == "openai" and body.get("stream") and "messages" in body:  # Responses streams carry usage already
                body.setdefault("stream_options", {})["include_usage"] = True
                raw = json.dumps(body).encode()
            t0 = time.time()
            resp = self._forward(raw)
            status = resp.status if hasattr(resp, "status") else resp.code
            ctype = resp.headers.get("Content-Type", "")
            if "event-stream" in ctype:
                self._send_head(resp)
                st = StreamState(provider)
                for line in iter(resp.readline, b""):
                    self.wfile.write(line)
                    self.wfile.flush()
                    st.feed(line.decode("utf-8", "replace").rstrip("\r\n"))
                # The connection closes after this handler returns, so the record lands before the client sees EOF.
                rec.write({**base, "status": status, "blocked": False, "latency_ms": round((time.time() - t0) * 1000),
                           "usage": st.usage, "stop_reason": st.stop, "tool_calls": st.calls()})
            else:
                data = resp.read()
                usage, stop, calls = None, None, []
                if status < 400:
                    try:
                        usage, stop, calls = parse_response(provider, json.loads(data))
                    except ValueError:
                        pass
                # Record before replying, so the trace is complete by the time the agent continues.
                rec.write({**base, "status": status, "blocked": False, "latency_ms": round((time.time() - t0) * 1000),
                           "usage": usage, "stop_reason": stop, "tool_calls": calls})
                self._send_head(resp, len(data))
                self.wfile.write(data)

    return Handler


def serve(provider, upstream, port, trace, budget=0, host="127.0.0.1"):
    """Start the proxy in a background thread. Returns the server (port: server.server_address[1])."""
    server = ThreadingHTTPServer((host, port), make_handler(provider, upstream, Recorder(trace, budget)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(argv):
    args = dict(zip(argv[::2], argv[1::2]))
    provider = args.get("--provider")
    if provider not in UPSTREAM or "--trace" not in args:
        sys.exit(__doc__)
    s = serve(provider, args.get("--upstream", UPSTREAM[provider]), int(args.get("--port", 8788)),
              args["--trace"], int(args.get("--budget", 0)))
    print(f"usage_proxy: {provider} -> {args.get('--upstream', UPSTREAM[provider])} on http://127.0.0.1:{s.server_address[1]}, "
          f"trace {args['--trace']}" + (f", budget {args['--budget']} tokens" if args.get("--budget") else ""), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        s.shutdown()


if __name__ == "__main__":
    main(sys.argv[1:])
