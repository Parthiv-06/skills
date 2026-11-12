---
name: compressing-agent-prompts
description: Use when an agent's system prompt, subagent definition, SKILL.md, CLAUDE.md, AGENTS.md, or tool description feels too long, costs too many tokens, or needs review; when asked how good a prompt is, what in it is useless, or how to shorten, compress, tighten, or optimize it without changing what the agent does.
---

# Compressing Agent Prompts

## Overview

Most long agent prompts carry a small core of instructions that actually change behavior, wrapped in repetition, filler, restated defaults, and stacked emphasis. The job is to find that core, say it in the fewest words, and prove the agent still behaves the same.

**Core principle:** Shorter is only a win if behavior is unchanged. Every cut is either lossless by construction or verified by a test. Nothing is dropped on the strength of "the model probably does this anyway" alone.

## Process

1. **Get the prompt and its context.** Read the full prompt file. Also note: which model runs it, which tools it has, and any files it references. A line that looks redundant may exist because of a past failure, so check git history or comments for why it was added.
2. **Measure.** Run `python3 scripts/prompt_check.py <prompt>` for size, repeated sentences, filler, and emphasis count.
3. **Build the inventory.** Split the prompt into numbered units, one per distinct instruction, fact, format, example, or persona trait. Label each:

   | Label | Meaning | Action |
   |---|---|---|
   | CORE | Changes behavior; the model would not do it unprompted | Keep the meaning; may reword shorter |
   | VERBOSE | Needed, but in too many words | Rewrite shorter |
   | DUPLICATE of #n | Same instruction as unit n | Merge into n, keeping the stronger wording and every detail of both |
   | FILLER | Hedges, politeness, "it is important that", stacked IMPORTANT/MUST | Delete (lossless) |
   | DEFAULT | Restates what the model already does ("be helpful", "think step by step") | Cut only if the behavioral test passes without it |
   | CONFLICT with #n | Contradicts unit n | Do not resolve silently; ask the user which wins |
   | VAGUE | Cannot be followed or tested as written | Flag; suggest a concrete rewrite for the user to approve |

4. **Compress in two tiers.**
   - **Lossless:** delete FILLER, merge DUPLICATEs, rewrite VERBOSE, turn parallel rules into a table or list, use one heading per topic. Behavior cannot change.
   - **Tested:** cut DEFAULTs and trim examples. Every one of these needs the behavioral test.
5. **Never alter, only move:** tool names, parameter names, enums, JSON schemas, output formats and templates, exact strings the agent must emit or match, numbers and limits, regexes, code, file paths, placeholders, XML tags, both branches of every conditional, negations, ordering requirements, and safety or refusal rules. Keep at least one example for each format an example teaches.
6. **Gate 1, static:** run `python3 scripts/prompt_check.py <original> <compressed>`. It must print PASS, or every missing token must have a ledger entry explaining why.
7. **Gate 2, behavioral:** see below. Any check the compressed prompt fails more often than the original means restoring that unit, then re-testing.
8. **Report** (below).

## Behavioral equivalence test

Write test inputs that would expose a lost instruction:
- one per CORE unit that can be observed in output,
- one per unit that was cut, merged, or reworded (these carry the most risk),
- one per conditional branch and edge case,
- two ordinary tasks, to catch shifts in tone, length, and format.

For each input, write a pass/fail check tied to the unit ("reply ends with the ticket ID", "refuses refund over $500"). Run both prompts on the same model, at least 3 runs each per input, through the API with the prompt as the system prompt. If only subagents are available, run them with the prompt as their full instructions and say in the report that the test was indirect. If neither is available, give the user the test file to run. Compare pass rates check by check, and also compare output length and format.

A compressed prompt is validated only for the model it was tested on. Re-test after changing models.

## Report

Save the report as `<prompt-name>.compression.md` and the result as `<prompt-name>.compressed.md` next to the original, unless the user names a place. The report contains, in order:

1. **Verdict:** original → compressed size (chars and ~tokens, % saved), a **signal score** (compressed tokens ÷ original tokens, i.e. how much of the original was needed), and the test result in one line.
2. **Quality issues** that are not about length: CONFLICT and VAGUE units, with suggested fixes.
3. **Inventory table:** unit #, short quote, label, what happened to it.
4. **The compressed prompt.**
5. **Ledger:** every original unit → where it lives in the compressed prompt, or why it was removed. No unit may be missing.
6. **Test results:** per-check pass rates, original vs compressed.
7. **Optional cuts:** further savings that failed or were not tested, each with its risk, for the user to decide.

State the result as "no measurable regression across N checks × R runs on <model>". Never claim a guarantee of zero change: a finite test cannot prove one, and the user is relying on the claim.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Rewording a tool name, enum, or output template "for brevity" | These are interfaces. Copy them exactly; the static gate catches most |
| Merging two similar rules and losing a detail from one | The merged rule must contain every condition from both |
| Cutting "obvious" rules without testing | Label DEFAULT and test; obvious rules are often fixes for real failures |
| Deleting all examples | Examples define format better than prose; keep one per format |
| Fixing a contradiction by picking one side | That changes behavior. Ask |
| Testing only the rules that were kept | Test hardest where you cut |
| Reporting only % saved | Lead with the test result; savings without it mean nothing |
| Compressing into cryptic shorthand | Use plain, complete sentences. Shorthand saves characters but costs comprehension and often tokens too |
