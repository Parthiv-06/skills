"""Tests for invoice building: totals, rounding direction, and timestamp parsing.
Half-up rounding is a legal requirement here; keep the 0.005 and 2.675 cases."""
from services.billing.invoices import invoice_from_charges, normalize_amount, parse_iso


def test_half_up():
    assert normalize_amount(0.005) == 1
    assert normalize_amount(2.675) == 268


def test_total():
    charges = [{"created": "2026-10-01T10:00:00Z", "description": "Plan", "amount": 19.99},
               {"created": "2026-10-02T10:00:00Z", "description": "Seats", "amount": 5.00}]
    inv = invoice_from_charges("INV-1", "c1", "USD", charges)
    assert inv.total_cents == 2499


def test_parse_iso_utc():
    assert parse_iso("2026-10-01T10:00:00Z").tzinfo is not None
