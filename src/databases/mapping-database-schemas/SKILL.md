---
name: mapping-database-schemas
description: Use when asked to understand, document, explain, or diagram a database schema or dataset (BigQuery, Postgres, SQLite, SQL DDL, dbt or ORM models); when asked how tables connect, what the primary and foreign keys are, what a view is built from, or for an ER diagram.
---

# Mapping Database Schemas

**Core principle:** facts come from the scripts, words come from you. Keys, labels, cardinality, joins, and layout are computed; you explain them. Never state or draw a connection the analysis doesn't contain, and never present an inferred link as declared.

**Output:** two files with the same name: `<name>.html` (explanation only, no diagrams) and `<name>.excalidraw` (the diagram; above 15 tables, an overview plus one file per area).

## Process

1. **Extract** (read-only, from this skill's `scripts/`):

| Source | Command |
|---|---|
| SQLite file | `python3 extract_schema.py sqlite shop.db > schema.json` |
| DDL, pg_dump, mysqldump, BigQuery console export | `python3 extract_schema.py ddl *.sql > schema.json` |
| Live BigQuery | `bq query --use_legacy_sql=false --format=json "$(python3 extract_schema.py sql bigquery PROJECT.DATASET)" > meta.json`, then `python3 extract_schema.py meta meta.json > schema.json` |
| Live Postgres | `psql "$DATABASE_URL" -At -c "$(python3 extract_schema.py sql postgres public)" > meta.json`, then `meta` as above |
| ORM models or dbt | Write the equivalent `CREATE TABLE` DDL from the models, then `ddl` |

2. **Analyze:** `python3 analyze_schema.py schema.json analysis.json [--sqlite shop.db]`. The summary lists every relationship with its label (declared, inferred, guess), cardinality, role, and the findings.
3. **Confirm inferred links with data only after the user says yes.** On BigQuery, dry-run each `verify_sql` and state the bytes first. Put the match rates in `matches.json` (`{"R7": 0.98}`) and re-run with `--matches matches.json`. If a finding is wrong, say so in `notes`; never edit `analysis.json`.
4. **Write `page.json`** (contract below). Learn what tables mean from column names, view SQL, and the code that uses them, never from guessing.
5. **Build the page:** `python3 build_schema_page.py analysis.json page.json <name>.html`. Fix every error it lists.
6. **Draw:** `python3 make_er_excalidraw.py analysis.json page.json <name>.excalidraw`. Quote its self-check line (overlaps, arrows through boxes, crossings) in your reply.
7. **Hand over:** publish the page with the Artifact tool if you have it (icon `database`), and give the `.excalidraw` paths (open at excalidraw.com, menu, Open).

## page.json contract

```json
{"title": "Shop database", "summary": "Two sentences: what the data is about and its main parts.",
 "domains": [{"name": "Orders", "about": "One line.", "tables": ["orders", "order_items"]}],
 "tables": {"orders": {"what": "One checkout by a customer.", "grain": "One row per order.",
                       "columns": {"status": "paid, shipped, ..."}}},
 "relationships": {"R7": "Every order was placed by exactly one customer; a customer can have many orders, or none."},
 "views": {"v_order_totals": {"answers": "What was each order worth?"}},
 "joinPaths": [{"question": "Where was each order shipped?", "path": ["customers", "orders", "addresses"], "rels": ["R8"]}],
 "notes": ["Anything a reader must know that the findings don't say."]}
```

- **Relationship sentences** read in both directions and say whether the link is required or optional: "Each X has exactly one Y; a Y can have many X, or none."
- **Inferred and guess links** say so in the sentence ("appears to", "not declared"). The build rejects them otherwise.
- **Grain** comes from the key, not the table name. A composite key means one row per combination.
- **Domains:** 2 to 7 business areas; every table is in exactly one.
- **Join paths:** 2 to 5 questions people actually ask. Use `rels` to pick a link wherever two tables are joined by more than one.

## Common mistakes

| Mistake | Fix |
|---|---|
| Placing boxes or drawing arrows by hand | The generator lays out and self-checks; hand layouts change meaning from run to run |
| Calling an inferred link a foreign key | The label comes from the analysis, and the sentence must hedge |
| Treating `entity_id` next to `entity` as a foreign key | It is POLYMORPHIC: explain that a join must filter on `entity` first |
| Joining across a type mismatch without saying so | It is labeled guess: name the CAST it needs |
| Running match checks on BigQuery without asking | They scan data: dry-run, show the bytes, wait for yes |
| Listing every date shard as its own table | `events_*` is one logical table; say how many shards and the date range |
| Adding a diagram, or ASCII art, to the page | The page explains; the `.excalidraw` file shows |
