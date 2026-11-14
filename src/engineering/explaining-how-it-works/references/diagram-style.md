# Diagram standard

The diagrams should read like a professional architecture document: black ink on white, clean lines, the same shape for the same kind of thing every time, and a title, level and legend on every view. `scripts/diagrams.py` draws them from a spec, so the job is choosing the right views and describing them well.

## Choosing views

| View | Level tag | Shows | Draw it when |
|---|---|---|---|
| `context` | Level 1 · System context | The system as one box, the people who use it, the external systems it talks to | Always |
| `containers` | Level 2 · Containers | Runnable parts: web app, API, worker, database, queue, cache, external services, with protocols | The path crosses more than one process or service |
| `components` | Level 3 · Components | Inside the one container where the logic lives: modules, handlers, classes | The interesting logic sits in one container |
| `sequence` | Dynamic · Sequence | The path over time, numbered | Always for a start-to-end question. This is the main technical diagram |
| `state` | State | An entity's lifecycle | Something has a status field or lifecycle |
| `data` | Data | Entities touched and how they relate | Several related tables are read or written. For a full schema, use the mapping-database-schemas skill |
| `deployment` | Deployment | Where things run: regions, serverless vs long-running, schedulers, CDN | Infrastructure changes behavior |

- Draw each view once. Going down a level must show something new; never redraw the same level.
- Each view has at most 15 elements; a sequence has at most 10 participants and 32 messages. Past that, split the view: by sub-flow for sequences, or by container for components.

## Kinds

Use the same kind for the same thing in every view.

| kind | Use for | Drawn as |
|---|---|---|
| `person` | A human role | Rounded box, «person» |
| `system` | Your whole system (context view) | Heavy-outline box, «system» |
| `service` | Your app, API, worker, script, or another of your own systems | Box |
| `component` | A module, class, or handler (components view) | Box with the UML component icon |
| `database` | SQL or NoSQL store | Cylinder |
| `queue` | Queue, topic, or stream | Box with end bars, «queue» |
| `cache` | Redis, Memcached, or an in-process cache | Box, «cache» |
| `storage` | Files, object storage, logs on disk | Document with a folded corner |
| `external` | Anything you don't run: SaaS, third-party API, another team's system | Dashed box, «external» |
| `scheduler` | Cron or another timer that starts work | Box, «cron» |
| `state`, `start`, `end` | State view | Rounded box, filled dot, ringed dot |
| `entity` | Data view; put key fields in `fields` | Box with a field list |

## Labels

- Each element has `name` (what the code calls it), `tech` (stack or framework, shown in brackets), and `does` (its job in 4–8 words).
- Each arrow's `label` is a verb or message plus the protocol: `POST /charges · HTTPS`, `OrderPaid · SQS`, `SELECT orders · SQL`, `reads config`.
- Mark async arrows with `"async": true`.
- Put `step` on the arrows of the traced path. Steps are `1`, `2`, `2a`, `2b`… and match the trace table.

## Layout

- Zones become boundaries: `{"id", "label", "trust": true}`. Mark a trust boundary wherever authentication or a network edge sits between the parts.
- Place data left to right in the order it flows: people → entry points → services → data → external.
- The layout is automatic:
  - Columns follow first use; rows follow order within a column.
  - Set `col` and `row` on elements to get a grid where flows run straight. Use them for any view with more than a single row.
  - Zones may span several columns but must not overlap; the script refuses overlapping zones.
- Arrow ends are spread along each side automatically. Boxes in the same row get straight arrows; everything else gets right-angle elbows.
- If the script warns that an arrow passes through a box, move that box with `row` or `col`.

## Box view spec

`context`, `containers`, `components`, `state`, `data`, and `deployment` all use this format:

```json
{"view": "containers", "title": "Containers: card payment", "caption": "One sentence on what this view shows.",
 "zones": [{"id": "web", "label": "Browser"}, {"id": "be", "label": "Our backend (AWS us-east-1)", "trust": true},
           {"id": "stripe", "label": "Stripe"}],
 "elements": [
   {"id": "checkout", "kind": "service", "name": "Checkout page", "tech": "Next.js", "does": "Collects card details", "zone": "web", "col": 0, "row": 0},
   {"id": "api", "kind": "service", "name": "Payments API", "tech": "Node · Express", "does": "Creates and confirms charges", "zone": "be", "col": 1, "row": 0},
   {"id": "db", "kind": "database", "name": "orders", "tech": "Postgres 16", "zone": "be", "col": 1, "row": 1},
   {"id": "stripeapi", "kind": "external", "name": "Stripe API", "tech": "HTTPS", "zone": "stripe", "col": 2, "row": 0}],
 "links": [
   {"from": "checkout", "to": "api", "label": "POST /pay · HTTPS", "step": "2"},
   {"from": "api", "to": "stripeapi", "label": "create PaymentIntent · HTTPS", "step": "3"},
   {"from": "api", "to": "db", "label": "INSERT order · SQL", "step": "4"},
   {"from": "stripeapi", "to": "api", "label": "payment_intent.succeeded · webhook", "async": true, "step": "6"}]}
```

## Sequence spec

```json
{"view": "sequence", "title": "Sequence: paying for an order", "caption": "...",
 "participants": [{"id": "ui", "kind": "service", "name": "Checkout page", "tech": "Next.js"},
                  {"id": "api", "kind": "service", "name": "Payments API", "tech": "Express"},
                  {"id": "stripe", "kind": "external", "name": "Stripe", "tech": "HTTPS"}],
 "messages": [
   {"from": "ui", "to": "api", "label": "POST /pay", "step": "2"},
   {"note": "Idempotency key = order id; safe to retry", "over": "api"},
   {"from": "api", "to": "stripe", "label": "create PaymentIntent", "step": "3"},
   {"from": "stripe", "to": "api", "label": "client_secret", "return": true},
   {"from": "api", "to": "api", "label": "save order (pending)", "step": "4"},
   {"from": "stripe", "to": "api", "label": "payment_intent.succeeded", "async": true, "step": "6"},
   {"from": "api", "to": "ui", "label": "402 card declined", "return": true}],
 "frames": [{"type": "alt", "label": "card accepted", "start": 2, "end": 6, "else": [{"at": 6, "label": "declined"}]}]}
```

- **Messages:** a message `from` and `to` the same participant is a self-call. `return: true` draws a dashed reply with an open head, and `async: true` draws a dashed message.
- **Notes:** a note sits over one participant, or `"over": ["a", "b"]` spans two.
- **Frames:** `start`, `end`, and `else[].at` are indexes into `messages`, counting notes. The types are:
  - `alt`: has at least one `else`
  - `opt`: a single optional block
  - `loop`: retries or iteration
  - `par`: parallel work
- **Steps:** step numbers must never go backwards from top to bottom.
