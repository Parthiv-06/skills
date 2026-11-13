---
name: packaging-code
description: Use when implementing or designing a feature in a Python codebase, especially one needing a helper or client (retries, HTTP calls, signing, notifications, parsing, formatting) that other modules may already have; when asked to shrink, deduplicate, or extract shared code into a package; or when auditing how Python dependencies are used.
---

# Packaging Code

**Core principle:** every job has one home. Before code gets another copy, it gets a shared home; before something becomes a package, it must prove it pays.

| Moment | Do |
|---|---|
| Building or designing a feature | Build-time check, before writing code |
| Asked to reduce size, deduplicate, or audit packages | Full review |

## Build-time check (about a minute)

1. Run `python3 scripts/scan_packages.py ROOT` (from this skill's folder; under a second). Grep for the helper's job too (`retry`, `sleep(`, `hmac`, `webhook`, `strptime`).
2. Pick the row that matches what you found:

| Found | Do |
|---|---|
| A declared dependency does the job (`tenacity` for retries) | Use it. If it isn't installed here, install it in your env: the declaration decides, not this machine |
| The code exists in a peer module (billing has what alerts needs) | Give it a shared home (`common/`) and import from there. Never import one service from another |
| Copies exist and you would add the next | Build your part on one shared version instead |
| Nothing exists, only you need it | Write it in place. No package |

3. Before coding, tell the user in one line: `Packaging: <what you reuse or share, or "none needed">`.
4. Moving existing code needs the user's yes. If you can't ask, build only the new code in its shared home, leave old copies alone, and list their migration under Next.

## Full review

1. Run the scanner, then open every flagged spot. Flags are leads: a NEAR row's Differs often says why copies must stay apart, and UNUSED? may be a CLI or driver.
2. Put every candidate through the package test (all four):
   1. Two or more users today, or one named and planned
   2. A narrow interface hiding real work (not a one-line wrapper)
   3. No reach-back into app code (models, config, services)
   4. It changes for one reason
3. Pick the smallest home: a module in the shared layer, then a workspace package, then a published library. A generic job (dates, PDFs, retries) with no declared dependency goes to researching-existing-solutions first.

## Report (chat, under 500 words)

```
Verdict: extract N, fix M, ~L lines saved   (or: nothing worth packaging)
Extract: <home> - what moves in; interface (signatures); users; lines saved
Use what you have: <declared package> instead of <hand-written code, file:line>
Misuse: FLAG file:line - fix   (one line each)
Keep as is: <candidate> - which package-test check it fails
Next: what I extract on your yes
```

## Extracting (after yes)

Tests pass before. Move the code unchanged, repoint imports, run tests again. One commit per extraction, separate from feature work.

## Common mistakes

| Mistake | Fix |
|---|---|
| "tenacity isn't installed here, so I'll hand-roll it" | Declared means it ships. Install it locally |
| "The shared helper only handles requests errors, not httpx" | Generalize the shared one (take exception types as an argument) instead of adding a copy |
| Importing another service to reuse its helper | Peer imports tie their releases together; use the shared layer |
| Raising packaging after the code is written | Say it before coding, while the copy is still avoidable |
| Merging NEAR copies into one | Differences are often the point (`ROUND_HALF_UP` vs `ROUND_HALF_EVEN`). Keep them, or require the difference as a parameter |
| Packaging a helper with one caller | Fails check 1; leave it where it is |
| A thin package that wraps a library | HOLLOW; call the library directly |
