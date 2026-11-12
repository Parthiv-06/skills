# Issue catalog

Each entry gives the analyzer id (or "code only"), how to confirm it in the code, the usual fix, and the fix's risk. "Risk: behavior" means the model will see different information, so the fix must be verified (re-run the task and compare answers).

| id | What it is | Confirm in code | Usual fix | Risk |
|---|---|---|---|---|
| `history-growth` | Every turn resends all earlier turns | A messages list that is only appended to | Stub old tool results after use; summarize old turns past N; cache the history prefix | behavior |
| `huge-tool-result` | One tool result is thousands of tokens and stays in context | A tool returns a raw file, page, API JSON, or logs with no limit | Filter at the source (only needed fields or rows); cap length with a "truncated, N total" note; paginate; return IDs and let the model fetch details | behavior (safe if the dropped part is provably unused) |
| `no-cache` | Nothing is read from the prompt cache | No `cache_control` (Anthropic). For OpenAI, a prefix under 1,024 tokens or one that varies | Mark the system prompt, tools, and last message for caching; keep the prefix byte-identical | safe |
| `cache-broken` | The cache is written but rarely read | Cache markers present, but something in the prefix changes | Find what changes (see `unstable-prefix`); move volatile parts after the cached prefix | safe |
| `unstable-prefix` | The system prompt or tools differ between calls or runs at the same size | Timestamps, request IDs, random examples, unsorted tool lists, user data in the system prompt | Move volatile text into the latest user message; sort tools; freeze examples | safe |
| `repeated-tool-call` | The model calls the same tool with the same arguments again | No dedupe in the tool runner | Answer repeats with "same result as above"; add a turn limit | behavior |
| `retry-storm` | The same request is sent back to back | Retry on parse or validation errors that replays the full request; a retry without backoff on 5xx | Small repair call with only the bad output; structured outputs or tool-forced JSON; retry only transport errors, with backoff | behavior |
| `duplicate-call` | An identical request is made twice, not back to back | Double invocation: a React effect running twice, stream plus non-stream, cache miss races, missing memoization | Deduplicate at the call site; memoize by request hash | safe |
| `per-item-calls` | One model call per item, each paying the full prompt | A loop over items calling the model | Batch items into one call; use a smaller model for simple per-item work; a batch API for offline work | behavior |
| `tool-schema-bloat` | Large tool definitions sent on every call, most never used | Dozens of tools or long descriptions always attached | Send only the tools for the current step; shorten descriptions; tool search or dynamic loading | behavior |
| `system-prompt-bloat` | A long system prompt on every call | — | Run the compressing-agent-prompts skill; cache it | behavior |
| `overthinking` | High reasoning or thinking use for the task | Large thinking budget or high reasoning effort on simple steps | Lower the budget or effort per step; no thinking on routing or formatting calls | behavior |
| `verbose-output` | Answers far longer than needed | "Explain in detail", no format, a high `max_tokens` | Ask for the shape needed; set `max_tokens` close to it; structured output | behavior |
| `context-duplication` | The same large block is passed to several agents | Each subagent receives the full parent context | Pass each subagent only its slice; share by reference (file path, ID) | behavior |
| `media-resent` | An image or file is sent in many calls | Base64 media kept in history | Drop media from history after it has been described; use file IDs where the API supports them | behavior |
| `debug-in-context` | Stack traces or object dumps sent to the model | `str(exception)`, `repr(obj)`, or full error objects in tool results | Send a one-line error and an error code | safe |
| `runaway` | The run hit the budget cap or a very high call count | `while True` with no turn limit; a stop condition that never fires | Turn limit, a no-progress detector, stop on repeated identical calls | safe |
| code only: RAG over-fetch | Retrieved context much larger than needed | High `top_k`, big chunks, duplicate chunks, no reranking | Lower `top_k`; rerank; dedupe; smaller chunks | behavior |
| code only: overkill model | The top model on trivial steps | Routing, classification, or extraction on the largest model | A small model for those steps | behavior |
| code only: wasted `max_tokens` on truncation | Answers cut at `max_tokens`, then regenerated | `stop_reason == "max_tokens"` followed by a retry | Raise the limit for that step or ask for a shorter shape | behavior |

## Working out the real waste

`tokens_involved` is the size of the pattern. The waste is what a fixed version would not spend:

- **Large block carried in k calls:** (block size − size after the fix) × k.
- **Retries:** total tokens of the retry calls − the cost of the replacement (for example, a repair call).
- **Caching:** cacheable tokens × (1 − cache-read price ÷ input price). Say it is in full-price-equivalent tokens.
- **Several fixes together:** do not add them. Measure the fixed version, or model it as one fixed run.
