"""Payment gateway client for charging cards and fetching charge status.
Every request is HMAC-signed; the gateway rejects calls older than 5 minutes."""
import hashlib
import hmac
import time

import requests

GATEWAY = "https://pay.example.com/v2"


def sign_request(secret, method, path, body=""):
    ts = str(int(time.time()))
    msg = f"{ts}\n{method.upper()}\n{path}\n{body}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return {"X-Timestamp": ts, "X-Signature": sig}


def with_retries(fn, attempts=4, base_delay=0.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            time.sleep(base_delay * 2 ** i)
    raise last


class GatewayClient:
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret

    def charge(self, customer_id, cents):
        body = f'{{"customer":"{customer_id}","amount":{cents}}}'
        headers = sign_request(self.secret, "POST", "/charges", body)
        headers["X-Key"] = self.key
        resp = with_retries(lambda: requests.post(GATEWAY + "/charges", data=body, headers=headers))
        resp.raise_for_status()
        return resp.json()

    def status(self, charge_id):
        headers = sign_request(self.secret, "GET", f"/charges/{charge_id}")
        headers["X-Key"] = self.key
        resp = with_retries(lambda: requests.get(f"{GATEWAY}/charges/{charge_id}", headers=headers))
        resp.raise_for_status()
        return resp.json()["status"]
