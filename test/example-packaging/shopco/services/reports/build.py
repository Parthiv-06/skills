"""Monthly revenue report: loads exported charges, groups by customer, and posts a summary.
Figures are statistical, so amounts round half-even to avoid bias across many rows."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal

import httpx
import pandas as pd
from httpx._config import DEFAULT_TIMEOUT_CONFIG

from common.utils import slugify

REPORTS_API = "https://reports.example.com"


def to_datetime(s):
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def normalize_amount(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def signed_headers(key, method, path, body=""):
    stamp = str(int(time.time()))
    text = f"{stamp}\n{method.upper()}\n{path}\n{body}".encode()
    mac = hmac.new(key.encode(), text, hashlib.sha256).hexdigest()
    return {"X-Timestamp": stamp, "X-Signature": mac}


def load_rows(csv_path):
    df = pd.read_csv(csv_path)
    return df.to_dict("records")


def build_monthly_report(csv_path, month):
    rows = [r for r in load_rows(csv_path) if r["created"].startswith(month)]
    by_customer = {}
    by_day = {}
    refunds = 0
    for r in rows:
        cents = normalize_amount(r["amount"])
        if r.get("kind") == "refund":
            refunds += cents
            cents = -cents
        by_customer[r["customer"]] = by_customer.get(r["customer"], 0) + cents
        day = to_datetime(r["created"]).date().isoformat()
        by_day[day] = by_day.get(day, 0) + cents
    total = sum(by_customer.values())
    top = sorted(by_customer.items(), key=lambda kv: kv[1], reverse=True)[:10]
    busiest = max(by_day.items(), key=lambda kv: kv[1]) if by_day else (None, 0)
    return {
        "id": slugify(f"revenue {month}"),
        "month": month,
        "total_cents": total,
        "refund_cents": refunds,
        "customers": len(by_customer),
        "top_customers": [{"customer": c, "cents": v} for c, v in top],
        "busiest_day": {"day": busiest[0], "cents": busiest[1]},
        "daily": dict(sorted(by_day.items())),
    }


def post_report(secret, report):
    body = json.dumps(report)
    headers = signed_headers(secret, "POST", "/reports", body)
    r = httpx.post(REPORTS_API + "/reports", content=body, headers=headers, timeout=DEFAULT_TIMEOUT_CONFIG)
    r.raise_for_status()
    return r.json()["url"]
