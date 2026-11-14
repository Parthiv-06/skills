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
| [packaging-code](src/engineering/packaging-code/SKILL.md) | Python code that keeps growing by copy-paste. While a feature is being built, it says what should be shared or which declared package to use, before another copy gets written. On request, it reviews the repo for code worth extracting into a package and for packages that are misused, unused, or carry nothing. |
| [mapping-database-schemas](src/databases/mapping-database-schemas/SKILL.md) | Understanding a database or dataset (BigQuery, Postgres, SQLite, SQL DDL): maps every primary and foreign key, labels each link declared, inferred, or guess, and traces what each view is built from. Produces two files: an Apple-style page that explains everything in words, and a precise Excalidraw diagram drawn from the exact key columns. |
| [mapping-data-access](src/databases/mapping-data-access/SKILL.md) | Which service reads and writes which table, in a Python codebase. Scans the code (following calls into shared libraries), adds query logs from Postgres or BigQuery when you have them, and labels every link code + logs, code only, or logs only. Produces an Apple-style page and an Excalidraw diagram of services, tables, and the direction data moves. |
| [writing-two-line-comments](src/engineering/writing-two-line-comments/SKILL.md) | Any time code is written or edited, in any language: every comment is at most 2 lines (what it is for, then what to watch), every file gets a header, and a checker plus an optional hook enforce it. |
| [explaining-how-it-works](src/engineering/explaining-how-it-works/SKILL.md) | Explaining how a feature, a flow from A to B, or an external integration works in existing code. Traces every hop with file:line evidence, then explains it twice: in plain English (jargon is blocked) and in depth, with professional architecture diagrams at several levels (context, containers, components, sequence, and more). Produces an Apple-style page plus editable Excalidraw files. |

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
ln -s "$(pwd)/skills/src/engineering/packaging-code" ~/.claude/skills/
ln -s "$(pwd)/skills/src/engineering/writing-two-line-comments" ~/.claude/skills/
ln -s "$(pwd)/skills/src/engineering/explaining-how-it-works" ~/.claude/skills/
ln -s "$(pwd)/skills/src/databases/mapping-database-schemas" ~/.claude/skills/
ln -s "$(pwd)/skills/src/databases/mapping-data-access" ~/.claude/skills/
```

Claude Code picks up the skills in new sessions and uses them automatically. Try:

- "Design the architecture for a URL shortener"
- "Why is there an attachment button in Claude?" or "I want to demo our sharing feature to the sales team"
- "How good is the prompt in `.claude/agents/reviewer.md`? Compress it without changing what it does"
- "Our support agent costs way too much per ticket. Find out where the tokens go"
- "I need to generate PDF invoices in Python. Research what open-source packages I can use"
- "This codebase is getting too big. What could be made into packages, and are we using any packages wrongly?"
- "Map our BigQuery dataset `acme.analytics`: how does everything connect?" or "Explain the schema in `shop.db`"
- "Which of our services read and write which tables? Here are the pg_stat_statements and BigQuery job logs"
- "Explain how checkout works, from clicking Pay until the receipt email arrives"
- Any coding task: the comment and packaging checks apply on their own

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

### packaging-code

Python only. It works at two points:

1. **While building a feature:** before writing a helper, it checks whether the job is already done somewhere. If a declared dependency covers it, it uses that dependency, even when it isn't installed on this machine. If another service has the code, it moves it to a shared home instead of importing one service from another. It says which it chose in one line before coding, and moves existing code only after you say yes.
2. **When asked for a review:** it puts every candidate through four checks: two or more users, a narrow interface hiding real work, no reach-back into app code, and one reason to change. It then reports a verdict, what to extract (with interfaces and lines saved), what to fix, and what to leave alone and why.

Both start with a scanner. It needs only the standard library and takes under a second:

```bash
python3 src/engineering/packaging-code/scripts/scan_packages.py path/to/repo
```

It lists duplicate functions. EXACT means copies identical apart from variable names. NEAR means the same shape with small differences, and it names them, such as `ROUND_HALF_UP vs ROUND_HALF_EVEN`, because those differences are often why the copies must stay separate. It also flags:

- **Dependencies:** UNUSED, UNDECLARED, MISPLACED, HEAVY, OVERLAP
- **Code:** BLOCKING (blocking calls in async code), NO-TIMEOUT, PRIVATE, PATCH (monkeypatching), RETRY-LOOP, VENDORED
- **Structure:** HOLLOW (packages carrying nothing), LEAKY, CYCLE, UNREFERENCED

`--help` explains each flag.

### mapping-database-schemas

Four Python scripts that use only the standard library. Facts come from the scripts and the agent writes the words:

| Script | Does |
|---|---|
| `extract_schema.py` | Reads a SQLite file or DDL files (pg_dump, mysqldump, BigQuery console exports) into one `schema.json`. For live BigQuery and Postgres, it prints a metadata query that reads INFORMATION_SCHEMA only, so no table data is scanned. Collapses day-sharded tables (`events_20261101`, ...) into `events_*` |
| `analyze_schema.py` | Finds every key and link. Labels each one declared, inferred (name and type match), or guess (type mismatch, or under 95% of values match in a data check). Works out cardinality, optional or required, roles (billing vs shipping address), self-references, many-to-many link tables, and view lineage. Also flags missing keys, polymorphic columns, unindexed foreign keys, and type mismatches |
| `build_schema_page.py` | Builds the explanation page from the analysis plus `page.json`, the agent's plain-language text. It refuses to build if any table, view, or link is unexplained, if an inferred link is described as certain, or if a join path uses a link that doesn't exist |
| `make_er_excalidraw.py` | Draws the diagram. Each foreign-key row has its own arrow to the exact key row, labeled N, 1, or 0..1. Lines are solid when declared, dashed when inferred, and dotted for a guess. A layout search keeps crossings low, and no box overlaps another and no arrow runs through a box. It prints that self-check after every run. Above 15 tables it draws an overview plus one diagram per area |

```bash
cd src/databases/mapping-database-schemas/scripts
python3 extract_schema.py sqlite shop.db > schema.json
python3 analyze_schema.py schema.json analysis.json --sqlite shop.db
python3 build_schema_page.py analysis.json page.json schema.html
python3 make_er_excalidraw.py analysis.json page.json schema.excalidraw
```

### mapping-data-access

Python only. Five scripts that use only the standard library:

| Script | Does |
|---|---|
| `scan_access.py` | Finds services (docker-compose, Dockerfiles, Alembic) and each service's database and role. Reads SQL in strings and in loaded `.sql` files, plus SQLAlchemy, Django, pandas, BigQuery client, and Alembic calls. It follows calls into shared libraries, so a repository function counts only for the services that call it. Dynamic SQL is resolved from call sites that pass a constant, or else listed as unresolved |
| `runtime_access.py` | Prints the read-only query for BigQuery `INFORMATION_SCHEMA.JOBS` or Postgres `pg_stat_statements` and turns the result into evidence with counts |
| `analyze_access.py` | Merges code and logs. Maps Postgres roles to services through `DATABASE_URL`, and BigQuery service accounts by name; everything else is shown as an outside reader or writer. Expands view reads to their base tables, and finds tables with several writers, writers outside the repo, tables nobody writes, tables written but never read, untouched tables, and links seen only in code or only in logs |
| `build_access_page.py` | Builds the page: services, outside participants, tables, a read/write matrix, data flows, findings, and the evidence for every link. It refuses to build while anything is unexplained |
| `make_access_excalidraw.py` | Draws one arrow per service and table, pointing the way data moves. Columns alternate services and each database's tables, so a job that reads one database and writes another sits between them. A layout search keeps crossings low, and it prints a self-check after every run |

```bash
cd src/databases/mapping-data-access/scripts
python3 scan_access.py path/to/repo access.json
python3 runtime_access.py parse postgres stats.json shopdb > rt_pg.json
python3 analyze_access.py access.json analysis.json --runtime rt_pg.json --schema shopdb=shop.analysis.json
python3 build_access_page.py analysis.json page.json access.html
python3 make_access_excalidraw.py analysis.json page.json access.excalidraw
```

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

### explaining-how-it-works

Turns "how does X work?" into a start → end path and traces it through the code. Every hop is recorded with file:line, every branch is followed to where it ends, and every external service gets a card covering auth, data sent, limits, and what happens when it is down. The result is explained twice. Part 1 is 5–9 plain steps; a gate blocks technical words unless they are defined. Part 2 has the trace, failure modes, security, config, and debugging notes. The same step numbers run through both parts and the diagrams.

Diagrams follow a professional standard: black ink on white, Excalidraw's clean "Architect" lines, a standard shape for each kind of thing, labeled boundaries, the protocol on every arrow, and a legend and level on every view. The views are Context, Containers, Components, Sequence, State, Data, and Deployment; the question decides which are drawn. Layout is automatic, and the script refuses messy diagrams:

```bash
python3 src/engineering/explaining-how-it-works/scripts/build_explainer.py explainer.json out/   # page + .svg + .excalidraw
python3 src/engineering/explaining-how-it-works/scripts/diagrams.py spec.json out/name           # one diagram
```

## Examples

- [test/example-url-shortener](test/example-url-shortener/) shows the architecture and demo skills on a URL shortener: the [design write-up](test/example-url-shortener/README.md), the [diagram](test/example-url-shortener/architecture.excalidraw) and its [spec](test/example-url-shortener/spec.json), and the [demo pack](test/example-url-shortener/demo.html) for a sales and marketing audience, built from [demo.json](test/example-url-shortener/demo.json).
- [test/example-attachment-button](test/example-attachment-button/) shows the demo skill on a public product feature, "Why is there an attachment button in Claude?": the [demo pack](test/example-attachment-button/demo.html) and its [demo.json](test/example-attachment-button/demo.json), with sources checked against Claude's help pages.
- [test/example-prompt-compression](test/example-prompt-compression/) shows a customer-support agent prompt cut by 60% (~604 → ~244 tokens): the [original](test/example-prompt-compression/support-agent.md), the [compressed prompt](test/example-prompt-compression/support-agent.compressed.md), the [report](test/example-prompt-compression/support-agent.compression.md), and the [behavioral tests](test/example-prompt-compression/tests.md).
- [test/example-packaging](test/example-packaging/) shows the packaging skill on a small three-service repo with planted problems: the [repo](test/example-packaging/shopco/), the [scanner output](test/example-packaging/scan.md), and the [review](test/example-packaging/review.md). The review finds 2 helpers to extract and 9 misuses, and leaves alone two rounding functions that look like copies but must stay different.
- [test/example-database-schema](test/example-database-schema/) shows the database skill on two schemas:
  - [shop/](test/example-database-schema/shop/): a SQLite shop with 14 declared foreign keys, a link table, two tables that point to themselves, two links from orders to addresses, a one-to-one, and a view built on another view.
  - [analytics/](test/example-database-schema/analytics/): a BigQuery dataset with almost no declared keys, daily-sharded events, and a type mismatch.

  Each folder has the input, `schema.html`, `schema.excalidraw`, and the intermediate JSON files. Both were produced by agents following the skill; without it, the same task took about 6 to 10 times longer and used 2 to 3 times the tokens.
- [test/example-data-access](test/example-data-access/) shows the data access skill on a [Python monorepo](test/example-data-access/shopco/) with four services, a shared repository library, Alembic migrations, and exported Postgres and BigQuery query logs. The [output](test/example-data-access/output/) has the page and the diagram, plus every intermediate JSON file. Things it gets right:
  - `admin-api` imports the orders repository but only reads through it, so it is not counted as a writer.
  - A dynamic `DELETE FROM {table}` is resolved to `audit_log` from its call site.
  - An outside CRM role turns out to be the only writer of `customers`.
- [test/example-token-audit](test/example-token-audit/) shows a token audit of a bug-triage agent with six planted problems: 168,068 tokens per task measured against 2,103 for the fixed version (80× less). See the [report page](test/example-token-audit/report.html), the [audit JSON](test/example-token-audit/token-audit.json), and the [agent](test/example-token-audit/wasteful_agent.py).
- [test/example-how-it-works](test/example-how-it-works/) explains how the token audit gets from an agent's API call to the report page, traced through this repo's own code. It has 7 plain steps and 9 hops with file:line, drawn as context, containers, components, and sequence views. See the [page](test/example-how-it-works/out/index.html), the [explainer JSON](test/example-how-it-works/explainer.json), and the [diagrams](test/example-how-it-works/out/diagrams/).

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
  packaging-code/
    SKILL.md
    scripts/scan_packages.py
  writing-two-line-comments/
    SKILL.md
    scripts/check_comments.py
  explaining-how-it-works/
    SKILL.md
    references/                # diagram standard, tracing checklist, plain English
    scripts/                   # diagrams, check_plain, build_explainer
    assets/explainer-template.html
    tests/
src/databases/
  mapping-database-schemas/
    SKILL.md
    scripts/                   # extract_schema, analyze_schema, build_schema_page, make_er_excalidraw
    assets/schema-template.html
  mapping-data-access/
    SKILL.md
    scripts/                   # sqlscan, scan_access, runtime_access, analyze_access, build_access_page, make_access_excalidraw
    assets/access-template.html
test/
  example-url-shortener/       # architecture + demo skills
  example-database-schema/     # database skill (SQLite + BigQuery)
  example-data-access/         # data access skill (monorepo + query logs)
  example-attachment-button/   # demo skill on a public product feature
  example-packaging/           # packaging skill
  example-prompt-compression/  # prompt compression skill
  example-token-audit/         # token audit skill
  example-how-it-works/        # explaining skill, on this repo's own code
```
