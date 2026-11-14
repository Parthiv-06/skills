# Tracing checklist

A trace is finished when every hop has both ends located (file:line), every branch ends somewhere, every external call has a card, and every write is listed. Work through each layer the path touches.

## Finding the start
- **UI action:** the component and its event handler, then the client call (`fetch`, an SDK, a server action, a form post).
- **HTTP request:** the router (Next.js `app/**/route.ts`, Express `app.post`, FastAPI decorators, Django `urls.py`, Rails `routes.rb`), then the middleware chain.
- **Background work:** the cron or scheduler definition (`vercel.json`/`vercel.ts` crons, Celery beat, Sidekiq, GitHub Actions `schedule`), and the queue consumer registration.
- **Incoming webhook:** the route it hits, and where its signature is verified.
- **CLI:** the entry point (`__main__`, `bin`, `package.json` scripts).

## Following each hop
- **Auth and permissions:** which middleware, guard, or decorator runs; what it checks; what happens on failure (status code, redirect).
- **Validation:** schemas (zod, pydantic, serializers), and what invalid input produces.
- **Business logic:** follow calls into services and helpers until the path does I/O or returns. Skip trivial helpers; record any that change data or make decisions.
- **Data:**
  - each read and write, with table, collection, or key, and the query or ORM call
  - transactions and their boundaries, locks, unique constraints that act as idempotency
  - caches: the key, TTL, and how they are invalidated
- **Async:**
  - every `enqueue` or `publish`, and **follow it to its consumer**: the consumer is part of the path
  - retries, backoff, dead-letter handling, ordering guarantees
- **External calls:** fill a card for each (below).
- **Response:** what goes back and in what shape; what the UI does with it (loading, success, and error states).
- **Branches:** every `if`, `catch`, early return, or status check on the path. Each one ends at a response, a retry, a log, or a crash. Write down which.
- **Config:** env vars, feature flags, and per-environment branches read along the path.
- **Observability:** logs, metrics, and traces emitted, and their names. These go in "How to debug it".
- **Tests:** tests that exercise the path. Name them in "How to debug it".

## External service card
Every `external` element in any diagram needs a card with `id` equal to the element's id:

| Field | Contents |
|---|---|
| `name`, `purpose` | What it is and why this path needs it |
| `interface` | SDK call or endpoint, and the format (JSON, SSE, gRPC, SMTP…) |
| `auth` | API key, OAuth, or signed requests; where the secret is stored (env var name) |
| `sends` | Exactly what data leaves your system. Call out personal or payment data |
| `limits` | Timeouts, retries, idempotency keys, rate limits, quotas, cost per call if relevant |
| `callbacks` | Webhooks or redirects back, and how they're verified |
| `whenDown` | What the user sees and what the code does when it fails or is slow |
| `evidence` | file:line for each fact, plus the provider's docs URL for facts the code can't show |

Write `unknown: <why>` instead of guessing.

## Status of each trace row
- `verified`: you read both ends in the code.
- `observed`: you also saw it happen (tests, logs, a local run).
- `inferred`: you could not find it in the code. Give the reason in the row's `how`, and list it under open questions.

## When the path is huge
- Explain the main path in full.
- List side paths (admin tools, rare branches) in open questions as "not traced".
- For a whole-system question, trace the 1–3 paths that matter most, and say which ones you chose and why.
