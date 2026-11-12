# auditing-agent-token-usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A skill that predicts, measures, and diagnoses an LLM agent's token use, and reports it as an Apple-style page.

**Architecture:** Four stdlib Python scripts: a token counter, a logging proxy that sits between the agent and the API, a trace analyzer with detectors, and a report builder. The skill text tells the coding agent how to combine them with its own reading of the code. A fake Anthropic API and two fixture agents (one wasteful, one clean) make everything testable without keys.

**Tech Stack:** Python 3 standard library only (`tiktoken` / Anthropic API used if available). Report: one HTML template with rough.js, matching `src/general/demoing-features/assets/demo-template.html`.

**Spec:** `docs/superpowers/specs/2026-11-12-auditing-agent-token-usage-design.md`

## Global Constraints
- Every number carries a label: `measured`, `counted`, or `estimated`.
- No API key or message content is written to disk by the proxy. It stores only sizes, hashes, tool names, and detector flags.
- The proxy enforces a hard budget cap and refuses calls past it with HTTP 400 (not 429, so SDKs don't retry).
- At least 3 runs per task. Report the median run and the min–max range.
- The report uses the demo template's look: white only, SF Pro, `#f5f5f7` tiles, 28px corners, `#0071e3` pills, `#bf4800` eyebrows, gradient used sparingly.

## Review Focus
1. Streaming (SSE) responses: usage must still be captured exactly. Covered by the proxy stream test.
2. Upstream errors (4xx/5xx) pass through unchanged and are recorded. Covered by the proxy error test.
3. A trace with 1 call, or with 0 runs, must not crash the analyzer. Covered by the analyzer edge test.
4. The clean agent must not trigger high-severity detectors (false alarms). Covered by the analyzer clean test.
5. Report JSON with a `</script>` string or missing fields fails loudly or is escaped. Covered by the builder tests.

---

## Trace record (one JSON line per model call, written by the proxy)
`call, ts, provider, path, model, status, latency_ms, stream, blocked,
usage{input, output, cache_write, cache_read, reasoning} | null,
stop_reason, max_tokens, thinking_budget,
blocks{system, tools, history, current, tool_results, media}` (estimated tokens),
`tool_names[]` (defined), `tool_calls[{name, args_hash}]` (made),
`request_hash, prefix_hash, big_blocks[{hash, source, tokens, flags[]}]` (blocks ≥ 500 est. tokens; flags: `traceback`, `object_repr`),
`dup_in_call` (big-block hashes repeated inside one request).

### Task 1: count_tokens.py
**Files:** create `src/agents/auditing-agent-token-usage/scripts/count_tokens.py`; test `.../tests/test_count_tokens.py`
**Produces:** `count(text: str, provider="anthropic", model=None) -> (int, str)`, where the method is `counted:anthropic-api` | `counted:tiktoken` | `estimated:chars/4`. CLI: `count_tokens.py FILE [--provider P] [--model M]` prints JSON `{tokens, method}`.
- [ ] Test: with no key and no tiktoken, `count("abcd"*100)` → `(100, "estimated:chars/4")`
- [ ] Implement: use the Anthropic `count_tokens` API if `ANTHROPIC_API_KEY` is set (subtract the count of a 1-char message), else `tiktoken` for openai, else chars/4
- [ ] Run the tests

### Task 2: fake API + usage_proxy.py
**Files:** create `scripts/usage_proxy.py`, `tests/fake_api.py`, `tests/test_proxy.py`
**Produces:** `usage_proxy.py --provider anthropic|openai --upstream URL --port N --trace FILE --budget TOKENS`. `fake_api.serve(port) -> server` speaks Anthropic Messages (stream and non-stream) and reports usage computed from the request.
- [ ] Tests: the non-stream usage in the trace equals the fake API's response usage; the stream usage equals the usage from the SSE events; a 500 from upstream passes through with `status: 500`; past the budget, status 400 and `blocked: true`; the trace file never contains the `x-api-key` value
- [ ] Implement the proxy: a `ThreadingHTTPServer` that forwards with `Accept-Encoding: identity`, streams the body through as it arrives, parses SSE, and writes one JSONL line per call
- [ ] Run the tests

### Task 3: analyze_trace.py
**Files:** create `scripts/analyze_trace.py`, `tests/test_analyze.py`, fixtures `test/example-token-audit/{mock_agent_api.py, wasteful_agent.py, clean_agent.py}`
**Produces:** `analyze(paths: list[str]) -> dict` with keys `runs, calls{median,min,max}, tokens{input,output,cache_read,cache_write,total}{median,min,max}, median_run, per_call[], attribution{source: tokens}, cache_hit_rate, findings[{id, severity, title, tokens_involved, calls[], evidence}]`. CLI prints JSON.
Detector ids: `history-growth, huge-tool-result, no-cache, cache-broken, repeated-tool-call, retry-storm, tool-schema-bloat, system-prompt-bloat, overthinking, verbose-output, context-duplication, duplicate-call, per-item-calls, media-resent, debug-in-context`.
- [ ] Tests: the wasteful agent (3 runs through the proxy) hits `history-growth, huge-tool-result, no-cache, repeated-tool-call, retry-storm, verbose-output`; the clean agent has no `high` findings; a 1-call trace and an empty list return without error
- [ ] Implement the detectors, with thresholds as module constants
- [ ] Run the tests

### Task 4: report template + build_report.py
**Files:** create `assets/report-template.html`, `scripts/build_report.py`, `tests/test_build_report.py`
**Produces:** `build_report.py audit.json out.html`. Required fields: `agent, task{name}, numbers{ideal, predicted, actual|null, runs}, cost{perTask, per1k, pricingSource, pricingDate}|null, sources[{source,tokens}], issues[{id,title,category,tokensWasted,confidence,risk,fix}]` (`calls`, `map`, `afterFix`, `method` optional; `predictOnly: true` allows `actual: null`).
- [ ] Tests: a missing `issues[0].fix` exits non-zero and names the field; a `"</script>"` inside a string is escaped in the output; a valid file builds
- [ ] Implement the template: nav, hero (headline, Ideal/Predicted/Actual, cost), where-tokens-go (stacked bar + per-call columns), agent map (rough.js, hot nodes circled), issue bento (filter, expandable evidence), fix-top-3, method, footer
- [ ] Run the tests, then check the report in a browser at 1280px and 390px wide

### Task 5: SKILL.md, references, example, README
**Files:** create `SKILL.md`, `references/issue-catalog.md`, `references/instrumenting.md`, `test/example-token-audit/{README.md, traces/, analysis.json, token-audit.json, report.html}`; modify `README.md`
- [ ] Write the skill (process, safety gates, audit JSON contract) and the references
- [ ] Run the full example end to end: fake API → proxy → wasteful agent × 3 → analyze → audit JSON → report
- [ ] Add the skill to the repo README
