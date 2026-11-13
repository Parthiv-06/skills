# Packaging review: shopco

Produced by the packaging-code skill on [shopco/](shopco/). The scanner output it started from is in [scan.md](scan.md).

**Verdict: extract 2, fix 9, about 55-60 lines saved (roughly 20%), plus two dependencies to drop.**

**Extract**
- `common/signing.py`: `sign(secret, method, path, body="") -> dict`. The same HMAC code is copied 3 times: `services/alerts/client.py:12`, `services/billing/client.py:12`, `services/reports/build.py:32`. Saves about 10 lines.
- `common/dates.py`: `parse_iso(value: str) -> datetime`. Exact copies in `services/billing/invoices.py:10` and `services/reports/build.py:19`. The project needs Python 3.11+, where `fromisoformat` already reads "Z", so only the "no zone means UTC" rule is still needed. Saves about 9 lines.

**Use what you have**
- `tenacity` is declared but never used. It should replace `retry_call` (`services/alerts/client.py:19`) and `with_retries` (`services/billing/client.py:19`), with `reraise=True` so callers still get the original exception.
- `csv.DictReader` instead of pandas at `services/reports/build.py:40`, where pandas only reads one CSV. Check first: numeric customer IDs come back as strings.

**Misuse**
- PATCH `common/http_patch.py:13`: patches `requests` for the whole process when billing is imported. Pass `timeout=10` at `services/billing/client.py:39` and `:46` instead.
- BLOCKING `services/alerts/client.py:33`: the async fetch calls `requests.get` and `time.sleep`, which freezes the event loop. Use `httpx.AsyncClient` with tenacity's async retry.
- PRIVATE `services/reports/build.py:12`: `httpx._config`. Use `timeout=5.0`.
- MISPLACED `pytest` is a runtime dependency. Move it to a dev group.
- OVERLAP `httpx` + `requests`. Settle on httpx once alerts moves over.
- UNUSED `redis`. Remove it.
- LEAKY / CYCLE `common/formatting.py:3` imports `services.billing.models`, but only for the unused `invoice_summary`. Delete that function.
- HOLLOW `common/formatting.money` has one user (billing). Move it there.
- HOLLOW `common/utils/` re-exports a one-line `slugify` that only reports uses. Move it there.

**Keep as is**
- The two `normalize_amount` functions: billing rounds `ROUND_HALF_UP` (a legal rule, checked by a test), reports rounds `ROUND_HALF_EVEN` on purpose. They fail check 4: they change for different reasons.

**Next, on your yes:** run the tests, then one commit each for signing, dates, tenacity, timeouts, async alerts, the formatting and utils cleanup, and the dependency changes.
