# Skills

Agent skills for [Claude Code](https://claude.com/claude-code).

## Skills

| Skill | Use it for |
|---|---|
| [designing-software-architecture](src/general/designing-software-architecture/SKILL.md) | Designing a system or major feature, comparing approaches (monolith vs services, SQL vs NoSQL, sync vs async), reviewing a design, or writing an ADR. Draws diagrams as plain white, hand-drawn [Excalidraw](https://excalidraw.com) files. |
| [demoing-features](src/general/demoing-features/SKILL.md) | Explaining why a feature or button exists and what people use it for, or preparing to demo a feature or product. Produces a styled web page with every use case, several ways to explain it, a demo script, and a hand-drawn sketch of the user's journey. |
| [compressing-agent-prompts](src/agents/compressing-agent-prompts/SKILL.md) | Reviewing an agent's system prompt (subagent, SKILL.md, CLAUDE.md, tool description): scores how much of it is needed, flags duplicates, filler, conflicts, and vague rules, and compresses it without changing what the agent does, checked by a static gate and a behavioral test. |
| [auditing-agent-token-usage](src/agents/auditing-agent-token-usage/SKILL.md) | Finding out why an LLM agent uses far more tokens than its task needs. Predicts the cost from the code, measures real usage through a logging proxy, explains every gap as an issue with file:line evidence and a fix, and shows it all on an Apple-style report page. |
| [researching-existing-solutions](src/engineering/researching-existing-solutions/SKILL.md) | Before writing Python code or adding a dependency: finds existing open-source packages, pulls live health, license, and vulnerability data, tests the top pick in a throwaway environment, and recommends one. |
| [writing-two-line-comments](src/engineering/writing-two-line-comments/SKILL.md) | Any time code is written or edited, in any language: every comment is at most 2 lines (what it is for, then what to watch), every file gets a header, and a checker plus an optional hook enforce it. |

## Install

Clone the repo and copy (or symlink) a skill into your personal skills folder:

```bash
git clone https://github.com/Parthiv-06/skills.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/src/general/designing-software-architecture" ~/.claude/skills/
ln -s "$(pwd)/skills/src/general/demoing-features" ~/.claude/skills/
ln -s "$(pwd)/skills/src/agents/compressing-agent-prompts" ~/.claude/skills/
ln -s "$(pwd)/skills/src/agents/auditing-agent-token-usage" ~/.claude/skills/
ln -s "$(pwd)/skills/src/engineering/researching-existing-solutions" ~/.claude/skills/
ln -s "$(pwd)/skills/src/engineering/writing-two-line-comments" ~/.claude/skills/
```

Claude Code picks up the skills in new sessions and uses them automatically. Try:

- "Design the architecture for a URL shortener"
- "Why is there an attachment button in Claude?" or "I want to demo our sharing feature to the sales team"
- "How good is the prompt in `.claude/agents/reviewer.md`? Compress it without changing what it does"
- "Our support agent costs way too much per ticket. Find out where the tokens go"
- "I need to generate PDF invoices in Python. Research what open-source packages I can use"
- Any coding task: the comment rule applies on its own

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

### auditing-agent-token-usage

Gives three numbers per task: **Ideal** (what the task needs), **Predicted** (what the code implies), and **Actual** (measured). Every number is labeled measured, counted, or estimated. Four Python scripts, standard library only:

| Script | Does |
|---|---|
| `count_tokens.py` | Exact token counts (Anthropic count_tokens API or tiktoken), else a labeled estimate |
| `usage_proxy.py` | Sits between the agent and the API with no code changes (`ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`). Logs real usage per call, handles streaming, enforces a budget cap, never stores keys or content |
| `analyze_trace.py` | Turns 3+ runs into stats, a by-source breakdown, and findings from 18 detectors (resent history, huge tool results, missing or broken caching, retry storms, repeated tool calls, and more) |
| `build_report.py` | Checks the audit JSON and builds the report page: hero numbers, where the tokens go, a hand-drawn agent map, ranked issue cards with code evidence and fixes, and before/after |

Running the agent costs money, so the skill shows the cost first and waits for a yes, stubs tools with side effects, and always sets a budget cap. Tests: `python3 -m unittest discover -s src/agents/auditing-agent-token-usage/tests`.

### researching-existing-solutions

Python only. Checks the project's own code and lockfile first, searches wide, then pulls live facts for every candidate in one call:

```bash
python3 src/engineering/researching-existing-solutions/scripts/pkg_facts.py tenacity backoff stamina --project path/to/repo
```

It prints a dated table (latest release, releases per year, downloads, stars, last push, OpenSSF Scorecard, license, dependencies, known vulnerabilities, already in the project) and flags ARCHIVED, STALE, VULNS, COPYLEFT, SOURCE-AVAILABLE, and more. Licenses are cross-checked across deps.dev, PyPI, and GitHub, so an AGPL package can't hide behind a "non-standard" label. The top pick is then tested in a throwaway virtualenv, never in the project. The answer is a short chat report with the verdict first.

### writing-two-line-comments

Every comment is at most 2 lines, each under 100 characters: line 1 says what it is for, line 2 says what to watch. Every code file gets a 2-line header; functions get a comment only when a teammate would have to read the body to call them safely. Editing a file brings all its comments within the rule.

The checker enforces it for Python (docstrings included), JS/TS, Go, Java, C/C++, Rust, Swift, Kotlin, shell, Ruby, SQL, and more:

```bash
python3 src/engineering/writing-two-line-comments/scripts/check_comments.py file.py other.ts   # specific files
python3 src/engineering/writing-two-line-comments/scripts/check_comments.py --changed .        # everything changed in git
```

It reports BLOCK, LONG, NO-HEADER, CODE (commented-out code), HISTORY (change-log wording), and BANNER. License headers and tool directives (`# noqa`, `// eslint-disable`) don't count. To check after every edit automatically, add this hook to `~/.claude/settings.json`; violations are sent straight back to Claude:

```json
"hooks": { "PostToolUse": [{ "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type": "command",
  "command": "python3 /path/to/skills/src/engineering/writing-two-line-comments/scripts/check_comments.py --hook" }] }] }
```

## Examples

- [test/example-url-shortener](test/example-url-shortener/) shows the architecture and demo skills on a URL shortener: the [design write-up](test/example-url-shortener/README.md), the [diagram](test/example-url-shortener/architecture.excalidraw) and its [spec](test/example-url-shortener/spec.json), and the [demo pack](test/example-url-shortener/demo.html) for a sales and marketing audience, built from [demo.json](test/example-url-shortener/demo.json).
- [test/example-attachment-button](test/example-attachment-button/) shows the demo skill on a public product feature, "Why is there an attachment button in Claude?": the [demo pack](test/example-attachment-button/demo.html) and its [demo.json](test/example-attachment-button/demo.json), with sources checked against Claude's help pages.
- [test/example-prompt-compression](test/example-prompt-compression/) shows a customer-support agent prompt cut by 60% (~604 → ~244 tokens): the [original](test/example-prompt-compression/support-agent.md), the [compressed prompt](test/example-prompt-compression/support-agent.compressed.md), the [report](test/example-prompt-compression/support-agent.compression.md), and the [behavioral tests](test/example-prompt-compression/tests.md).
- [test/example-token-audit](test/example-token-audit/) shows a token audit of a bug-triage agent with six planted problems: 168,068 tokens per task measured against 2,103 for the fixed version (80× less). See the [report page](test/example-token-audit/report.html), the [audit JSON](test/example-token-audit/token-audit.json), and the [agent](test/example-token-audit/wasteful_agent.py).

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
  auditing-agent-token-usage/
    SKILL.md
    references/                # issue catalog, per-SDK instrumenting
    scripts/                   # count_tokens, usage_proxy, analyze_trace, build_report
    assets/report-template.html
    tests/                     # 21 tests + a fake API for running agents offline
src/engineering/
  researching-existing-solutions/
    SKILL.md
    scripts/pkg_facts.py
  writing-two-line-comments/
    SKILL.md
    scripts/check_comments.py
test/
  example-url-shortener/       # architecture + demo skills
  example-attachment-button/   # demo skill on a public product feature
  example-prompt-compression/  # prompt compression skill
  example-token-audit/         # token audit skill
```
