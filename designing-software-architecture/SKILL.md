---
name: designing-software-architecture
description: Use when designing a new system or major feature, choosing between architectural approaches (monolith vs services, SQL vs NoSQL, sync vs async), reviewing an existing design, or asked to write an ADR, system design, or tech stack recommendation.
---

# Designing Software Architecture

## Overview

Architecture is the set of decisions that are expensive to change later. Spend effort in proportion to that cost: decide the hard-to-reverse things deliberately, and defer or default the rest.

**Core principle:** Every choice is a trade-off against stated requirements. A recommendation with no named cost is not an architecture decision.

## Process

1. **Pin down requirements.** Ask or state assumptions for: users and scale (now and in 12 months), read/write ratio, latency and availability targets, consistency needs, data sensitivity, team size and skills, deadline, budget.
2. **Rank the quality attributes.** Pick the top 2-3 (e.g. simplicity, cost, latency, availability, security, evolvability). They cannot all win. This ranking drives every later choice.
3. **Identify the hard-to-reverse decisions.** Usually: data store and data model, service boundaries, sync vs async contracts, auth model, hosting platform, public API shape.
4. **Generate 2-3 real options** for each, including the boring one. Always include "the simplest thing that meets requirements."
5. **Compare against the ranked attributes.** Table: option vs attribute, with the cost of being wrong.
6. **Recommend one**, with reasons, risks, and the trigger that would make you revisit it.
7. **Record it** as an ADR (below).

## Defaults

- Start with a modular monolith. Split into services only for independent scaling, independent deploy cadence by separate teams, or fault isolation you can name.
- Start with one relational database. Add specialized stores for a measured need.
- Prefer managed services over self-run infrastructure unless cost or control is a stated requirement.
- Draw boundaries around things that change together; keep data owned by one module.
- Make the failure modes explicit: what happens when each dependency is down or slow?

## Output Shape

1. Requirements and assumptions (bulleted)
2. Ranked quality attributes
3. Component diagram as an Excalidraw file (see Diagrams) with data flow and trust boundaries
4. Key decisions, each with options considered and the trade-off
5. Risks and open questions
6. Evolution path: what changes at 10x scale

## Diagrams

Draw architecture in Excalidraw's hand-drawn style, as a `.excalidraw` file the user can drag onto https://excalidraw.com to edit or share.

1. Write a JSON spec of `nodes` (id, label, x, y, optional w/h/color/shape) and `edges` (from, to, optional label/dashed). Layout: clients left, edge/API middle, data right; ~100px gaps.
2. Run `python3 scripts/make_excalidraw.py spec.json architecture.excalidraw` (script docstring has the spec format).
3. Conventions: rectangles for services, ellipses for datastores and queues, dashed arrows for async flows, one pastel color per layer, a label on every arrow.
4. Keep one diagram to ~12 boxes; split into context and container views beyond that.

## ADR Template

```markdown
# ADR-NNN: <decision title>
Status: proposed | accepted | superseded by ADR-NNN
Context: <forces, constraints, requirements>
Options: <A, B, C with one-line pros/cons>
Decision: <chosen option and why>
Consequences: <what gets easier, what gets harder, revisit trigger>
```

## Common Mistakes

| Mistake | Fix |
|---|---|
| Microservices "for scale" with no scale data | Modular monolith; extract later along existing module seams |
| Picking tech by familiarity or hype | Tie each choice to a ranked attribute |
| Designing for hypothetical load | Design for 10x current; document what breaks at 100x |
| One option presented | Always show the simple alternative and why it was rejected or chosen |
| Diagram with no failure modes | Annotate what happens when each box is down |
| Skipping the data model | Data shape and ownership outlive code; design them first |
| No revisit trigger | State the metric or event that would reopen the decision |

## Reviewing an Existing Design

Check, in order: requirements unstated or unmet, single points of failure, unclear data ownership, distributed-monolith coupling (services that must deploy together), missing observability, unbounded growth (queues, tables, fan-out), auth at boundaries, and operational burden versus team size.
