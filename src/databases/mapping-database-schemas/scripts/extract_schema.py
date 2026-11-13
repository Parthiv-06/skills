"""Read a database's tables, columns, keys, indexes, and views into one engine-neutral schema.json.
Read-only, never touches row data; for BigQuery and Postgres it prints the metadata query to run."""
USAGE = """Usage:
  python3 extract_schema.py sqlite DB_FILE                  > schema.json
  python3 extract_schema.py ddl FILE.sql [FILE.sql ...]     > schema.json
  python3 extract_schema.py sql bigquery PROJECT.DATASET    (prints the metadata query)
  python3 extract_schema.py sql postgres [SCHEMA]           (prints the metadata query; default public)
  python3 extract_schema.py meta META.json                  > schema.json

Live BigQuery:  bq query --use_legacy_sql=false --format=json "$(python3 extract_schema.py sql bigquery p.d)" > meta.json
Live Postgres:  psql "$DATABASE_URL" -At -c "$(python3 extract_schema.py sql postgres public)" > meta.json
Both metadata queries read INFORMATION_SCHEMA only; neither scans table data.

ddl understands CREATE TABLE / VIEW / MATERIALIZED VIEW / INDEX and ALTER TABLE ... ADD CONSTRAINT,
from pg_dump, mysqldump, SQLite, and the BigQuery console (backticks, NOT ENFORCED, STRUCT<...>).
Day-sharded tables (events_20261101, events_20261102...) collapse into one logical table events_*."""
import json
import re
import sqlite3
import sys
from collections import defaultdict

IDENT = r'(?:`[^`]+`|"[^"]+"|\[[^\]]+\]|[\w$.]+)'
SHARD = re.compile(r"^(.*_)(\d{8})$")


def bare(name):
    """`acme.analytics.users` -> users; "public"."orders" -> orders. Tables are keyed by bare name."""
    parts = re.findall(r'`([^`]+)`|"([^"]+)"|\[([^\]]+)\]|([^.`"\[\]]+)', name.strip())
    flat = [p for group in parts for p in group if p]
    return ".".join(flat).split(".")[-1]


def table(name, kind="table"):
    return {"name": name, "kind": kind, "columns": [], "primary_key": [], "unique": [], "foreign_keys": [],
            "indexes": [], "sql": None}


def from_sqlite(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    q = lambda sql: db.execute(sql).fetchall()
    out = []
    for name, kind, sql in q("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view') "
                             "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        t = table(name, kind)
        info = q(f'PRAGMA table_info("{name}")')
        pk = sorted((r[5], r[1]) for r in info if r[5])
        t["primary_key"] = [c for _, c in pk]
        t["columns"] = [{"name": r[1], "type": r[2] or "", "nullable": not r[3] and r[1] not in t["primary_key"]}
                        for r in info]
        if kind == "view":
            t["sql"] = re.sub(r"(?is)^\s*CREATE\s+VIEW\s+\S+\s+AS\s+", "", sql or "")
        else:
            fks = defaultdict(list)
            for row in q(f'PRAGMA foreign_key_list("{name}")'):
                fks[row[0]].append(row)
            for rows in fks.values():
                rows.sort(key=lambda r: r[1])
                t["foreign_keys"].append({"columns": [r[3] for r in rows], "ref_table": rows[0][2],
                                          "ref_columns": [r[4] for r in rows if r[4]]})
            for idx in q(f'PRAGMA index_list("{name}")'):
                cols = [r[2] for r in q(f'PRAGMA index_info("{idx[1]}")')]
                t["indexes"].append(cols)
                if idx[2] and cols != t["primary_key"]:
                    t["unique"].append(cols)
        out.append(t)
    by_name = {t["name"]: t for t in out}
    for t in out:
        for fk in t["foreign_keys"]:
            if not fk["ref_columns"] and fk["ref_table"] in by_name:
                fk["ref_columns"] = list(by_name[fk["ref_table"]]["primary_key"])
    return {"source": {"engine": "sqlite", "name": path.split("/")[-1]}, "tables": out, "indexes_known": True}


def strip_comments(sql):
    out, i, quote = [], 0, None
    while i < len(sql):
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
            out.append(ch)
        elif sql.startswith("--", i) or ch == "#" and (i == 0 or sql[i - 1] == "\n"):
            while i < len(sql) and sql[i] != "\n":
                i += 1
            continue
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = len(sql) if end < 0 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def split_top(text, sep):
    """Split on sep outside quotes, parentheses, and STRUCT<...>/ARRAY<...> type brackets."""
    parts, buf, depth, angle, quote = [], [], 0, 0, None
    for i, ch in enumerate(text):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "<" and re.search(r"(STRUCT|ARRAY|MAP)\s*$", "".join(buf[-8:]), re.I):
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        elif ch == sep and depth == 0 and angle == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return parts


def cols_in(text):
    return [bare(c) for c in split_top(text, ",") if c.strip()]


def paren_body(text, start):
    depth = 0
    for i in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return text[start + 1:i], i
    return text[start + 1:], len(text)


def apply_constraint(t, part):
    part = re.sub(rf"(?is)^\s*CONSTRAINT\s+{IDENT}\s+", "", part).strip()
    m = re.match(r"(?is)PRIMARY\s+KEY\s*\((.*?)\)", part)
    if m:
        t["primary_key"] = cols_in(m.group(1))
        return True
    m = re.match(rf"(?is)FOREIGN\s+KEY\s*\((.*?)\)\s*REFERENCES\s+({IDENT})\s*(?:\((.*?)\))?", part)
    if m:
        t["foreign_keys"].append({"columns": cols_in(m.group(1)), "ref_table": bare(m.group(2)),
                                  "ref_columns": cols_in(m.group(3) or "")})
        return True
    m = re.match(rf"(?is)UNIQUE(?:\s+(?:KEY|INDEX))?(?:\s+{IDENT})?\s*\((.*?)\)", part)
    if m:
        t["unique"].append(cols_in(m.group(1)))
        t["indexes"].append(cols_in(m.group(1)))
        return True
    m = re.match(rf"(?is)(?:KEY|INDEX)(?:\s+{IDENT})?\s*\((.*?)\)", part)
    if m:
        t["indexes"].append(cols_in(m.group(1)))
        return True
    return bool(re.match(r"(?is)(CHECK|EXCLUDE|FULLTEXT|SPATIAL)\b", part))


def add_column(t, part):
    m = re.match(rf"(?is)\s*({IDENT})\s+(.*)", part)
    if not m:
        return
    name, rest = bare(m.group(1)), m.group(2)
    stop = re.search(r"(?i)\b(NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|REFERENCES|DEFAULT|CHECK|CONSTRAINT|"
                     r"OPTIONS|COLLATE|GENERATED|AUTO_INCREMENT|AUTOINCREMENT|COMMENT)\b", rest)
    ctype = (rest[:stop.start()] if stop else rest).strip()
    t["columns"].append({"name": name, "type": ctype, "nullable": not re.search(r"(?i)NOT\s+NULL|PRIMARY\s+KEY", rest)})
    if re.search(r"(?i)PRIMARY\s+KEY", rest):
        t["primary_key"] = [name]
    if re.search(r"(?i)\bUNIQUE\b", rest):
        t["unique"].append([name])
    ref = re.search(rf"(?is)REFERENCES\s+({IDENT})\s*(?:\((.*?)\))?", rest)
    if ref:
        t["foreign_keys"].append({"columns": [name], "ref_table": bare(ref.group(1)),
                                  "ref_columns": cols_in(ref.group(2) or "")})


def from_ddl(paths):
    text = "\n".join(open(p, encoding="utf-8", errors="replace").read() for p in paths)
    engine = "bigquery" if re.search(r"(?i)`[\w-]+\.[\w-]+\.[\w-]+`|\bINT64\b|\bSTRING\b|NOT\s+ENFORCED", text) \
        else "ddl"
    tables, order = {}, []
    for stmt in split_top(strip_comments(text), ";"):
        s = stmt.strip()
        m = re.match(rf"(?is)CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+|EXTERNAL\s+|UNLOGGED\s+)?TABLE\s+"
                     rf"(?:IF\s+NOT\s+EXISTS\s+)?({IDENT})\s*\(", s)
        if m:
            t = table(bare(m.group(1)))
            body, _ = paren_body(s, m.end() - 1)
            for part in split_top(body, ","):
                if part.strip() and not apply_constraint(t, part):
                    add_column(t, part)
            tables[t["name"]] = t
            order.append(t["name"])
            continue
        m = re.match(rf"(?is)CREATE\s+(?:OR\s+REPLACE\s+)?(MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                     rf"({IDENT})(?:\s*\([^)]*\))?\s+(?:OPTIONS\s*\(.*?\)\s*)?AS\s+(.*)", s)
        if m:
            t = table(bare(m.group(2)), "materialized view" if m.group(1) else "view")
            t["sql"] = m.group(3).strip()
            tables[t["name"]] = t
            order.append(t["name"])
            continue
        m = re.match(rf"(?is)CREATE\s+(UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
                     rf"(?:{IDENT}\s+)?ON\s+(?:ONLY\s+)?({IDENT})\s*(?:USING\s+\w+\s*)?\((.*?)\)", s)
        if m and bare(m.group(2)) in tables:
            cols = cols_in(m.group(3))
            tables[bare(m.group(2))]["indexes"].append(cols)
            if m.group(1):
                tables[bare(m.group(2))]["unique"].append(cols)
            continue
        m = re.match(rf"(?is)ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?({IDENT})\s+ADD\s+(.*)", s)
        if m and bare(m.group(1)) in tables:
            apply_constraint(tables[bare(m.group(1))], m.group(2))
    out = [tables[n] for n in order]
    for t in out:
        for fk in t["foreign_keys"]:
            ref = tables.get(fk["ref_table"])
            if not fk["ref_columns"] and ref:
                fk["ref_columns"] = list(ref["primary_key"])
        if t["primary_key"]:
            t["indexes"].append(list(t["primary_key"]))
    return {"source": {"engine": engine, "name": ", ".join(p.split("/")[-1] for p in paths)}, "tables": out,
            "indexes_known": engine != "bigquery"}


BIGQUERY_SQL = """SELECT
  (SELECT TO_JSON_STRING(ARRAY_AGG(STRUCT(table_name, table_type,
      IF(table_type = 'MATERIALIZED VIEW', ddl, NULL) AS ddl)))
   FROM `{d}.INFORMATION_SCHEMA.TABLES`) AS tables,
  (SELECT TO_JSON_STRING(ARRAY_AGG(STRUCT(table_name, column_name, ordinal_position, is_nullable, data_type)
      ORDER BY table_name, ordinal_position))
   FROM `{d}.INFORMATION_SCHEMA.COLUMNS`) AS columns,
  (SELECT TO_JSON_STRING(ARRAY_AGG(DISTINCT FORMAT('%t', STRUCT(tc.table_name, tc.constraint_name,
      tc.constraint_type, k.column_name, k.ordinal_position, k.position_in_unique_constraint, c.table_name)))))
   FROM `{d}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS` tc
   JOIN `{d}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE` k
     ON k.constraint_name = tc.constraint_name AND k.table_name = tc.table_name
   LEFT JOIN `{d}.INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE` c
     ON tc.constraint_type = 'FOREIGN KEY' AND c.constraint_name = tc.constraint_name) AS keys_tuples,
  (SELECT TO_JSON_STRING(ARRAY_AGG(STRUCT(table_name, view_definition)))
   FROM `{d}.INFORMATION_SCHEMA.VIEWS`) AS views"""

POSTGRES_SQL = """SELECT json_build_object(
  'tables', (SELECT json_agg(json_build_object('table_name', table_name, 'table_type', table_type))
             FROM information_schema.tables WHERE table_schema = '{s}'),
  'columns', (SELECT json_agg(json_build_object('table_name', table_name, 'column_name', column_name,
                'ordinal_position', ordinal_position, 'is_nullable', is_nullable, 'data_type', data_type)
                ORDER BY table_name, ordinal_position)
              FROM information_schema.columns WHERE table_schema = '{s}'),
  'keys', (SELECT json_agg(json_build_object('table_name', tc.table_name, 'constraint_name', tc.constraint_name,
             'constraint_type', tc.constraint_type, 'column_name', kcu.column_name,
             'ordinal_position', kcu.ordinal_position, 'ref_table', ref.table_name, 'ref_column', ref.column_name))
           FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
             AND kcu.constraint_schema = tc.constraint_schema AND kcu.table_name = tc.table_name
           LEFT JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name
             AND rc.constraint_schema = tc.constraint_schema
           LEFT JOIN information_schema.key_column_usage ref ON ref.constraint_name = rc.unique_constraint_name
             AND ref.constraint_schema = rc.unique_constraint_schema
             AND ref.ordinal_position = kcu.position_in_unique_constraint
           WHERE tc.table_schema = '{s}' AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')),
  'views', (SELECT json_agg(json_build_object('table_name', table_name, 'view_definition', view_definition))
            FROM information_schema.views WHERE table_schema = '{s}'),
  'matviews', (SELECT json_agg(json_build_object('table_name', matviewname, 'view_definition', definition))
               FROM pg_matviews WHERE schemaname = '{s}'),
  'indexes', (SELECT json_agg(json_build_object('table_name', t.relname, 'columns',
                (SELECT json_agg(a.attname ORDER BY k.ord) FROM unnest(ix.indkey) WITH ORDINALITY k(attnum, ord)
                 JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum)))
              FROM pg_index ix JOIN pg_class t ON t.oid = ix.indrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace WHERE n.nspname = '{s}')
)"""


def parse_tuple(text):
    """BigQuery FORMAT('%t') row -> list of fields; NULL becomes None."""
    fields = [f.strip() for f in text.strip("()").split(",")]
    return [None if f == "NULL" else f for f in fields]


def from_meta(path):
    raw = json.load(open(path))
    row = raw[0] if isinstance(raw, list) else raw
    meta = {k: (json.loads(v) if isinstance(v, str) else v) or [] for k, v in row.items()}
    engine = "bigquery" if "keys_tuples" in meta else "postgres"
    tables = {}
    for r in meta.get("tables", []):
        kind = {"VIEW": "view", "MATERIALIZED VIEW": "materialized view"}.get(r["table_type"], "table")
        tables[r["table_name"]] = table(r["table_name"], kind)
        if r.get("ddl"):
            tables[r["table_name"]]["sql"] = re.sub(r"(?is)^.*?\bAS\s+", "", r["ddl"], count=1)
    for r in meta.get("matviews", []):
        tables.setdefault(r["table_name"], table(r["table_name"], "materialized view"))["sql"] = r["view_definition"]
    for r in meta.get("columns", []):
        t = tables.setdefault(r["table_name"], table(r["table_name"]))
        t["columns"].append({"name": r["column_name"], "type": r["data_type"], "nullable": r["is_nullable"] == "YES"})
    for r in meta.get("views", []):
        tables.setdefault(r["table_name"], table(r["table_name"], "view"))["sql"] = r["view_definition"]
    keys = meta.get("keys", [])
    if engine == "bigquery":
        names = ["table_name", "constraint_name", "constraint_type", "column_name", "ordinal_position",
                 "position_in_unique_constraint", "ref_table"]
        keys = [dict(zip(names, parse_tuple(t))) for t in meta.get("keys_tuples", [])]
    groups = defaultdict(list)
    for k in keys:
        groups[(k["table_name"], k["constraint_name"], k["constraint_type"])].append(k)
    fk_groups = []
    for (tname, _, ctype), rows in groups.items():
        rows.sort(key=lambda r: int(r["ordinal_position"]))
        cols = [r["column_name"] for r in rows]
        t = tables.setdefault(tname, table(tname))
        if ctype == "PRIMARY KEY":
            t["primary_key"] = cols
        elif ctype == "UNIQUE":
            t["unique"].append(cols)
        else:
            fk_groups.append((t, rows))
    for t, rows in fk_groups:
        ref = rows[0]["ref_table"]
        ref_pk = tables.get(ref, {}).get("primary_key", [])
        if rows[0].get("ref_column"):
            ref_cols = [r["ref_column"] for r in rows]
        else:
            ref_cols = [ref_pk[int(r["position_in_unique_constraint"]) - 1] if r.get("position_in_unique_constraint")
                        and int(r["position_in_unique_constraint"]) <= len(ref_pk) else None for r in rows]
            ref_cols = ref_cols if None not in ref_cols else list(ref_pk)
        t["foreign_keys"].append({"columns": [r["column_name"] for r in rows], "ref_table": ref,
                                  "ref_columns": ref_cols})
    for r in meta.get("indexes", []):
        if r["table_name"] in tables and r.get("columns"):
            tables[r["table_name"]]["indexes"].append(r["columns"])
    return {"source": {"engine": engine, "name": path.split("/")[-1]}, "tables": list(tables.values()),
            "indexes_known": engine == "postgres"}


def collapse_shards(schema):
    """events_20261101..03 with the same columns -> one table events_* that records its shard range."""
    groups = defaultdict(list)
    for t in schema["tables"]:
        m = SHARD.match(t["name"])
        if m and t["kind"] == "table":
            groups[m.group(1)].append((m.group(2), t))
    drop = set()
    for prefix, members in groups.items():
        shapes = {json.dumps([(c["name"], c["type"]) for c in t["columns"]]) for _, t in members}
        if len(members) < 2 or len(shapes) > 1:
            continue
        members.sort(key=lambda x: x[0])
        merged = dict(members[0][1], name=prefix + "*",
                      shards={"count": len(members), "first": members[0][0], "last": members[-1][0]})
        schema["tables"][schema["tables"].index(members[0][1])] = merged
        drop |= {id(t) for _, t in members[1:]}
    schema["tables"] = [t for t in schema["tables"] if id(t) not in drop]
    return schema


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    if a[0] == "sql":
        if a[1] == "bigquery" and len(a) > 2:
            print(BIGQUERY_SQL.format(d=a[2]))
        elif a[1] == "postgres":
            print(POSTGRES_SQL.format(s=a[2] if len(a) > 2 else "public"))
        else:
            sys.exit(USAGE)
        return
    loaders = {"sqlite": lambda: from_sqlite(a[1]), "ddl": lambda: from_ddl(a[1:]), "meta": lambda: from_meta(a[1])}
    if a[0] not in loaders:
        sys.exit(USAGE)
    print(json.dumps(collapse_shards(loaders[a[0]]()), indent=1))


if __name__ == "__main__":
    main()
