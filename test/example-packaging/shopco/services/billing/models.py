"""Invoice and line-item records as stored in the billing database.
Amounts are integer cents; currency is per invoice, never per line."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LineItem:
    description: str
    cents: int


@dataclass
class Invoice:
    number: str
    customer: str
    currency: str
    issued: datetime
    lines: list = field(default_factory=list)

    @property
    def total_cents(self):
        return sum(li.cents for li in self.lines)
