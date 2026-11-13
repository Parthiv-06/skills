"""Turn schema.json into analysis.json: every key and connection, labeled declared, inferred, or guess.
Inferred links come from names and types only until checked against data (--sqlite or --matches)."""
USAGE = """Usage:
  python3 analyze_schema.py schema.json analysis.json [--sqlite DB] [--matches matches.json]

Prints a markdown summary and writes analysis.json for build_schema_page.py and make_er_excalidraw.py.

Labels on each relationship:
  declared   a real constraint (BigQuery NOT ENFORCED keys count)
  inferred   no constraint; name and type both point to the target
  guess      a type mismatch, or a data check found under 95% of values in the target

--sqlite DB         run each inferred link's match check on a SQLite file (read-only)
--matches FILE      {"R7": 0.98, ...}: match rates you got by running each verify_sql yourself
                    (on BigQuery, dry-run first: these scan the key columns)"""
import json
import re
import sqlite3
import sys
from collections import defaultdict

ID_SUFFIX = re.compile(r"^(.+?)_?(id|key|fk|ref)$", re.I)
POLY_SIBLINGS = ("{}", "{}_type", "{}_table", "{}_kind", "{}_class")
FAMILIES = [("int", r"INT|SERIAL|LONG"), ("string", r"CHAR|TEXT|STRING|CLOB"), ("uuid", r"UUID"),
            ("decimal", r"NUMERIC|DECIMAL|NUMBER|BIGNUMERIC"), ("float", r"FLOAT|DOUBLE|REAL"),
            ("time", r"DATE|TIME"), ("bool", r"BOOL"), ("bytes", r"BLOB|BYTES|BINARY")]


def family(sql_type):
    for fam, pat in FAMILIES:
        if re.search(pat, sql_type or "", re.I):
            return fam
    return (sql_type or "").lower() or "unknown"


def singular(word):
    w = word.rstrip("_*")
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def table_for(stem, by_name):
    for cand in (stem, stem + "s", stem + "es", stem[:-1] + "ies" if stem.endswith("y") else None,
                 stem + "_*", stem + "s_*"):
        if cand and cand in by_name and by_name[cand]["kind"] == "table":
            return cand
    for name, t in by_name.items():
        if t["kind"] == "table" and singular(name) == stem:
            return name
    return None


def col(t, name):
    return next((c for c in t["columns"] if c["name"] == name), None)


def infer_pk(t):
    base = singular(t["name"])
    for cand in (f"{base}_id", "id", f"{t['name'].rstrip('_*')}_id", f"{base}_key", f"{base}id"):
        c = col(t, cand)
        if c:
            return [cand]
    return []


def resolve(column, t, by_name):
    """Target table and role for an id-like column: billing_address_id -> (addresses, 'billing')."""
    m = ID_SUFFIX.match(column)
    if not m:
        return None, None
    words = m.group(1).rstrip("_").split("_")
    for k in range(len(words)):
        target = table_for("_".join(words[k:]), by_name)
        if target:
            return target, "_".join(words[:k]) or None
    return None, None


def view_sources(sql, by_name):
    """Tables and views a view reads, plus its equality join keys, from the SQL text."""
    text = re.sub(r"'(?:[^']|'')*'", "''", sql or "")
    ctes = {m.group(1).lower() for m in re.finditer(r"(?i)(?:WITH|,)\s*(\w+)\s+AS\s*\(", text)}
    aliases, reads = {}, []
    for m in re.finditer(r"(?i)\b(?:FROM|JOIN)\s+\(*\s*(`[^`]+`|\"[^\"]+\"|[\w.*$-]+)(?:\s+(?:AS\s+)?(\w+))?", text):
        raw = m.group(1).strip('`"')
        name = raw.split(".")[-1]
        if name.lower() in ctes or name.upper() in ("SELECT", "WITH", "UNNEST", "LATERAL", "VALUES"):
            continue
        if name not in by_name:
            shard = re.match(r"^(.*_)\d*\*?$", name)
            if shard and shard.group(1) + "*" in by_name:
                name = shard.group(1) + "*"
        alias = m.group(2)
        if alias and alias.upper() not in ("ON", "USING", "WHERE", "GROUP", "LEFT", "RIGHT", "INNER", "FULL",
                                           "CROSS", "JOIN", "ORDER", "LIMIT", "WINDOW", "QUALIFY", "UNION"):
            aliases[alias] = name
        aliases[name] = name
        if name not in reads:
            reads.append(name)
    joins = []
    for m in re.finditer(r"(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)", text):
        left = f"{aliases.get(m.group(1), m.group(1))}.{m.group(2)}"
        right = f"{aliases.get(m.group(3), m.group(3))}.{m.group(4)}"
        if [right, left] not in joins and [left, right] not in joins:
            joins.append([left, right])
    return reads, joins


def grain_draft(t, junction, key=None):
    pk = t["primary_key"] or key or []
    if t["kind"] != "table":
        return "derived (a view): see what it reads"
    if not pk:
        return "unknown: no key, so one row per ? (ask or check the data)"
    names = [singular(re.sub(r"(?i)_?(id|key)$", "", c)) or c for c in pk]
    text = f"one row per {' + '.join(names)} pair" if junction else \
        "one row per " + (singular(t["name"]) if len(pk) == 1 else " + ".join(names))
    if t.get("shards"):
        text += f"; one physical table per day ({t['shards']['count']} shards)"
    return text


def analyze(schema, sqlite_path=None, matches=None):
    tables = schema["tables"]
    by_name = {t["name"]: t for t in tables}
    findings = []
    for t in tables:
        t["pk_source"] = "declared" if t["primary_key"] else "none"
        if not t["primary_key"] and t["kind"] == "table":
            pk = infer_pk(t)
            if pk:
                t["primary_key"], t["pk_source"] = pk, "inferred"
                findings.append(("INFERRED-PK", t["name"], f"no declared key; {pk[0]} looks like it"))
            else:
                findings.append(("NO-PK", t["name"], "no declared or obvious key, so rows can't be told apart"))
        for c in t["primary_key"]:
            if (col(t, c) or {}).get("nullable") and t["pk_source"] == "declared":
                findings.append(("NULLABLE-PK", f"{t['name']}.{c}", "key column allows NULL"))

    rels = []
    for t in tables:
        for fk in t["foreign_keys"]:
            rels.append({"from": t["name"], "from_columns": fk["columns"], "to": fk["ref_table"],
                         "to_columns": fk["ref_columns"], "source": "declared"})
    covered = {(r["from"], c) for r in rels for c in r["from_columns"]}
    for t in tables:
        if t["kind"] != "table":
            continue
        names = {c["name"] for c in t["columns"]}
        for c in t["columns"]:
            if (t["name"], c["name"]) in covered:
                continue
            stem = (ID_SUFFIX.match(c["name"]) or [None, None])[1]
            if stem and c["name"] not in t["primary_key"] and any(s.format(stem) in names - {c["name"]} for s in POLY_SIBLINGS):
                findings.append(("POLYMORPHIC", f"{t['name']}.{c['name']}",
                                 f"points at different tables depending on {stem}; not a foreign key"))
                continue
            target, role = resolve(c["name"], t, by_name)
            if not target or (target == t["name"] and c["name"] in t["primary_key"]):
                continue
            tt = by_name[target]
            to_cols = tt["primary_key"] if len(tt["primary_key"]) == 1 else \
                [c["name"]] if col(tt, c["name"]) else []
            if not to_cols:
                continue
            rels.append({"from": t["name"], "from_columns": [c["name"]], "to": target, "to_columns": to_cols,
                         "source": "inferred", "role": role})

    rels.sort(key=lambda r: (r["from"], r["from_columns"]))
    db = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True) if sqlite_path else None
    for i, r in enumerate(rels, 1):
        r["id"] = f"R{i}"
        src, dst = by_name[r["from"]], by_name.get(r["to"])
        r.setdefault("role", None)
        if r["role"] is None and len(r["from_columns"]) == 1:
            stem = re.sub(r"(?i)_?(id|key|fk|ref)$", "", r["from_columns"][0])
            target_stem = singular(r["to"])
            if stem and stem != target_stem and not stem.endswith(target_stem):
                r["role"] = stem
            elif stem.endswith("_" + target_stem):
                r["role"] = stem[: -len(target_stem) - 1]
        r["self"] = r["from"] == r["to"]
        keyset = set(r["from_columns"])
        unique = keyset == set(src["primary_key"]) or any(keyset == set(u) for u in src["unique"])
        r["cardinality"] = "1:1" if unique else "N:1"
        r["optional"] = any((col(src, c) or {}).get("nullable", True) for c in r["from_columns"])
        r["type_mismatch"] = None
        if dst:
            pairs = [(col(src, a), col(dst, b)) for a, b in zip(r["from_columns"], r["to_columns"])]
            bad = [(a["type"], b["type"]) for a, b in pairs if a and b and family(a["type"]) != family(b["type"])]
            if bad:
                r["type_mismatch"] = f"{bad[0][0]} vs {bad[0][1]}"
                findings.append(("TYPE-MISMATCH", f"{r['from']}.{r['from_columns'][0]}",
                                 f"{bad[0][0]} here, {bad[0][1]} in {r['to']}.{r['to_columns'][0]}; "
                                 "the join needs a CAST and may silently match nothing"))
        else:
            findings.append(("UNKNOWN-TARGET", r["from"], f"points to {r['to']}, which is not in this schema"))
        on = " AND ".join(f"c.{a} = p.{b}" for a, b in zip(r["from_columns"], r["to_columns"]))
        cast = "SAFE_CAST" if schema["source"]["engine"] == "bigquery" else "CAST"
        parts = []
        for x, y in zip(r["from_columns"], r["to_columns"]):
            left, target = f"{r['from']}.{x}", col(dst, y) if dst else None
            if r["type_mismatch"] and target:
                left = f"{cast}({left} AS {target['type']})"
            parts.append(f"{left} = {r['to']}.{y}")
        r["join"] = " AND ".join(parts)
        r["verify_sql"] = (f"SELECT COUNT(*) AS total, COUNT(p.{r['to_columns'][0]}) AS matched "
                           f"FROM {r['from']} c LEFT JOIN {r['to']} p ON {on} "
                           f"WHERE c.{r['from_columns'][0]} IS NOT NULL")
        r["match"] = (matches or {}).get(r["id"])
        if db and r["source"] == "inferred" and r["match"] is None and dst:
            try:
                total, matched = db.execute(r["verify_sql"].replace(" p.", " p.")).fetchone()
                r["match"] = round(matched / total, 3) if total else None
            except sqlite3.Error:
                pass
        if r["source"] == "declared":
            r["confidence"] = "declared"
        elif r["type_mismatch"] or (r["match"] is not None and r["match"] < 0.95):
            r["confidence"] = "guess"
        else:
            r["confidence"] = "inferred"
        r["label"] = r["confidence"] if r["match"] is None or r["source"] == "declared" else \
            f"{r['confidence']} · {round(r['match'] * 100)}% match"

    by_from = defaultdict(list)
    for r in rels:
        by_from[r["from"]].append(r)
    m2m = []
    for t in tables:
        if t["kind"] != "table":
            t["junction"], t["grain_draft"] = False, grain_draft(t, False)
            continue
        out = by_from[t["name"]]
        fk_cols = {c for r in out for c in r["from_columns"]}
        key = set(t["primary_key"]) or {c["name"] for c in t["columns"] if not c["nullable"]}
        targets = sorted({r["to"] for r in out if not r["self"]})
        others = [c for c in t["columns"] if c["name"] not in fk_cols]
        t["junction"] = len(targets) >= 2 and key and key <= fk_cols and len(others) <= 2
        if t["junction"]:
            m2m.append({"via": t["name"], "between": targets[:2], "relationships": [r["id"] for r in out]})
        t["grain_draft"] = grain_draft(t, t["junction"], [c["name"] for c in t["columns"] if c["name"] in key & fk_cols])
        if t["junction"] and not t["primary_key"]:
            t["grain_draft"] += " (no declared key; declare one so duplicates can't creep in)"

    lineage = []
    for t in tables:
        if t["kind"] != "table":
            reads, joins = view_sources(t["sql"], by_name)
            t["reads"], t["joins"] = reads, joins
            lineage.append({"view": t["name"], "reads": reads, "joins": joins})
            for name in reads:
                if name not in by_name:
                    findings.append(("VIEW-SOURCE-OUTSIDE", t["name"], f"reads {name}, which is not in this schema"))
    linked = {r["from"] for r in rels} | {r["to"] for r in rels} | {n for v in lineage for n in v["reads"]} | \
        {v["view"] for v in lineage}
    for t in tables:
        if t["name"] not in linked:
            findings.append(("ISOLATED", t["name"], "no key connects it and no view reads it"))
        t["fk_columns"] = sorted({c for r in by_from[t["name"]] for c in r["from_columns"]})

    if schema.get("indexes_known"):
        for r in rels:
            src = by_name[r["from"]]
            if r["source"] == "declared" and not any(ix[:len(r["from_columns"])] == r["from_columns"]
                                                     for ix in src["indexes"] + [src["primary_key"]]):
                findings.append(("UNINDEXED-FK", f"{r['from']}.{', '.join(r['from_columns'])}",
                                 f"joins to {r['to']} and deletes there will scan {r['from']}"))
    inferred = [r for r in rels if r["source"] == "inferred"]
    if inferred:
        findings.append(("UNDECLARED-FK", f"{len(inferred)} links",
                         "work only by naming convention; declare them (BigQuery: NOT ENFORCED) "
                         "so tools and people can trust them"))
    return {"source": schema["source"], "indexes_known": schema.get("indexes_known", False), "tables": tables,
            "relationships": rels, "many_to_many": m2m, "lineage": lineage,
            "findings": [{"kind": k, "where": w, "detail": d} for k, w, d in findings]}


def summary(a):
    t_count = sum(1 for t in a["tables"] if t["kind"] == "table")
    lines = [f"# {a['source']['name']} ({a['source']['engine']}): {t_count} tables, "
             f"{len(a['tables']) - t_count} views, {len(a['relationships'])} relationships", "",
             "| Id | From | To | Label | Card. | Optional | Role |", "|---|---|---|---|---|---|---|"]
    for r in a["relationships"]:
        lines.append(f"| {r['id']} | {r['from']}.{', '.join(r['from_columns'])} | {r['to']}.{', '.join(r['to_columns'])}"
                     f" | {r['label']}{' · TYPE ' + r['type_mismatch'] if r['type_mismatch'] else ''} | "
                     f"{r['cardinality']} | {'yes' if r['optional'] else 'no'} | {r['role'] or '-'} |")
    lines += ["", "Many-to-many: " + ("; ".join(f"{m['between'][0]} <-> {m['between'][1]} via {m['via']}"
                                                for m in a["many_to_many"]) or "none")]
    lines += ["Views: " + ("; ".join(f"{v['view']} <- {', '.join(v['reads'])}" for v in a["lineage"]) or "none")]
    lines += ["", "Tables (key, grain draft):"]
    lines += [f"- {t['name']} [{t['kind']}] key={'+'.join(t['primary_key']) or '-'} ({t['pk_source']}): "
              f"{t['grain_draft']}" for t in a["tables"]]
    lines += ["", "Findings:"] + [f"- {f['kind']} {f['where']}: {f['detail']}" for f in a["findings"]]
    return "\n".join(lines)


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    opts = {k: a[a.index(k) + 1] for k in ("--sqlite", "--matches") if k in a}
    matches = json.load(open(opts["--matches"])) if "--matches" in opts else None
    result = analyze(json.load(open(a[0])), opts.get("--sqlite"), matches)
    with open(a[1], "w") as f:
        json.dump(result, f, indent=1)
    print(summary(result))


if __name__ == "__main__":
    main()
