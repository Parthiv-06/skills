```
Scanned shopco: 16 files, 301 lines, 6 declared dependencies (2026-11-13)
Every row is a lead: open the code before acting on it.

## Duplicate code (exact copies alone: ~26 lines)
| Kind | Copies | Lines | Saves | Where | Differs |
|---|---|---|---|---|---|
| EXACT | 3 | 5 | 10 | services/alerts/client.py:12 make_signature<br>services/billing/client.py:12 sign_request<br>services/reports/build.py:32 signed_headers | - |
| EXACT | 2 | 9 | 9 | services/alerts/client.py:19 retry_call<br>services/billing/client.py:19 with_retries | - |
| EXACT | 2 | 7 | 7 | services/billing/invoices.py:10 parse_iso<br>services/reports/build.py:19 to_datetime | - |
| NEAR | 2 | 2 | 2 | services/billing/invoices.py:19 normalize_amount<br>services/reports/build.py:28 normalize_amount | ROUND_HALF_UP vs ROUND_HALF_EVEN |

## Dependencies
| Flag | Package | Evidence |
|---|---|---|
| HEAVY | pandas | 1 use(s): pandas.read_csv (services/reports/build.py:40) |
| MISPLACED | pytest | dev tool declared as runtime in pyproject.toml |
| UNUSED | redis | runtime in pyproject.toml; nothing imports it |
| UNUSED | tenacity | runtime in pyproject.toml; nothing imports it |
| OVERLAP | httpx + requests | HTTP clients: httpx (1 files), requests (3 files) |

## Code
| Flag | Where | Detail |
|---|---|---|
| PATCH | common/http_patch.py:13 | assigns requests.Session.request |
| BLOCKING | services/alerts/client.py:33 | async fetch_metric() calls retry_call(), which calls time.sleep() |
| BLOCKING | services/alerts/client.py:33 | requests.get() inside async fetch_metric() |
| RETRY-LOOP | services/alerts/client.py:21 | sleep-and-retry loop; tenacity already declared |
| RETRY-LOOP | services/billing/client.py:21 | sleep-and-retry loop; tenacity already declared |
| NO-TIMEOUT | services/billing/client.py:39 | requests.post() has no timeout= |
| NO-TIMEOUT | services/billing/client.py:46 | requests.get() has no timeout= |
| PRIVATE | services/reports/build.py:12 | imports httpx._config DEFAULT_TIMEOUT_CONFIG |

## Structure
| Flag | Where | Detail |
|---|---|---|
| LEAKY | common/formatting.py:3 | shared code imports app code services.billing.models |
| HOLLOW | common.formatting | 1 importing file(s): services/billing/invoices.py; 2 def(s) |
| UNREFERENCED | common/formatting.py:13 | invoice_summary is never named anywhere |
| HOLLOW | common.http_patch | 1 importing file(s): services/billing/__init__.py; 1 def(s) |
| HOLLOW | common.utils | 1 importing file(s): services/reports/build.py; 1 def(s); only re-exports: common/utils/__init__.py |
| CYCLE | common.formatting <-> services.billing | common/formatting.py:3 -> services.billing.models; services/billing/invoices.py:6 -> common.formatting |

```
