---
name: explaining-how-it-works
description: Use when asked to explain how a feature, flow, integration, or part of an application works; how it works from one point to another (from a click to an email, from a webhook to the database); what happens when something is triggered; how the code talks to an external service; or for an architecture diagram of existing code.
---

# Explaining How It Works

## Overview

The output explains how existing code works, twice:

- **Part 1:** plain English that anyone can follow.
- **Part 2:** a deep technical account in which every hop is proven by file:line, with professional architecture diagrams at as many levels as the question needs.

Both parts share one step numbering. Plain step 3 points to trace steps 3a–3c, which are arrows 3a–3c in the sequence diagram.

**Core principle:** Trace before you explain. Follow the path through the real code to its real end, including error paths and anything that runs later. A summary written from two skimmed files is the failure this skill exists to prevent.

## Process

1. **Pin the question as start → end.**
   - Start: a click, a request, a cron tick, an incoming webhook, or a CLI call.
   - End: what the user sees, the data written, the message sent.
   - For "explain feature X", trace its main use; list other entry points as side paths.
   - If you can't find the start or end in the code, ask one question.
2. **Trace hop by hop**, using `references/tracing-checklist.md`. For each hop, record:
   - from → to, and how (call, HTTP, queue, event, cron)
   - what data travels
   - file:line
   - what can fail

   The trace is finished only when:
   - every hop has both ends located
   - every branch ends somewhere (a response, a retry, a log, a crash)
   - every async hand-off has been followed to its consumer
   - every external call has a filled card
   - every write is listed

   Read the code at every hop. A name that suggests behavior is not evidence.
3. **Optional runtime check.** If the order of hops is unclear (events, races, async), propose running the flow or its tests with temporary logs. Run it only after the user agrees, and remove the logs afterwards. Mark confirmed rows `observed`. If there is no one to ask (you are a subagent or running unattended), skip it: rows stay `verified`, and the unclear ordering goes in `open`.
4. **Choose the views.**
   - Context and Sequence are always drawn.
   - Add Containers, Components, State, Data, or Deployment when the question needs them (table in `references/diagram-style.md`).
   - Each view must show something the others don't. Most explanations need 3–5 views.
5. **Write the explainer JSON** (contract below).
   - Part 1 follows `references/plain-english.md`.
   - Diagram specs follow `references/diagram-style.md`. Give elements `col` and `row` so the flow reads left to right with straight arrows.
6. **Build:** `python3 scripts/build_explainer.py explainer.json <out_dir>`.
   - It refuses to build until everything checks out: plain English, step links, one card per external system, every diagram's layout.
   - Fix every problem it lists, then look at each SVG in `<out_dir>/diagrams/`. Open them in a browser, or render them to PNG (`qlmanage -t -s 1600 -o <dir> <file>.svg` on macOS, or headless Chrome `--screenshot`) and view the image. If two boxes or labels crowd each other, adjust `col` and `row` and rebuild.
7. **Publish** `<out_dir>/index.html` with the Artifact tool if available (icon `book`); otherwise give the path. In chat, give the answer sentence, the plain steps as one line each, and the link. The `.excalidraw` files in `<out_dir>/diagrams/` open in excalidraw.com for editing.

Save to `explainers/<subject-slug>/` in the working directory, unless the user names a place or asks you not to change the repo. In that case, use a scratch or temp folder and say where.

If the path calls no third-party or other-team service, leave `external` empty and say so in the context view's caption. Don't invent one. Code the path itself launches (a child process, a plugin, the program under test) is a `service`, not `external`.

## Explainer JSON

| Field | Contents |
|---|---|
| `question`, `subject`, `answer` | The question as asked; a 3–6 word title; one plain sentence (30 words max) |
| `scope` | `{start, end}` in plain words |
| `plain` | `{steps: [{n, title, see, behind, tech: [trace steps]}], analogy?, worth: [...], terms: [{term, plain}]}`. 5–9 steps numbered 1..n. Together they cover every trace step |
| `summary` | 3–5 sentences for engineers. Backticks mark code |
| `diagrams` | Specs from `references/diagram-style.md`, at most one per view. `context` and `sequence` are required. Sequence steps must equal the trace steps |
| `trace` | `[{step, from, to, how, data, where, status}]` in step order. `status` is verified, observed, or inferred. `where` (file:line) is required unless inferred |
| `external` | One card per `external` element, `{id, name, purpose, interface, auth, sends, limits, callbacks, whenDown, evidence: [...]}` |
| `data` | `[{store, reads, writes, notes}]` |
| `failures` | `[{what, userSees, codeDoes, where}]`, at least one |
| `timing`, `security`, `performance`, `debug`, `open`, `noticed` | Lists of strings. `debug` names breakpoints, logs, tests, and how to run it locally. `noticed` holds suspected bugs seen along the way |
| `config` | `[{name, effect, where}]` |
| `sources` | Files and URLs read |
| `diagramFiles` | Where the `.excalidraw` files are |

## Common Mistakes

| Mistake | Fix |
|---|---|
| Explaining from function names | Open every hop; quote file:line or mark it `inferred` |
| Stopping at `enqueue`, `publish`, or "sends a webhook" | Find the consumer or receiver; it's part of the path |
| Only the happy path | Every branch ends somewhere; failures go in the table |
| One big diagram | Split by level: Context → Containers → Components, plus Sequence for time |
| The same level drawn twice | One per view; a deeper view must show new detail |
| Colors, icons, or decoration | The standard is black ink, standard shapes, and a legend |
| Jargon in Part 1 | Say it plainly (`references/plain-english.md`); the gate blocks the rest |
| Guessing what an external service does | Cite its docs, or write `unknown: <why>` |
| Mixing review comments into the explanation | Put them in `noticed`; keep the story clean |
