"""Find which tables a SQL statement reads and which it writes, with the operation for each write.
Text-level and dialect-tolerant; a {} placeholder in a table slot marks the table unresolved."""
import re

KEYWORD_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|MERGE|WITH|CREATE|TRUNCATE|REPLACE|UPSERT|ALTER|DROP)\b",
                           re.I)
IDENT = r"(`[^`]+`|\"[^\"]+\"|\[[^\]]+\]|\{\}|[A-Za-z_][\w$]*(?:\.(?:`[^`]+`|\"[^\"]+\"|[\w$*]+|\{\}))*)"
NOT_TABLES = {"select", "lateral", "unnest", "values", "dual", "table", "only", "the", "a", "an"}
FUNC_FROM = re.compile(r"(EXTRACT|SUBSTRING|TRIM|OVERLAY|POSITION)\s*\([^()]*$", re.I)


def looks_like_sql(text):
    return bool(KEYWORD_START.match(text or "")) and bool(re.search(r"\b(FROM|INTO|TABLE|SET|USING)\b", text, re.I))


def clean(sql):
    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def split_name(raw):
    """`acme.shop.daily_sales` -> ("acme.shop", "daily_sales"); public.orders -> (None, "orders").
    Other two-part names keep their schema (staging.users) so different tables never merge."""
    parts = [p.strip('`"[]') for p in re.findall(r"`[^`]+`|\"[^\"]+\"|\[[^\]]+\]|\{\}|[^.]+", raw)]
    if len(parts) == 1 and "." in parts[0]:
        parts = parts[0].split(".")
    if len(parts) >= 3:
        return ".".join(parts[-3:-1]), parts[-1]
    if len(parts) == 2 and parts[0].lower() not in ("public", "dbo", "main"):
        return None, ".".join(parts)
    return None, parts[-1]


def tables(sql):
    """List of (database or None, table, kind, op): kind is read / write / ddl; '{}' means unresolved."""
    text = clean(sql)
    out, writes = [], set()
    ctes = {m.group(1).lower() for m in re.finditer(r"(?i)(?:\bWITH\s+(?:RECURSIVE\s+)?|,\s*)(\w+)\s+AS\s*\(", text)}

    def add(raw, kind, op):
        db, name = split_name(raw)
        if name.lower() in ctes or name.lower() in NOT_TABLES:
            return
        out.append((db, name, kind, op))
        if kind != "read":
            writes.add(name)

    upsert = bool(re.search(r"(?i)ON\s+CONFLICT[^;]*DO\s+UPDATE|ON\s+DUPLICATE\s+KEY\s+UPDATE", text))
    for m in re.finditer(rf"(?i)\bINSERT\s+(?:OVERWRITE\s+(?:TABLE\s+)?|INTO\s+|IGNORE\s+INTO\s+)?{IDENT}", text):
        add(m.group(1), "write", "UPSERT" if upsert else "INSERT")
    for m in re.finditer(rf"(?i)\b(?:REPLACE|UPSERT)\s+INTO\s+{IDENT}", text):
        add(m.group(1), "write", "UPSERT")
    for m in re.finditer(rf"(?i)\bUPDATE\s+(?:ONLY\s+)?{IDENT}(?:\s+(?:AS\s+)?\w+)?\s+SET\b", text):
        add(m.group(1), "write", "UPDATE")
    for m in re.finditer(rf"(?i)\bDELETE\s+FROM\s+(?:ONLY\s+)?{IDENT}", text):
        add(m.group(1), "write", "DELETE")
    for m in re.finditer(rf"(?i)\bMERGE\s+(?:INTO\s+)?{IDENT}", text):
        add(m.group(1), "write", "MERGE")
    for m in re.finditer(rf"(?i)\bTRUNCATE\s+(?:TABLE\s+)?{IDENT}", text):
        add(m.group(1), "write", "TRUNCATE")
    for m in re.finditer(rf"(?i)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                         rf"{IDENT}([^;]*?)\bAS\s*(?:\(|SELECT|WITH)", text):
        add(m.group(1), "write", "CREATE AS")
    for m in re.finditer(rf"(?i)\b(CREATE|ALTER|DROP)\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?"
                         rf"(?:MATERIALIZED\s+)?(TABLE|VIEW)\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?{IDENT}", text):
        if (split_name(m.group(3))[1], "write") not in [(o[1], o[2]) for o in out]:
            add(m.group(3), "ddl", f"{m.group(1).upper()} {m.group(2).upper()}")
    delete_targets = {m.group(1).lower() for m in re.finditer(rf"(?i)\bDELETE\s+FROM\s+(?:ONLY\s+)?{IDENT}", text)}
    for m in re.finditer(rf"(?i)\b(FROM|JOIN|USING)\s+{IDENT}", text):
        before = text[max(0, m.start() - 40):m.start()]
        if FUNC_FROM.search(before) or re.match(r"\s*\(", text[m.end():]):
            continue
        if m.group(1).upper() == "FROM" and re.search(r"(?i)\bDELETE\s*$", before):
            continue
        if m.group(2).lower() in delete_targets and re.search(r"(?i)DELETE\s+$", before):
            continue
        add(m.group(2), "read", "SELECT")
    seen, result = set(), []
    for item in out:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
