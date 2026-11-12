# Skills

Agent skills for [Claude Code](https://claude.com/claude-code).

## Skills

| Skill | Use it for |
|---|---|
| [designing-software-architecture](src/general/designing-software-architecture/SKILL.md) | Designing a system or major feature, comparing approaches (monolith vs services, SQL vs NoSQL, sync vs async), reviewing a design, or writing an ADR. Draws diagrams as plain white, hand-drawn [Excalidraw](https://excalidraw.com) files. |
| [demoing-features](src/general/demoing-features/SKILL.md) | Explaining why a feature or button exists and what people use it for, or preparing to demo a feature or product. Produces a styled web page with every use case, several ways to explain it, a demo script, and a hand-drawn sketch of the user's journey. |
| [compressing-agent-prompts](src/agents/compressing-agent-prompts/SKILL.md) | Reviewing an agent's system prompt (subagent, SKILL.md, CLAUDE.md, tool description): scores how much of it is needed, flags duplicates, filler, conflicts, and vague rules, and compresses it without changing what the agent does, checked by a static gate and a behavioral test. |

## Install

Clone the repo and copy (or symlink) a skill into your personal skills folder:

```bash
git clone https://github.com/Parthiv-06/skills.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/src/general/designing-software-architecture" ~/.claude/skills/
ln -s "$(pwd)/skills/src/general/demoing-features" ~/.claude/skills/
ln -s "$(pwd)/skills/src/agents/compressing-agent-prompts" ~/.claude/skills/
```

Claude Code picks up the skills in new sessions and uses them automatically. Try:

- "Design the architecture for a URL shortener"
- "Why is there an attachment button in Claude?" or "I want to demo our sharing feature to the sales team"
- "How good is the prompt in `.claude/agents/reviewer.md`? Compress it without changing what it does"

## Usage

### designing-software-architecture

Produces a design write-up covering:

1. Requirements and assumptions
2. Ranked priorities (quality attributes)
3. An Excalidraw diagram
4. Key decisions with trade-offs
5. Risks
6. What changes at 10× scale
7. An ADR (architecture decision record)

To generate a diagram by hand, write a small JSON spec of boxes and arrows and run:

```bash
python3 src/general/designing-software-architecture/scripts/make_excalidraw.py spec.json architecture.excalidraw
```

Open the result at https://excalidraw.com (☰ menu → Open). The spec format is documented at the top of the script. It needs Python 3 and no extra packages.

### demoing-features

Produces one web page, a demo pack, written from the user's point of view rather than the technical one:

1. What it is for, in one sentence
2. The problem it solves (before and after)
3. A hand-drawn sketch of the user's journey
4. Every use case, ranked and grouped by who uses it
5. Several ways to explain it (analogy, business value, per audience)
6. A timed demo script with lines to say and one "wow" moment
7. Questions the audience will ask, with answers
8. What it is not for

The page is a white, Apple-style layout with a filterable grid of use cases, tabs for each framing, and a Present mode (arrow keys step through sections; a clock shows which script step you should be on). The skill writes one JSON file and builds the page from [the template](src/general/demoing-features/assets/demo-template.html):

```bash
python3 src/general/demoing-features/scripts/build_demo.py demo.json demo.html
```

The script checks every required field and lists anything missing. The sketch uses the same nodes-and-edges format as the architecture diagrams.

### compressing-agent-prompts

Reads an agent's prompt, splits it into individual instructions, and labels each one: CORE, VERBOSE, DUPLICATE, FILLER, DEFAULT (restates what the model does anyway), CONFLICT, or VAGUE. It then compresses in two tiers: lossless (filler, duplicates, wording) and tested (cuts that need proof). The result must pass two gates before it counts:

1. **Static gate:** every tool name, parameter, number, exact string, and code block from the original is still present:
   ```bash
   python3 src/agents/compressing-agent-prompts/scripts/prompt_check.py original.md                # measure
   python3 src/agents/compressing-agent-prompts/scripts/prompt_check.py original.md compressed.md  # gate (exit 1 on loss)
   ```
2. **Behavioral test:** both prompts run on the same test cases, aimed hardest at whatever was cut. The compressed prompt must pass every check at least as often as the original.

The report gives the size saved, a signal score (how much of the original was needed), quality issues, a ledger mapping every original instruction to its new place, and the test results. It reports "no measurable regression across N checks", never a guarantee.

## Examples

- [test/example-url-shortener](test/example-url-shortener/) shows the architecture and demo skills on a URL shortener: the [design write-up](test/example-url-shortener/README.md), the [diagram](test/example-url-shortener/architecture.excalidraw) and its [spec](test/example-url-shortener/spec.json), and the [demo pack](test/example-url-shortener/demo.html) for a sales and marketing audience, built from [demo.json](test/example-url-shortener/demo.json).
- [test/example-attachment-button](test/example-attachment-button/) shows the demo skill on a public product feature, "Why is there an attachment button in Claude?": the [demo pack](test/example-attachment-button/demo.html) and its [demo.json](test/example-attachment-button/demo.json), with sources checked against Claude's help pages.
- [test/example-prompt-compression](test/example-prompt-compression/) shows a customer-support agent prompt cut by 60% (~604 → ~244 tokens): the [original](test/example-prompt-compression/support-agent.md), the [compressed prompt](test/example-prompt-compression/support-agent.compressed.md), the [report](test/example-prompt-compression/support-agent.compression.md), and the [behavioral tests](test/example-prompt-compression/tests.md).

## Repo layout

```
src/general/
  designing-software-architecture/
    SKILL.md
    scripts/make_excalidraw.py
  demoing-features/
    SKILL.md
    assets/demo-template.html
    scripts/build_demo.py
src/agents/
  compressing-agent-prompts/
    SKILL.md
    scripts/prompt_check.py
test/
  example-url-shortener/       # architecture + demo skills
  example-attachment-button/   # demo skill on a public product feature
  example-prompt-compression/  # prompt compression skill
```
