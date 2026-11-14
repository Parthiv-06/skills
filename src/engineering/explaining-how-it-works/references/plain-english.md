# Writing Part 1

Write it for someone smart who has never seen code: a new teammate in sales, a founder, or the person who asked. They should finish it knowing what happens, in what order, and what can go wrong.

## Shape
- **`answer`:** one sentence, 30 words at most, saying what it does for someone.
- **`steps`:** 5–9 of them. Each step has:
  - `title`: what happens, starting with who does it ("The recorder passes the message on").
  - `see`: what a person notices. "Nothing" is a fine answer.
  - `behind`: what the system does, in everyday words.
  - `tech`: the trace steps it covers. Every trace step belongs to exactly one plain step.
- **`analogy`:** optional, and only if it is accurate. A misleading analogy is worse than none.
- **`worth`:** 2–4 limits or surprises a non-engineer should know: delays, what happens on failure, privacy, cost.
- **`terms`:** a word you truly cannot avoid goes here with a plain definition. Keep it to 0–3 words. When the subject itself is a technical idea (tokens, an API, a cache), defining it here is expected, not a failure.

## Ways to say it plainly
| Instead of | Say |
|---|---|
| The client sends a POST request to the API | Your browser sends the order to our server |
| It's enqueued and a worker processes it async | It's put in a to-do list, and another part of the system picks it up a moment later |
| The webhook fires | The payment company calls us back to say the payment went through |
| We cache the result for 5 minutes | We remember the answer for 5 minutes, so repeat visits are instant |
| Idempotency key prevents double charges | If the same request arrives twice, we notice and charge only once |
| Auth middleware validates the JWT | First it checks you are signed in |
| Writes to the database in a transaction | Saves everything at once, so it's never half-saved |
| Rate-limited at 100 rpm | It accepts at most 100 requests a minute |

## Rules the gate checks
- No word from the technical list (`scripts/check_plain.py`) unless it appears in `terms`.
- Average sentence length is 20 words or fewer, and no sentence is longer than 32 words.

The gate can't check for vague writing, so reread each step and ask "could my parent picture this?"
