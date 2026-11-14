"""HTTP entry point for checkout-api; each route opens a session and calls checkout.py.
Sessions are per request and always closed, even when the handler raises."""
from services.checkout_api import checkout


def handle_pay(session_factory, order_id, amount_cents):
    session = session_factory()
    try:
        checkout.pay(session, order_id, amount_cents)
    finally:
        session.close()
