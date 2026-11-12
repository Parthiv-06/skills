# Skills

Agent skills for [Claude Code](https://claude.com/claude-code).

## Skills

| Skill | Use it for |
|---|---|
| [designing-software-architecture](src/general/designing-software-architecture/SKILL.md) | Designing a system or major feature, comparing approaches (monolith vs services, SQL vs NoSQL, sync vs async), reviewing a design, or writing an ADR. Draws diagrams as plain white, hand-drawn [Excalidraw](https://excalidraw.com) files. |
| [demoing-features](src/general/demoing-features/SKILL.md) | Explaining why a feature or button exists and what people use it for, or preparing to demo a feature or product. Produces a styled web page with every use case, several ways to explain it, a demo script, and a hand-drawn sketch of the user's journey. |

## Install

Clone the repo and copy (or symlink) a skill into your personal skills folder:

```bash
git clone https://github.com/Parthiv-06/skills.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/src/general/designing-software-architecture" ~/.claude/skills/
ln -s "$(pwd)/skills/src/general/demoing-features" ~/.claude/skills/
```

Claude Code picks up the skills in new sessions and uses them automatically. Try:

- "Design the architecture for a URL shortener"
- "Why is there an attachment button in Claude?" or "I want to demo our sharing feature to the sales team"

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

The page is built from [assets/demo-template.html](src/general/demoing-features/assets/demo-template.html): the skill fills in one JSON block and the template draws the page. The sketch uses the same nodes-and-edges format as the architecture diagrams.

## Example

[test/example-url-shortener](test/example-url-shortener/) shows both skills on a URL shortener: the [design write-up](test/example-url-shortener/README.md), the [diagram](test/example-url-shortener/architecture.excalidraw) and its [spec](test/example-url-shortener/spec.json), and the [demo pack](test/example-url-shortener/demo.html) for a sales and marketing audience.

## Repo layout

```
src/general/
  designing-software-architecture/
    SKILL.md
    scripts/make_excalidraw.py
  demoing-features/
    SKILL.md
    assets/demo-template.html
test/
  example-url-shortener/   # sample output from both skills
```
