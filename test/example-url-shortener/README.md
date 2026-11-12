# URL Shortener — Architecture

Example output of the `designing-software-architecture` skill.

Files:
- `architecture.excalidraw`: the diagram. Open it at https://excalidraw.com (☰ menu → Open).
- `spec.json`: the input used to generate the diagram. Regenerate with:
  `python3 ../../designing-software-architecture/scripts/make_excalidraw.py spec.json architecture.excalidraw`

## 1. Requirements and assumptions

- Users create short links and are redirected when they open them.
- About 1M redirects/day and 10K new links/day, so reads outnumber writes about 100 to 1.
- A redirect should take under 50 ms, and redirects must keep working.
- A team of two people.

## 2. Ranked priorities

1. Simplicity
2. Fast redirects
3. Low cost

## 3. Diagram

See `architecture.excalidraw`. Text version:

```
User ──GET /abc──▶ Shortener App ──lookup──▶ Redis cache
                        │      └──on miss──▶ Postgres ◀──counts── Stats worker
                        └ ─ click ─ ▶ Click queue ─ ─ consume ─ ─ ▶ ┘
```

Dashed arrows are background (async) steps.

## 4. Key decisions

| Decision | Options | Chosen | Trade-off |
|---|---|---|---|
| App structure | Microservices / single app | **Single app (monolith)** | Easy for two people to run; split it later if needed |
| Storage | DynamoDB / Postgres | **Postgres** | Familiar and cheap; fine at this volume |
| Fast redirects | Database only / Redis cache | **Redis cache** | One more thing to run, but most redirects never touch the database |
| Click counting | Update the count inside each redirect / send to a queue | **Queue** | Click stats show up a few seconds late, but redirects stay fast |

## 5. Risks and open questions

- If Redis goes down, every redirect hits Postgres. Mitigation: a database read replica.
- Short codes could collide. Mitigation: a unique constraint plus a retry.
- People could abuse it for spam links. Mitigation: rate limits and a URL blocklist.

## 6. At 10× traffic

Put a CDN in front to cache redirects and add read replicas. Only split out the stats service if the worker starts slowing the app down.

## ADR-001: Start with a single app on Postgres

- **Status:** accepted
- **Context:** two-person team, read-heavy traffic, redirects must be fast.
- **Options:** microservices; single app on DynamoDB; single app on Postgres.
- **Decision:** one app, one Postgres database, and Redis for caching.
- **Consequences:** simple to build and run; harder to scale parts of the system independently.
- **Revisit when:** redirects exceed 1,000 per second, or the stats worker needs its own release schedule.
