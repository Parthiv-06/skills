---
name: auditing-agent-token-usage
description: Use when an LLM agent, chatbot, or AI feature in a codebase uses too many tokens, costs too much, runs slowly, or hits context limits; when asked how many tokens a task should take versus how many it really uses; or when asked to audit, profile, measure, or cut an agent's token usage or API bill.
---

# Auditing Agent Token Usage

## Overview

A task that needs 100 tokens often costs 10,000 because of the code around the model: history resent every turn, a tool dumping a whole file into context, a retry that replays everything, caching that never hits. This skill produces three numbers per task, **Ideal**, **Predicted** (from the code), and **Actual** (measured), then explains every gap with evidence, and shows it all on one report page.

**Core principle:** Every number says how it was made: `measured` (API usage fields), `counted` (exact tokenizer), or `estimated`. An estimate shown as a measurement is the worst failure this skill can have.

## Process

1. **Map the agent.** Read the code and find: every model call (SDK, model, `max_tokens`, thinking budget, streaming), the loop and its stop condition and turn limit, what is assembled into each request (system prompt, tool schemas, history, retrieved docs, files, images), how tool results are sized, retry and error paths, subagents, and prompt-caching markers. Note anything that changes per call or per run (timestamps, IDs, tool order). Sketch it as `map` nodes and edges; mark hot spots with `hot: "<why>"`.
2. **Pick 1–3 tasks.** Use the user's task, else the agent's tests or examples, else propose tasks and confirm.
3. **Predict.**
   - **Fixed cost per call:** run `python3 scripts/count_tokens.py --request body.json` on a real or reconstructed request.
   - **Each turn:** input at turn *t* = fixed + history so far + new content.
   - **Predicted:** the task under this code as written. Show the arithmetic in `method.notes`.
   - **Ideal:** the fewest calls, minimal context, and caching on. If you build or already have a fixed variant, measure it and label Ideal `measured`.
4. **Measure.** Never skip a safety gate:
   1. Show the user the command, the tasks, the number of runs, and a worst-case cost (Predicted × runs, capped by the budget). Wait for a yes.
   2. Tools with side effects (email, payments, writes to shared data) run against a sandbox or are stubbed.
   3. Always run through the proxy with `--budget`.
   4. Nothing secret is stored: the proxy never writes keys or message content. Keep it that way.

   For each run (at least 3, because agents are nondeterministic):
   ```bash
   python3 scripts/usage_proxy.py --provider anthropic --trace audit/traces/<task>-run1.jsonl --budget 500000 &
   ANTHROPIC_BASE_URL=http://127.0.0.1:8788 <command that runs the agent>
   kill %1
   ```
   For OpenAI use `--provider openai` and `OPENAI_BASE_URL=http://127.0.0.1:8788/v1`. If the agent cannot be pointed at a base URL, see `references/instrumenting.md`. If it cannot be run at all, set `predictOnly: true` and say plainly that nothing was measured.
5. **Diagnose.** Run `python3 scripts/analyze_trace.py audit/traces/<task>-run*.jsonl > audit/analysis.json`. Each finding is a lead: its `tokens_involved` is how big the pattern is, not how much is wasted. For each finding:
   - Open the code and confirm the cause at a file and line.
   - Decide the real waste: what the code spends minus what a fixed version would spend.
   - Write the fix with a diff, and set its risk: `safe` only if the model sees the same information.
   - Also check the code for issues a trace cannot show (see `references/issue-catalog.md`).
   - Drop any finding you cannot confirm in the code.
   - Never add up overlapping waste.
6. **After fixing.** Prefer measured: apply the fixes on a branch or copy (with the user's approval) and run step 4 again. Otherwise model the fixed version and label it `estimated`.
7. **Price.** Look up the model's current pricing page (web search). Price input, output, cache-write, and cache-read tokens separately. Record the URL and date. If you can't get prices, set `cost: null`. Never price from memory.
8. **Report.** Write `audit/token-audit.json` (contract below) and run `python3 scripts/build_report.py audit/token-audit.json audit/report.html`. Publish it with the Artifact tool if available (icon `chart`); otherwise tell the user to open the file. In chat, give the three numbers, the top 3 issues in one line each, and the link.

## Audit JSON

| Field | Contents |
|---|---|
| `agent`, `task{name, description}`, `model`, `date`, `project` | Strings. `agent` and `task.name` are required |
| `predictOnly` | `true` if the agent was not run. Then `numbers.actual` is `null` |
| `numbers` | `{ideal, predicted, actual, actualRange: [min, max], runs, labels: {ideal, predicted, actual}}`. Integers per task. `runs` ≥ 3 unless `predictOnly`. Labels are `measured`, `counted`, or `estimated` |
| `cost` | `{perTask, per1k, pricingSource, pricingDate}`, or `null` |
| `sources` | `[{source, tokens}]`: the analyzer's `attribution` with plain names ("Conversation history, resent") |
| `calls`, `cacheHitRate` | The median run's `per_call` as `{call, input, cacheRead, cacheWrite, output, tools}`, and the analyzer's hit rate |
| `map`, `mapCaption` | `{nodes: [{id, label, x, y, w?, h?, shape?, hot?}], edges: [{from, to, label?, dashed?}]}`. Same spec as the architecture skill. 4–7 nodes, about 300px apart |
| `issues` | `[{id, title, category, severity, tokensWasted, confidence, risk, fixSummary, fix, diff?, evidence: {code: [{file, line, snippet}], trace}}]`. `severity` is high, medium, or low. `confidence` is measured or estimated. `risk` is safe or behavior-affecting. Use an empty list if nothing was found |
| `afterFix` | `{count, tokens, label, note}`: tokens per task after fixing the top `count` issues |
| `method` | `{tokenizer, notes: [...], notMeasured: [...]}` |

`build_report.py` refuses incomplete files and names every missing field.

## Common Mistakes

| Mistake | Fix |
|---|---|
| A chars/4 number shown without a label | Label everything; use `count_tokens.py` for exact counts |
| One run | At least 3; report the median and the range |
| Reporting `tokens_involved` as waste | Confirm in the code and compute the real waste |
| Adding up waste across issues | Issues overlap; model the fixes together, or better, measure them |
| Running an agent that can send email or charge cards | Sandbox or stub it, and set a budget cap |
| Marking a context change as a `safe` fix | If the model sees different information, it is `behavior-affecting`; verify it |
| Blaming the model for repeats or loops | The fix belongs in the agent code: deduplicate, limit turns, validate |
| Prices from memory | Look them up, with the date and URL |
| Auditing only the prompt | Most waste is in the loop and the context; for a long prompt, hand off to compressing-agent-prompts |
