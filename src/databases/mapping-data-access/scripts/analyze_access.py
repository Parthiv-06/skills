"""Merge code evidence and log evidence into one map of who reads and writes each table.
Each link is labeled code + logs, code only, or logs only; views expand to the tables they read."""
USAGE = """Usage:
  python3 analyze_access.py access.json analysis.json [--runtime runtime.json ...] [--schema DB=schema.json ...]

access.json    from scan_access.py
--runtime      from runtime_access.py; repeat for each database. Postgres roles map to services through each
               service's DATABASE_URL user; BigQuery principals map by name (nightly-reports@... -> nightly-reports).
               Anything unmatched is shown as an outside reader or writer.
--schema       analysis.json from the mapping-database-schemas skill, per database (shopdb=shop.analysis.json):
               expands view reads to their base tables, flags unknown tables, and lists untouched ones.

Prints a summary and writes analysis.json for build_access_page.py and make_access_excalidraw.py."""
import json
import re
import sys
from collections import defaultdict


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def analyze(access, runtimes, schemas):
    services = {s["name"]: s for s in access["services"]}
    participants = {n: {"name": n, "kind": s["kind"], "root": s["root"], "db": s["db"], "bigquery": s["bigquery"],
                        "external": False} for n, s in services.items()}
    links = {}

    def link(who, db, table, kind):
        k = (who, db, table, kind)
        if k not in links:
            links[k] = {"participant": who, "database": db, "table": table, "kind": kind, "ops": [],
                        "code": [], "logs": None, "via_view": None}
        return links[k]

    for a in access["accesses"]:
        lk = link(a["service"], a["database"], a["table"], a["kind"])
        if a["op"] not in lk["ops"]:
            lk["ops"].append(a["op"])
        lk["code"].append({k: a[k] for k in ("file", "line", "op", "how", "via")})

    logged_dbs = defaultdict(set)
    for r in runtimes:
        who = None
        if r["principal_kind"] == "db role":
            who = next((n for n, s in services.items() if s["db"] and s["db"].get("role") == r["principal"]
                        and s["db"].get("db") == r["database"]), None)
        else:
            local = r["principal"].split("@")[0]
            who = next((n for n in services if norm(n) == norm(local)), None)
        if not who:
            who = r["principal"].split("@")[0] if r["principal_kind"] != "person" else r["principal"]
            participants.setdefault(who, {"name": who, "kind": r["principal_kind"], "root": None, "db": None,
                                          "bigquery": [], "external": True, "principal": r["principal"]})
        logged_dbs[who].add(r["database"])
        lk = link(who, r["database"], r["table"], r["kind"])
        if r["op"] not in lk["ops"]:
            lk["ops"].append(r["op"])
        logs = lk["logs"] or {"count": 0, "last_seen": None, "source": r["source"], "ops": []}
        logs["count"] += r["count"]
        logs["last_seen"] = max(filter(None, [logs["last_seen"], r["last_seen"]]), default=None)
        if r["op"] not in logs["ops"]:
            logs["ops"].append(r["op"])
        lk["logs"] = logs

    lineage = {}
    for db, sch in schemas.items():
        for v in sch.get("lineage", []):
            lineage[(db, v["view"])] = v["reads"]
    for lk in [x for x in links.values() if x["kind"] == "read"]:
        stack, seen = [(lk["table"], lk["table"])], set()
        while stack:
            name, top = stack.pop()
            for src in lineage.get((lk["database"], name), []):
                if src in seen:
                    continue
                seen.add(src)
                d = link(lk["participant"], lk["database"], src, "read")
                if not d["code"] and not d["logs"]:
                    d["via_view"] = top
                    d["ops"] = ["SELECT"]
                stack.append((src, top))

    for lk in links.values():
        if lk["via_view"] and not lk["code"] and not lk["logs"]:
            lk["label"] = f"via view {lk['via_view']}"
        elif lk["code"] and lk["logs"]:
            lk["label"] = "code + logs"
        elif lk["code"]:
            lk["label"] = "code only"
        else:
            lk["label"] = "logs only"
    ordered = sorted(links.values(), key=lambda x: (x["database"] or "", x["table"], x["kind"], x["participant"]))
    for i, lk in enumerate(ordered, 1):
        lk["id"] = f"L{i}"

    tables = {}
    for lk in ordered:
        t = tables.setdefault((lk["database"], lk["table"]), {
            "id": f"{lk['database']}.{lk['table']}", "database": lk["database"], "name": lk["table"],
            "writers": [], "readers": [], "ddl": [], "kind": "table"})
        role = {"write": "writers", "read": "readers", "ddl": "ddl"}[lk["kind"]]
        if lk["participant"] not in t[role]:
            t[role].append(lk["participant"])
    for db, sch in schemas.items():
        kinds = {x["name"]: x["kind"] for x in sch.get("tables", [])}
        for (tdb, name), t in tables.items():
            if tdb == db:
                t["kind"] = kinds.get(name, "unknown")

    findings = []
    for (db, name), t in sorted(tables.items(), key=lambda x: (x[0][0] or "", x[0][1])):
        tid = t["id"]
        if t["kind"] not in ("table", "unknown"):
            continue
        writers = [w for w in t["writers"]]
        inside = [w for w in writers if not participants[w]["external"]]
        if len(writers) > 1:
            findings.append(("MULTI-WRITER", tid, "written by " + ", ".join(writers) +
                             "; one owner per table keeps its rules in one place"))
        if writers and not inside:
            findings.append(("OUTSIDE-WRITER", tid, "only written from outside this repo by " + ", ".join(writers)))
        if not writers and t["readers"]:
            findings.append(("NO-WRITER", tid, "read by " + ", ".join(t["readers"]) + " but nothing here writes "
                             "it: rows come from another repo, a manual load, or a seed"))
        if writers and not t["readers"]:
            findings.append(("WRITE-ONLY", tid, "written by " + ", ".join(writers) + " and read by nothing seen"
                             + ("" if runtimes else " in code (no logs given)")))
        if t["kind"] == "unknown":
            findings.append(("UNKNOWN-TABLE", tid, "not in the schema given for " + db))
    for db, sch in schemas.items():
        for x in sch.get("tables", []):
            t = tables.get((db, x["name"]))
            if x["kind"] == "table" and (not t or not (t["writers"] or t["readers"])):
                findings.append(("UNTOUCHED", f"{db}.{x['name']}", "no service reads or writes it" +
                                 (" (only migrations change it)" if t and t["ddl"] else "")))
    for lk in ordered:
        p = participants[lk["participant"]]
        if lk["label"] == "code only" and lk["database"] in logged_dbs.get(lk["participant"], set()):
            findings.append(("CODE-ONLY", f"{lk['participant']} -> {lk['database']}.{lk['table']}",
                             f"{lk['kind']} in code but not in the logs: a dead path, or too rare to show"))
        if lk["label"] == "logs only" and not p["external"]:
            findings.append(("LOGS-ONLY", f"{lk['participant']} -> {lk['database']}.{lk['table']}",
                             f"{lk['kind']} seen in the logs but not found in code: dynamic SQL or another codebase"))
    names = defaultdict(set)
    for db, name in tables:
        names[name].add(db)
    for name, dbs in names.items():
        if len(dbs) > 1:
            findings.append(("SAME-NAME", name, "exists in " + " and ".join(sorted(dbs)) + "; they are different "
                             "tables, never mix them up"))
    for u in access.get("unresolved", []):
        if u.get("resolved_by"):
            continue
        findings.append(("DYNAMIC-SQL", f"{u['file']}:{u['line']}", f"{u['op']} on a table chosen at run time: "
                         f"{u['sql']}"))
    for u in access.get("unused_library", []):
        findings.append(("UNUSED-LIBRARY", u.split(" ")[0], "library code touches " + u.split(" ", 2)[2] +
                         " but no service calls it"))

    flows = []
    for t in tables.values():
        readers = [r for r in t["readers"] if r not in t["writers"]]
        if t["writers"] and readers:
            flows.append({"table": t["id"], "writers": t["writers"], "readers": readers})
    return {"root": access["root"], "participants": list(participants.values()), "tables": list(tables.values()),
            "links": ordered, "flows": flows, "unresolved": access.get("unresolved", []),
            "logs_given": bool(runtimes), "schemas": sorted(schemas),
            "findings": [{"kind": k, "where": w, "detail": d} for k, w, d in findings]}


def summary(r):
    inside = [p for p in r["participants"] if not p["external"]]
    lines = [f"# {len(inside)} services, {len(r['participants']) - len(inside)} outside participants, "
             f"{len(r['tables'])} tables, {len(r['links'])} links", ""]
    for p in r["participants"]:
        mine = [lk for lk in r["links"] if lk["participant"] == p["name"]]
        lines.append(f"## {p['name']}{' (outside the repo, ' + p['kind'] + ')' if p['external'] else ''}")
        for kind in ("write", "read", "ddl"):
            items = [f"{lk['database']}.{lk['table']} [{'/'.join(lk['ops'])}; {lk['label']}]" if kind != "read"
                     else f"{lk['database']}.{lk['table']} [{lk['label']}]" for lk in mine if lk["kind"] == kind]
            if items:
                lines.append(f"  {kind}: " + ", ".join(items))
    lines += ["", "Flows (written by one, read by another):"]
    lines += [f"- {f['table']}: {', '.join(f['writers'])} -> {', '.join(f['readers'])}" for f in r["flows"]]
    lines += ["", "Findings:"] + [f"- {f['kind']} {f['where']}: {f['detail']}" for f in r["findings"]]
    return "\n".join(lines)


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    runtimes, schemas, i = [], {}, 2
    while i < len(a):
        if a[i] == "--runtime":
            runtimes += json.load(open(a[i + 1]))
        elif a[i] == "--schema":
            db, path = a[i + 1].split("=", 1)
            schemas[db] = json.load(open(path))
        i += 2
    result = analyze(json.load(open(a[0])), runtimes, schemas)
    with open(a[1], "w") as f:
        json.dump(result, f, indent=1)
    print(summary(result))


if __name__ == "__main__":
    main()
