---
name: writing-two-line-comments
description: Use when writing or editing code in any language, adding docstrings, file headers, or inline comments, or when a comment checker reports BLOCK, LONG, NO-HEADER, CODE, HISTORY, or BANNER.
---

# Writing Two-Line Comments

**Every comment is at most 2 lines.** That covers file headers, docstrings, JSDoc, and inline comments alike. Each line under 100 characters.

## The two lines

1. **What it is for:** its purpose, in the project's own terms. Never the name restated.
2. **What to watch:** the one fact a reader would otherwise get wrong: a side effect, a constraint, units, failure behavior, or why it is done this way.

```python
"""Per-key token-bucket rate limiter, thread-safe, with blocking and asyncio waits.
Waiters reserve tokens up front (balance can go negative), so callers are served FIFO."""
```

## Where comments go

| Place | Rule |
|---|---|
| Top of every code file | Required 2-line header |
| Function, class, method | Only if a teammate would have to read the body to call it safely |
| Inside a function | Only for a non-obvious why |

## Editing a file

Bring every comment in the file you edited within the rule. When cutting a long comment, keep its single most decision-critical fact. Usage examples belong in tests, and design history belongs in the commit message. A banner that states a rule ("callers must hold the lock") moves that rule to line 2 of each affected docstring before the banner goes. Tell the user the diff includes comment cleanup, and keep it in a separate commit from the behavior change when committing.

## Before saying done

Run `python3 scripts/check_comments.py <files you touched>`, or `--changed <repo>`. It must print `OK`. If the hook is installed, it runs after every edit; fix whatever it reports before moving on.

## Common mistakes

| Mistake | Fix |
|---|---|
| Args/Returns/Raises sections | Types live in the signature; keep only the surprising part |
| Comments on every line | Delete them; rename the variable instead |
| Section banners (`# ===== Helpers =====`) | Delete; split the file if it needs sections |
| "Fixed X", "now handles Y" | Commit message |
| Commented-out code | Delete it; git keeps history |
| Two lines crammed into one 300-character line | Under 100 characters per line |
