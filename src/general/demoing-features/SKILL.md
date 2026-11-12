---
name: demoing-features
description: Use when asked why a feature, button, or screen exists, what it is used for, or who would use it, or when preparing to demo, present, pitch, or walk someone through a feature, product, or application.
---

# Demoing Features

## Overview

A demo sells what people can do, not how it is built. The output is a styled web page the presenter can run the demo from: every real use of the feature, several ways to explain it, a script, and an Excalidraw-style sketch of the user's journey.

**Core principle:** Every use case is a person in a situation getting a result. If a sentence would only make sense to the engineer who built it, it does not belong on the page.

## Process

1. **Pin the feature and the room.** Name exactly one feature. If the user asked about a control (a button, menu, or screen), everything that control opens is in scope. Take the audience from the request ("my team", "investors"); only if it gives no clue, assume non-technical customers. Write any assumption into `audience`.
2. **Learn what it really does**, from the best source available:
   - In the current codebase: read the code to find what a user can do (inputs, options, outcomes). None of it appears on the page.
   - A public product (Claude, Figma, Slack...): use web search to confirm current behavior, limits, and plan availability. Put the URLs in `sources`. When sources disagree, use the newest official page and add the conflict to `notFor` as "check before the demo".
   - Only a design or spec exists: say so in the first Q&A, the first `notFor` item, and the first setup step, and demo the journey with the sketch.
   - None of these: ask.
3. **List every distinct use**, usually 6-12. Merge near-duplicates. Rank by how common, then how impressive.
4. **Fill the template** (below) and publish.

## Page contract

Write one JSON file, then build the page with `python3 scripts/build_demo.py demo.json demos/<feature-slug>.html` (paths relative to this skill's folder for the script). It checks every field below, lists what is missing, and fills `assets/demo-template.html`: a white, Apple-style page with a bento grid of use cases, framing tabs, and a Present mode (arrow keys plus a clock that shows the current script step). Do not hand-edit the template per demo. `feature` doubles as the page title, so keep it 2-4 words. Fields:

| Field | Contents |
|---|---|
| `feature`, `product`, `audience`, `demoLength` | Short strings |
| `oneLiner` | One sentence, 20 words max: what it is for, in words a non-technical person would say. Caveats go in `questions` or `notFor` |
| `problem` | `{before: [...], after: [...]}`: life without and with it |
| `flow` | `{nodes, edges}`: nodes `{id, label, x, y, w?, h?, shape?}` (shape `rectangle` \| `ellipse` \| `diamond`, `\n` for line breaks), edges `{from, to, label?, dashed?}`. Same spec as the designing-software-architecture skill's diagrams. 3-6 nodes, left to right, ~220px apart: person → what they do → what they get. Labels are user words; no servers, databases, or APIs |
| `flowCaption` | One sentence under the sketch |
| `useCases` | Ranked array of `{group, title, situation, action, result, without}`. `group` is who uses it ("Students", "Sales teams"), never a file type or technology |
| `explanations` | At least 3 `{style, text}`: an everyday analogy, a business-value pitch, and one aimed at the top user group. Add more when the room is mixed |
| `script` | `{hook, setup: [...], steps: [{time, do, say, wow}]}`. Exactly one step has `wow: true`. `do` is the click; `say` is the line to speak |
| `questions` | 4-8 `{q, a}` the audience will ask. Technical answers go here, in plain words |
| `notFor` | Honest limits and what it does not do |
| `sources` | URLs or file paths checked |

Save as `demos/<feature-slug>.html` in the working directory unless the user names a place. If the Artifact tool is available, publish the file (icon `presentation`); otherwise tell the user to open it in a browser. In chat, give the link plus the top 3 uses in one line each.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Use cases grouped by file type or tech ("CSV analysis", "code execution") | Group by who: "Finance analyst closing the month" |
| A "How it works" section, architecture diagram, or jargon table | Sketch the user's journey; technical detail only inside a Q&A answer |
| One analogy | 3+ framings so the presenter can pick for the room |
| Limits and plan details from memory | Web search, or list them in `notFor` as "check before the demo" |
| Covering neighboring features in the same menu | One feature per page; mention a neighbor only inside a use case that needs it |
| Bespoke simulators, download buttons, sample-file generators | Use the template. Downloads do not work in published artifacts |
| Pretending a design is a working product | Say it is a design up front; demo the journey |
