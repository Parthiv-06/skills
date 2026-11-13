"""Merge analysis.json (facts) with page.json (plain-language explanations) into the schema page.
Refuses to build if a table, view, or connection is unexplained, or a join path uses a missing link."""
USAGE = """Usage:
  python3 build_schema_page.py analysis.json page.json OUT.html

page.json (the contract is in ../SKILL.md):
  title, summary                              strings
  domains: [{name, about, tables: [...]}]      every table in exactly one domain
  tables: {name: {what, grain, columns: {col: note}}}   every table and view; grain for tables
  relationships: {R1: "sentence", ...}         every relationship id from analysis.json
  views: {name: {answers}}                     every view
  joinPaths: [{question, path: [t1, t2, ...], rels: [R.., ...]?}]   rels only where a hop is ambiguous
  notes: ["..."]                               optional extra findings in plain words"""
import html
import json
import os
import re
import sys

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "schema-template.html")
HEDGE = re.compile(r"\b(appears?|likely|probably|seems?|inferred|looks? like|assum|not declared|by name|"
                   r"unconfirmed|guess|check)", re.I)


def quote(name):
    return f"`{name}`" if re.search(r"[^\w]", name) else name


def check_and_merge(an, page):
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    for k in ("title", "summary"):
        need(isinstance(page.get(k), str) and page[k].strip(), f"{k}: required string")
    tables = {t["name"]: t for t in an["tables"]}
    real = [n for n, t in tables.items() if t["kind"] == "table"]
    views = [n for n, t in tables.items() if t["kind"] != "table"]
    seen = {}
    for d in page.get("domains", []):
        need(d.get("name") and d.get("about"), f"domains: each needs name and about ({d.get('name')})")
        for n in d.get("tables", []):
            need(n in tables, f"domains.{d.get('name')}: unknown table {n}")
            need(n not in seen, f"domains: {n} is in both {seen.get(n)} and {d.get('name')}")
            seen[n] = d.get("name")
    for n in real:
        need(n in seen, f"domains: table {n} is in no domain")
    texts = page.get("tables", {})
    for n in real + views:
        t = texts.get(n, {})
        need(t.get("what"), f"tables.{n}.what: say what one row is about, in plain words")
        if n in real:
            need(t.get("grain"), f"tables.{n}.grain: 'One row per ...'")
    for n in texts:
        need(n in tables, f"tables.{n}: not in analysis.json")
    sentences = page.get("relationships", {})
    for r in an["relationships"]:
        s = sentences.get(r["id"], "")
        need(s, f"relationships.{r['id']} ({r['from']}.{r['from_columns'][0]} -> {r['to']}): plain-language sentence")
        if s and r["confidence"] != "declared":
            need(HEDGE.search(s), f"relationships.{r['id']}: is {r['label']}, so the sentence must say so "
                                  "(e.g. 'appears to', 'likely', 'not declared')")
    for v in views:
        need(page.get("views", {}).get(v, {}).get("answers"), f"views.{v}.answers: what question it answers")

    links = {}
    for r in an["relationships"]:
        links.setdefault(frozenset((r["from"], r["to"])), []).append(r)
    paths = []
    for i, jp in enumerate(page.get("joinPaths", [])):
        path, picks = jp.get("path", []), list(jp.get("rels") or [])
        need(jp.get("question") and len(path) >= 2, f"joinPaths[{i}]: needs question and a path of 2+ tables")
        hops, sql = [], f"FROM {quote(path[0])}" if path else ""
        for a, b in zip(path, path[1:]):
            options = links.get(frozenset((a, b)), [])
            if not options:
                need(False, f"joinPaths[{i}]: no relationship between {a} and {b}")
                continue
            chosen = options[0]
            if len(options) > 1:
                ids = [r["id"] for r in options]
                pick = next((p for p in picks if p in ids), None)
                need(pick, f"joinPaths[{i}]: {a}-{b} has {len(options)} links ({', '.join(ids)}); list one in rels")
                chosen = next((r for r in options if r["id"] == pick), options[0])
            on = chosen["join"]
            for name in {chosen["from"], chosen["to"]}:
                on = re.sub(rf"(?<![\w`]){re.escape(name)}\.", f"{quote(name)}.", on)
            hops.append({"rel": chosen["id"], "label": chosen["label"]})
            sql += f"\nJOIN {quote(b)} ON {on}"
        paths.append({"question": jp.get("question", ""), "path": path, "hops": hops, "sql": sql})
    need(len(paths) >= 2 or len(real) < 3, "joinPaths: give at least 2 common questions with their path")
    if errs:
        return None, errs

    rels = []
    for r in an["relationships"]:
        rels.append(dict(r, sentence=sentences[r["id"]]))
    out = {
        "title": page["title"], "summary": page["summary"], "source": an["source"],
        "domains": [dict(d) for d in page.get("domains", [])],
        "tables": [], "relationships": rels, "manyToMany": an["many_to_many"], "joinPaths": paths,
        "findings": an["findings"], "notes": page.get("notes", []),
        "stats": {"tables": len(real), "views": len(views), "links": len(rels),
                  "declared": sum(r["confidence"] == "declared" for r in rels),
                  "inferred": sum(r["confidence"] == "inferred" for r in rels),
                  "guess": sum(r["confidence"] == "guess" for r in rels)},
    }
    for n in real + views:
        t, words = tables[n], texts.get(n, {})
        notes = words.get("columns", {})
        out["tables"].append({
            "name": n, "kind": t["kind"], "domain": seen.get(n, "Views" if n in views else "Other"),
            "what": words.get("what", ""), "grain": words.get("grain", ""), "answers":
            page.get("views", {}).get(n, {}).get("answers", ""), "pk": t["primary_key"], "pkSource": t["pk_source"],
            "junction": t.get("junction", False), "shards": t.get("shards"), "reads": t.get("reads", []),
            "joins": t.get("joins", []),
            "columns": [dict(c, pk=c["name"] in t["primary_key"], fk=c["name"] in t.get("fk_columns", []),
                             note=notes.get(c["name"], "")) for c in t["columns"]],
            "out": [r["id"] for r in rels if r["from"] == n], "in": [r["id"] for r in rels if r["to"] == n],
        })
    return out, []


def main():
    a = sys.argv[1:]
    if len(a) != 3 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    data, errs = check_and_merge(json.load(open(a[0])), json.load(open(a[1])))
    if errs:
        sys.exit("page.json is incomplete:\n  " + "\n  ".join(errs))
    with open(TEMPLATE) as f:
        page = f.read()
    blob = json.dumps(data, indent=1, ensure_ascii=False).replace("</", "<\\/")
    with open(a[2], "w") as f:
        f.write(page.replace("{{TITLE}}", html.escape(data["title"])).replace("{{SCHEMA_JSON}}", blob))
    print(f"Wrote {a[2]}: {data['stats']['tables']} tables, {data['stats']['views']} views, "
          f"{data['stats']['links']} connections explained")


if __name__ == "__main__":
    main()
