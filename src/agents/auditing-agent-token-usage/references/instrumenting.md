# Instrumenting an agent

The proxy needs no code changes when the agent's base URL can be redirected. Start it, point the agent at it, and run.

| Stack | Point it at the proxy |
|---|---|
| Anthropic SDK (Python, TypeScript) | `ANTHROPIC_BASE_URL=http://127.0.0.1:8788` (the SDKs read it), or `Anthropic(base_url=...)` |
| OpenAI SDK (Python, TypeScript) | `OPENAI_BASE_URL=http://127.0.0.1:8788/v1`, or `OpenAI(base_url=...)`. Chat Completions and the Responses API are both parsed |
| AI SDK (`@ai-sdk/anthropic`, `@ai-sdk/openai`) | `createAnthropic({ baseURL: "http://127.0.0.1:8788/v1" })`, `createOpenAI({ baseURL: "http://127.0.0.1:8788/v1" })` |
| LangChain | `ChatAnthropic(base_url=...)`, `ChatOpenAI(base_url=...)` |
| Raw HTTP | Change the host in the request URL |

The proxy forwards to `https://api.anthropic.com` or `https://api.openai.com` unless you pass `--upstream`. For an OpenAI-compatible server, pass its URL as `--upstream` with `--provider openai`.

## When the proxy cannot sit in the path

AWS Bedrock and Google Vertex sign each request, and AI gateways (Vercel AI Gateway, OpenRouter, LiteLLM) may hide the provider. In those cases, log usage from inside the code, writing the same fields the proxy writes so `analyze_trace.py` still works.

Python, Anthropic SDK:
```python
import json, time
_create = client.messages.create
def logged_create(**kw):
    r = _create(**kw)
    u = r.usage
    with open("audit/traces/run1.jsonl", "a") as f:
        f.write(json.dumps({"call": logged_create.n, "ts": time.time(), "status": 200, "model": kw.get("model"),
            "usage": {"input": u.input_tokens, "output": u.output_tokens,
                      "cache_write": u.cache_creation_input_tokens or 0, "cache_read": u.cache_read_input_tokens or 0, "reasoning": None},
            "stop_reason": r.stop_reason,
            "tool_calls": [{"name": b.name, "args_hash": usage_proxy.args_hash(b.input)} for b in r.content if b.type == "tool_use"],
            **usage_proxy.analyze_request("anthropic", kw)}) + "\n")   # import usage_proxy from this skill's scripts/
    logged_create.n += 1
    return r
logged_create.n = 1
client.messages.create = logged_create
```

AI SDK: read `usage` (and `providerMetadata` for cache tokens) from each `generateText` or `streamText` result, or from `onStepFinish`. OpenTelemetry: the AI SDK and many frameworks emit spans with token counts (`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`). Export them and convert each span into one trace line.

Instrumentation in code is temporary. Remove it after the audit, or keep it behind a flag if the user asks.

## Exact counts without running

`count_tokens.py --request body.json` posts a full request body to the Anthropic `count_tokens` endpoint (needs `ANTHROPIC_API_KEY`; free and rate-limited). It counts system prompt, tools, and messages exactly. For OpenAI, install `tiktoken` and count text with `count_tokens.py FILE --provider openai --model <model>`. Both fall back to chars/4, labeled `estimated:chars/4`.
