"""Turn database query logs into read/write evidence: who touched which table, how often, and when.
Prints the read-only log query to run; never connects to a database itself."""
USAGE = """Usage:
  python3 runtime_access.py sql bigquery PROJECT REGION [DAYS]   prints the JOBS query (default 30 days)
  python3 runtime_access.py sql postgres                         prints the pg_stat_statements query
  python3 runtime_access.py parse bigquery JOBS.json > runtime.json
  python3 runtime_access.py parse postgres STATS.json DATABASE > runtime.json

BigQuery: bq query --use_legacy_sql=false --format=json "$(python3 runtime_access.py sql bigquery p us 30)"
  Needs bigquery.jobs.listAll on the project. Reads job metadata only, not table data.
Postgres: psql "$DATABASE_URL" -At -c "$(python3 runtime_access.py sql postgres)" > stats.json
  Needs the pg_stat_statements extension and pg_read_all_stats. Counts are since the last stats reset."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlscan import tables as sql_tables  # noqa: E402

BQ_SQL = """SELECT user_email AS principal, job_type, statement_type,
  TO_JSON_STRING(ARRAY(SELECT FORMAT('%s.%s.%s', t.project_id, t.dataset_id, t.table_id)
                       FROM UNNEST(referenced_tables) t ORDER BY 1)) AS reads,
  IF(destination_table.dataset_id IS NULL OR STARTS_WITH(destination_table.dataset_id, '_'), NULL,
     FORMAT('%s.%s.%s', destination_table.project_id, destination_table.dataset_id,
            destination_table.table_id)) AS writes,
  COUNT(*) AS jobs, FORMAT_TIMESTAMP('%F %T UTC', MAX(creation_time)) AS last_seen
FROM `{project}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
  AND state = 'DONE' AND error_result IS NULL
GROUP BY principal, job_type, statement_type, reads, writes"""

PG_SQL = """SELECT json_agg(json_build_object('rolname', r.rolname, 'calls', s.calls, 'query', s.query))
FROM pg_stat_statements s
JOIN pg_roles r ON r.oid = s.userid
JOIN pg_database d ON d.oid = s.dbid
WHERE d.datname = current_database()"""

BQ_OPS = {"CREATE_TABLE_AS_SELECT": "CREATE AS", "INSERT": "INSERT", "MERGE": "MERGE", "UPDATE": "UPDATE",
          "DELETE": "DELETE", "TRUNCATE_TABLE": "TRUNCATE", "SELECT": "QUERY RESULT"}


def kind_of(principal):
    if principal.endswith(".gserviceaccount.com"):
        return "service account"
    return "person" if "@" in principal else "db role"


def split3(name):
    parts = name.split(".")
    return (".".join(parts[:-1]), parts[-1]) if len(parts) >= 3 else (None, name)


def parse_bigquery(rows):
    out = []
    for r in rows:
        who, count, seen = r["principal"], int(r.get("jobs") or 1), r.get("last_seen")
        reads = json.loads(r["reads"]) if isinstance(r.get("reads"), str) else (r.get("reads") or [])
        for name in reads:
            db, table = split3(name)
            out.append(dict(principal=who, principal_kind=kind_of(who), database=db, table=table, kind="read",
                            op="SELECT", count=count, last_seen=seen, source="bigquery jobs"))
        if r.get("writes"):
            db, table = split3(r["writes"])
            job = (r.get("job_type") or "").upper()
            op = {"LOAD": "LOAD", "COPY": "COPY"}.get(job) or BQ_OPS.get(r.get("statement_type") or "", "LOAD")
            out.append(dict(principal=who, principal_kind=kind_of(who), database=db, table=table, kind="write",
                            op=op, count=count, last_seen=seen, source="bigquery jobs"))
    return out


def parse_postgres(rows, database):
    out = []
    for r in rows or []:
        for db, table, kind, op in sql_tables(r["query"]):
            if "{}" not in table:
                out.append(dict(principal=r["rolname"], principal_kind="db role", database=db or database,
                                table=table, kind=kind, op=op, count=int(r.get("calls") or 1), last_seen=None,
                                source="pg_stat_statements"))
    return out


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    if a[0] == "sql":
        if a[1] == "bigquery" and len(a) >= 4:
            print(BQ_SQL.format(project=a[2], region=a[3], days=a[4] if len(a) > 4 else 30))
        elif a[1] == "postgres":
            print(PG_SQL)
        else:
            sys.exit(USAGE)
        return
    if a[0] == "parse" and a[1] == "bigquery" and len(a) == 3:
        rows = parse_bigquery(json.load(open(a[2])))
    elif a[0] == "parse" and a[1] == "postgres" and len(a) == 4:
        raw = json.load(open(a[2]))
        rows = parse_postgres(raw[0]["json_agg"] if isinstance(raw, list) and raw and "json_agg" in raw[0] else raw,
                              a[3])
    else:
        sys.exit(USAGE)
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
