"""Plain-English gate for Part 1: flags technical words and long sentences in text meant for anyone.
A flagged word passes only when the explainer defines it in plain.terms; matching is whole-word."""
import json
import re
import sys

TECH = """
api apis endpoint endpoints webhook webhooks payload payloads json jsonl xml yaml csv http https rest graphql grpc
sdk sdks cli oauth jwt sso saml auth authn authz token tokens async asynchronous synchronous callback callbacks promise
thread threads threading mutex lock queue queues queued enqueue dequeue cache caches caching cached database databases db
sql nosql query queries schema schemas index indexes backend frontend server servers serverless client-side server-side
proxy proxies middleware microservice microservices container containers docker kubernetes k8s deploy deployed deployment
runtime latency throughput idempotent idempotency encryption encrypted hash hashes hashing sha base64 regex parse parser
parsing serialize serialized deserialize lambda cron cronjob stream streams streaming sse websocket websockets socket tcp
udp dns cdn url urls uri localhost port env config configuration repository repo commit branch merge pipeline orm
migration migrations transaction transactions rollback null boolean string integer array object function functions
method methods class classes module modules library libraries framework frameworks dependency dependencies package
packages npm pip python javascript typescript node nodejs react nextjs html css dom render rendering props instance
instances invoke invoked instantiate polling subprocess daemon exception exceptions stacktrace debug debugger llm llms
inference embedding embeddings vector vectors byte bytes jsonb uuid cors csrf xss tls ssl certificate s3 blob bucket
kafka redis postgres postgresql mysql sqlite mongodb bigquery aws gcp azure vercel cloudflare terraform yaml ci cd
""".split()
MAX_AVG, MAX_ONE = 20, 32


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.split()) >= 2]


def check_plain(texts, terms=()):
    """Problems in the plain-English texts; terms are the words the explainer defines for readers."""
    allowed = {t.lower() for t in terms}
    found, long_ones, sents = {}, [], []
    for text in texts:
        for s in sentences(text):
            sents.append(s)
            n = len(s.split())
            if n > MAX_ONE:
                long_ones.append(f"{n} words: \"{s[:70]}...\"")
            for w in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]*[A-Za-z0-9]|[A-Za-z]", s):
                k = w.lower().rstrip(".")
                if k in TECH and k not in allowed and k.rstrip("s") not in allowed:
                    found.setdefault(k, s[:70])
    problems = [f"technical word \"{w}\" in: \"{s}...\" (say it plainly, or define it in plain.terms)" for w, s in found.items()]
    problems += [f"sentence too long ({MAX_ONE} words max) — {x}" for x in long_ones]
    if sents:
        avg = sum(len(s.split()) for s in sents) / len(sents)
        if avg > MAX_AVG:
            problems.append(f"average sentence is {avg:.1f} words; keep it at {MAX_AVG} or fewer")
    return problems


def plain_texts(plain):
    out = [plain.get("analogy") or ""] + list(plain.get("worth") or [])
    for s in plain.get("steps") or []:
        out += [s.get("title", ""), s.get("see", ""), s.get("behind", "")]
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: check_plain.py EXPLAINER.json")
    with open(sys.argv[1], encoding="utf-8") as f:
        d = json.load(f)
    plain = d.get("plain") or {}
    probs = check_plain(plain_texts(plain) + [d.get("answer", "")], [t.get("term", "") for t in plain.get("terms") or []])
    print("\n".join(probs) if probs else "OK: Part 1 reads as plain English")
    sys.exit(1 if probs else 0)
