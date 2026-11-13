"""Client for the metrics API that alert rules poll for current values.
Polling runs inside the asyncio scheduler, so calls here must not block for long."""
import hashlib
import hmac
import time

import requests

METRICS = "https://metrics.example.com/api"


def make_signature(api_secret, verb, url_path, payload=""):
    now = str(int(time.time()))
    raw = f"{now}\n{verb.upper()}\n{url_path}\n{payload}".encode()
    digest = hmac.new(api_secret.encode(), raw, hashlib.sha256).hexdigest()
    return {"X-Timestamp": now, "X-Signature": digest}


def retry_call(func, tries=4, delay=0.5):
    err = None
    for attempt in range(tries):
        try:
            return func()
        except (requests.ConnectionError, requests.Timeout) as exc:
            err = exc
            time.sleep(delay * 2 ** attempt)
    raise err


async def fetch_metric(secret, name):
    path = f"/metrics/{name}"
    headers = make_signature(secret, "GET", path)
    resp = retry_call(lambda: requests.get(METRICS + path, headers=headers, timeout=5))
    resp.raise_for_status()
    return resp.json()["value"]
