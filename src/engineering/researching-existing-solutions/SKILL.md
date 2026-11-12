---
name: researching-existing-solutions
description: Use when about to write Python code that a library might already provide, when adding a Python dependency, or when asked which Python package, library, or open-source tool to use for something.
---

# Researching Existing Solutions (Python)

## Overview

Before writing code or adding a dependency, find out what already exists, prove the best option works, and recommend one. Evidence beats memory: every claim about a package is live, dated, and linked.

**Core principle:** A recommendation is only as good as its weakest check. Unverified health, an unchecked license, or an untried API each sink it.

## Depth

| Situation | Depth |
|---|---|
| Small helper inside existing code (slugify, retry one call) | **Quick:** steps 1, 2, 4. Max 3 candidates. Spike only if unsure |
| New production dependency, or user asks for deep research | **Deep:** all steps |

## Process

1. **Write the need as testable must-haves**, plus constraints: Python version, the project's license (closed-source? distributed or SaaS?), deployment (Docker, Lambda, Windows), threading or async model.
2. **Check the project first.** Search the code for an existing helper. Run `python3 scripts/pkg_facts.py <candidates> --project <repo>` to see what is already declared or pinned. Check the standard library. An installed package that meets the must-haves wins unless it fails a check.
3. **Search wide (deep only).** Web search for `python <need> library`, `<best-known package> alternatives`, the awesome-python list, GitHub topics, and deps.dev. Include services you can run beside the app (a Docker sidecar) when the need is heavy. Collect 6-15 names.
4. **Pull facts in one call:** `python3 scripts/pkg_facts.py name1 name2 ... --project <repo>`. Drop anything flagged ARCHIVED, STALE, VULNS, DEPRECATED, or NO-PY312 unless nothing else fits. Treat COPYLEFT and SOURCE-AVAILABLE by the project's license: AGPL, SSPL, BUSL are out for closed-source SaaS; GPL is out for distributed closed-source; LGPL is fine as an unmodified dependency. Resolve LICENSE-MISMATCH by reading the repo's LICENSE file.
5. **Read for fit.** For the 2-4 survivors, read the docs and search open issues for each must-have keyword. Note known pitfalls (thread safety, async support, unsafe defaults).
6. **Spike the top 1-2.** Build a throwaway venv outside the project (`python3 -m venv "$TMPDIR/spike-<pkg>"`), install the exact version, and run a script that exercises every must-have, including one failure case. Never install into the project's environment. Budget about 10 minutes; if a spike is impossible (system libraries, API keys), say why in the report.
7. **Decide.** Adopt (exact fit), Extend (thin wrapper), Compose (2-3 small packages), or Build (nothing fits, or under ~50 lines with no edge cases, so a dependency costs more than it saves).

## Report

Reply in chat (no artifact unless asked), under ~600 words, in this order:

1. **Verdict:** Adopt/Extend/Compose/Build `package==version`, one sentence why, and the install command.
2. **Must-haves:** checklist, each marked met or not by the pick.
3. **Already in the project:** what was found, and whether it was used.
4. **Candidates:** the `pkg_facts.py` table trimmed to the finalists, with a Fit column.
5. **Proof:** what the spike ran and the result per must-have, or why there was no spike.
6. **Ruled out:** one line each: name, reason, source.
7. **Risks:** how the pick could still hurt in this codebase (unsafe defaults, non-idempotent calls, thread safety, system packages for Docker).
8. **Not checked:** channels or facts that were unavailable.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Release dates, licenses, or stars from memory | `pkg_facts.py` output, dated |
| Handing the user a "1-2 day trial" | Run a 10-minute spike yourself; leave only what truly needs their data |
| 3,000-word report with the verdict buried | The report order above; verdict first |
| Adding a new package when an installed one fits | Step 2; say why the installed one lost if it did |
| Trusting a package's defaults | Spike the defaults; flag unsafe ones in Risks |
| Reporting "nothing found" when a search channel failed | List it under Not checked |
