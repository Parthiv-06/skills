"""Money and invoice-line formatting shared by emails and reports.
Amounts come in as integer cents; output uses the currency's symbol when known."""
from services.billing.models import Invoice

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def money(cents, currency):
    sym = SYMBOLS.get(currency, currency + " ")
    return f"{sym}{cents / 100:,.2f}"


def invoice_summary(inv: Invoice):
    return f"{inv.number} · {inv.customer} · {money(inv.total_cents, inv.currency)}"
