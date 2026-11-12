# Skills

Agent skills for [Claude Code](https://claude.com/claude-code).

## Skills

| Skill | Use it for |
|---|---|
| [designing-software-architecture](designing-software-architecture/SKILL.md) | Designing a system or major feature, comparing approaches (monolith vs services, SQL vs NoSQL, sync vs async), reviewing a design, or writing an ADR. Draws diagrams as plain white, hand-drawn [Excalidraw](https://excalidraw.com) files. |

## Install

Clone the repo and copy (or symlink) a skill into your personal skills folder:

```bash
git clone https://github.com/Parthiv-06/skills.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/designing-software-architecture" ~/.claude/skills/
```

Claude Code picks up the skill in new sessions. Ask for something like "design the architecture for a URL shortener" and it will be used automatically.

## Usage

The architecture skill produces a design write-up covering:

1. Requirements and assumptions
2. Ranked priorities (quality attributes)
3. An Excalidraw diagram
4. Key decisions with trade-offs
5. Risks
6. What changes at 10× scale
7. An ADR (architecture decision record)

To generate a diagram by hand, write a small JSON spec of boxes and arrows and run:

```bash
python3 designing-software-architecture/scripts/make_excalidraw.py spec.json architecture.excalidraw
```

Open the result at https://excalidraw.com (☰ menu → Open). The spec format is documented at the top of the script. It needs Python 3 and no extra packages.

## Example

[test/example-url-shortener](test/example-url-shortener/) shows the full output for a URL shortener: the [design write-up](test/example-url-shortener/README.md), the [diagram](test/example-url-shortener/architecture.excalidraw), and the [spec](test/example-url-shortener/spec.json) used to generate it.

## Repo layout

```
designing-software-architecture/
  SKILL.md                 # the skill
  scripts/make_excalidraw.py
test/
  example-url-shortener/   # sample output
```
