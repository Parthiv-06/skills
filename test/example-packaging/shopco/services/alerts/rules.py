"""Alert rules: compare a metric against a threshold and decide whether to fire.
A rule fires once per breach and re-arms only after the value drops back to the threshold."""
import asyncio
from dataclasses import dataclass, field

from services.alerts.client import fetch_metric


@dataclass
class Rule:
    metric: str
    threshold: float
    firing: bool = field(default=False)

    def check(self, value):
        if value > self.threshold and not self.firing:
            self.firing = True
            return True
        if value <= self.threshold:
            self.firing = False
        return False


async def evaluate(rules, secret):
    values = await asyncio.gather(*(fetch_metric(secret, r.metric) for r in rules))
    return [r for r, v in zip(rules, values) if r.check(v)]
