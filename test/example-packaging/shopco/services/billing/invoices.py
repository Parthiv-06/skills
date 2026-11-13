"""Builds invoices from gateway charges and renders their totals for emails.
Rounding is half-up to match the tax authority's invoice rules."""
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from common.formatting import money
from services.billing.models import Invoice, LineItem


def parse_iso(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_amount(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def invoice_from_charges(number, customer, currency, charges):
    inv = Invoice(number, customer, currency, parse_iso(charges[0]["created"]))
    for c in charges:
        inv.lines.append(LineItem(c["description"], normalize_amount(c["amount"])))
    return inv


def email_total(inv):
    return f"Total due: {money(inv.total_cents, inv.currency)}"
