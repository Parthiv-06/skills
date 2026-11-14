"""Merge analysis.json (who reads and writes what) with page.json (plain words) into the access page.
Refuses to build if a service, outside participant, table, or data flow is left unexplained."""
USAGE = """Usage:
  python3 build_access_page.py analysis.json page.json OUT.html

page.json (the contract is in ../SKILL.md):
  title, summary                       strings
  services: {name: {what}}             every service found in the repo
  outside: {name: {what}}              every reader or writer seen only in the logs
  tables: {database.table: {what}}     every table in the analysis
  flows: {database.table: sentence}    every flow; the sentence names each writer and each reader
  notes: ["..."]                       optional"""
import html
import json
import os
import re
import sys

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "access-template.html")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def check_and_merge(an, page):
    errs = []

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    for k in ("title", "summary"):
        need(isinstance(page.get(k), str) and page[k].strip(), f"{k}: required string")
    for p in an["participants"]:
        group = "outside" if p["external"] else "services"
        need(page.get(group, {}).get(p["name"], {}).get("what"), f"{group}.{p['name']}.what: what it is and does")
    for t in an["tables"]:
        need(page.get("tables", {}).get(t["id"], {}).get("what"), f"tables.{t['id']}.what: what one row is about")
    for f in an["flows"]:
        s = page.get("flows", {}).get(f["table"], "")
        need(s, f"flows.{f['table']}: one sentence: who writes it and who relies on reading it")
        missing = [n for n in f["writers"] + f["readers"] if norm(n) not in norm(s)]
        need(not s or not missing, f"flows.{f['table']}: name every writer and reader (missing {', '.join(missing)})")
    if errs:
        return None, errs
    texts = {**page.get("services", {}), **page.get("outside", {})}
    data = dict(an, title=page["title"], summary=page["summary"], notes=page.get("notes", []), logsGiven=an["logs_given"])
    data["participants"] = [dict(p, what=texts[p["name"]]["what"]) for p in an["participants"]]
    data["tables"] = [dict(t, what=page["tables"][t["id"]]["what"]) for t in an["tables"]]
    data["flows"] = [dict(f, sentence=page["flows"][f["table"]]) for f in an["flows"]]
    return data, []


def main():
    a = sys.argv[1:]
    if len(a) != 3 or a[0] in ("-h", "--help"):
        sys.exit(USAGE)
    data, errs = check_and_merge(json.load(open(a[0])), json.load(open(a[1])))
    if errs:
        sys.exit("page.json is incomplete:\n  " + "\n  ".join(errs))
    page = open(TEMPLATE).read()
    blob = json.dumps(data, indent=1, ensure_ascii=False).replace("</", "<\\/")
    with open(a[2], "w") as f:
        f.write(page.replace("{{TITLE}}", html.escape(data["title"])).replace("{{ACCESS_JSON}}", blob))
    print(f"Wrote {a[2]}: {len(data['participants'])} participants, {len(data['tables'])} tables, "
          f"{len(data['links'])} links, {len(data['flows'])} flows explained")


if __name__ == "__main__":
    main()
