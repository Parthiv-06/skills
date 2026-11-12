"""Tools and API plumbing shared by the two example agents. Stdlib only; talks to ANTHROPIC_BASE_URL."""
import json
import os
import urllib.request

COMPONENTS = ["checkout", "search", "auth", "payments", "inbox"]


def read_file(path):
    """The whole bug export: ~40 KB of JSON."""
    bugs = [{"id": 1000 + i, "title": f"{COMPONENTS[i % 5]} request times out under load ({i})",
             "status": "open" if i % 7 == 0 else "closed", "component": COMPONENTS[i % 5],
             "reporter": f"user{i}@example.com", "created": f"2026-10-{1 + i % 28:02d}",
             "body": "Steps: open the page, wait, request hangs for 30s then fails with a timeout error. " * 2}
            for i in range(200)]
    return json.dumps({"path": path, "bugs": bugs})


def search_logs(query):
    """Log lines matching the query: ~6 KB."""
    return "\n".join(f"2026-11-0{1 + i % 9}T10:{i % 60:02d}:00Z db-pool WARN {query}: connection wait exceeded 5000ms "
                     f"(pool=primary active=50/50 waiting={i})" for i in range(60))


TOOLS = [
    {"name": "read_file", "description": "Read a file from the project.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "search_logs", "description": "Search service logs.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]

RUN = {"read_file": lambda a: read_file(a["path"]), "search_logs": lambda a: search_logs(a["query"])}


def call_model(body):
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    req = urllib.request.Request(base + "/v1/messages", data=json.dumps(body).encode(), headers={
        "content-type": "application/json", "anthropic-version": "2023-06-01",
        "x-api-key": os.environ.get("ANTHROPIC_API_KEY", "fake-key")})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def text_of(resp):
    return "".join(b.get("text", "") for b in resp["content"] if b["type"] == "text")


def is_json(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False
