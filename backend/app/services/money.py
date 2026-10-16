"""Explicit monetary conversions using observed, persisted daily FX only.

Current valuations may expose stale observations; historical conversions never
borrow today's rate or a daily close from after the execution date.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite

from app.repositories import prices


class MoneyUnavailable(ValueError):
    pass


def money_sum(values) -> float:
    return float(sum((Decimal(str(value)) for value in values), Decimal(0)))


def rounded_money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Conversion:
    rate: float
    as_of: date
    source: str = "price_cache"


def conversion(source: str, target: str, *, on: date | None = None) -> Conversion | None:
    minor_source = source in {"GBp", "GBX"}
    minor_target = target in {"GBp", "GBX"}
    source, target = ("GBP" if minor_source else source.upper()), ("GBP" if minor_target else target.upper())
    day = on or date.today()
    if source == target:
        return Conversion((0.01 if minor_source else 1) / (0.01 if minor_target else 1), day, "identity")

    def usd(currency):
        if currency == "USD":
            return 1.0, day
        try:
            bars = prices.list_price_bars(f"{currency}USD=X", start_date=day - timedelta(days=14))
        except prices.PriceRepositoryUnavailable:
            return None
        eligible = [bar for bar in bars if (bar.date < day if on else bar.date <= day)
                    and bar.close is not None and isfinite(float(bar.close)) and float(bar.close) > 0]
        if not eligible:
            return None
        bar = max(eligible, key=lambda item: item.date)
        if (day - bar.date).days > (4 if on else 7):
            return None
        return float(bar.close), bar.date

    left, right = usd(source), usd(target)
    if left is None or right is None:
        return None
    return Conversion(left[0] / right[0] * (0.01 if minor_source else 1) / (0.01 if minor_target else 1),
                      min(left[1], right[1]))


def convert_amount(value: float, source: str, target: str, *, on: date | None = None) -> float | None:
    if value == 0:
        return 0.0
    rate = conversion(source, target, on=on)
    return value * rate.rate if rate else None
