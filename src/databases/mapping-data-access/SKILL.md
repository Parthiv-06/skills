---
name: mapping-data-access
description: Use when asked which services, jobs, or scripts in a Python codebase read or write which database tables; who owns or depends on a table; what breaks if a table changes; or how data flows between services and databases (Postgres, BigQuery, SQLite), including from query logs.
---

# Mapping Data Access

**Core principle:** every read and write carries its evidence (`file:line` from code, counts from query logs) and a label that says which: `code + logs`, `code only`, `logs only`, or `via view`. The scripts find the access; you explain it. Never add a link the analysis doesn't contain.

**Output:** two files with the same name: `<name>.html` (explanation only, no diagrams) and `<name>.excalidraw` (the diagram).

## Process

All scripts are in this skill's `scripts/`.

1. **Scan the code:** `python3 scan_access.py REPO access.json`. Check the services it prints against the repo (it reads docker-compose, Dockerfiles, and alembic.ini). Read every UNRESOLVED line. If the code makes the table obvious, say so in `notes`; don't guess.
2. **Add query logs if the user has them** (ask before running anything against a database; both queries read metadata only):

| Database | Get the logs | Turn them into evidence |
|---|---|---|
| BigQuery | `bq query --use_legacy_sql=false --format=json "$(python3 runtime_access.py sql bigquery PROJECT REGION 30)" > jobs.json` | `python3 runtime_access.py parse bigquery jobs.json > rt_bq.json` |
| Postgres | `psql "$DATABASE_URL" -At -c "$(python3 runtime_access.py sql postgres)" > stats.json` | `python3 runtime_access.py parse postgres stats.json DBNAME > rt_pg.json` |

3. **Add the schema if you can** (it expands view reads and lists untouched tables). Use the mapping-database-schemas skill's `extract_schema.py` and `analyze_schema.py` for each database.
4. **Analyze:** `python3 analyze_access.py access.json analysis.json [--runtime rt_pg.json --runtime rt_bq.json] [--schema shopdb=shop.analysis.json]`. The summary lists every participant, link, flow, and finding.
5. **Write `page.json`** (contract below), from the code and the summary.
6. **Build the page:** `python3 build_access_page.py analysis.json page.json <name>.html`. Fix every error it lists.
7. **Draw:** `python3 make_access_excalidraw.py analysis.json page.json <name>.excalidraw`. Quote its self-check line in your reply.
8. **Hand over:** publish the page with the Artifact tool if you have it (icon `database`), and give the `.excalidraw` path (open at excalidraw.com, menu, Open).

## page.json contract

```json
{"title": "shopco: who reads and writes what",
 "summary": "Two sentences: the services, the databases, and the one thing to worry about most.",
 "services": {"checkout-api": {"what": "Takes orders and card payments for the web shop."}},
 "outside": {"crm_sync": {"what": "A Postgres role from outside this repo, likely the CRM sync, that keeps customers up to date."}},
 "tables": {"shopdb.orders": {"what": "One checkout by a customer, with its status."}},
 "flows": {"shopdb.orders": "checkout-api and fulfilment-worker write orders; admin-api and nightly-reports read them, so a status change in either writer reaches both readers."},
 "notes": ["Anything the scripts can't see: a column read but never written, or a doubt about a log window."]}
```

- **Every service, outside participant, and table** gets a `what`, written from its code or its name, in plain words.
- **Every flow sentence** names each writer and each reader (the build checks this) and says what a reader would feel if the writer changed.
- **Outside participants** are described as what they probably are, with "likely" when you can't confirm it.

## Common mistakes

| Mistake | Fix |
|---|---|
| Crediting a shared library's writes to every service that imports it | The scan follows actual calls; trust it over the import list |
| Guessing the table behind dynamic SQL | Keep it unresolved unless a call site or the logs show it |
| Calling a CODE-ONLY link dead | It wasn't seen in the log window; say "not seen in N days", not "dead" |
| Treating a logs-only principal as a repo service | It is outside the repo; describe it as such |
| Merging same-name tables from two databases | `shopdb.orders` and `acme.shop.orders` are different tables |
| Placing boxes or drawing arrows by hand | The generator lays out and self-checks |
