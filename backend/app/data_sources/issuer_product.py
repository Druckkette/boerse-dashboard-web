"""Validate issuer lifecycle evidence separately from observed market quotes."""
from datetime import UTC, date, datetime, time
import math
from zoneinfo import ZoneInfo

from app.repositories.prices import PriceBarWrite


def sg_final_bid(product: dict, properties: list[dict], *, now: datetime) -> PriceBarWrite | None:
    """Read the issuer's last bid after the German quoting session has closed.

    SG's unqualified TimeStamp is UTC (the website displays it in Berlin time).
    Intraday or old snapshots never masquerade as a later daily close.
    """
    if product.get("Currency") != "EUR":
        raise ValueError("Unexpected issuer currency")
    fields = {row.get("Name"): row for row in properties}
    stamp = fields.get("TimeStamp", {}).get("Value")
    bid = fields.get("Bid", {})
    if not stamp or bid.get("Value") is None:
        return None
    quoted_at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if quoted_at.tzinfo is None:
        quoted_at = quoted_at.replace(tzinfo=UTC)
    local = quoted_at.astimezone(ZoneInfo("Europe/Berlin"))
    closed_at = datetime.combine(local.date(), time(22), ZoneInfo("Europe/Berlin"))
    if now < closed_at or quoted_at > now or local.time() < time(21, 30):
        return None
    value = float(bid["Value"])
    if bid.get("Suffix", "").strip() != "EUR" or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid issuer closing bid")
    return PriceBarWrite(date=local.date(), close=value, open=None, high=None, low=None, adj_close=None, volume=None)


def vontobel_redemption(isin: str, data: dict) -> dict | None:
    product = data.get("data", {})
    if product.get("isin") != isin or product.get("currency") != "EUR":
        raise ValueError("Issuer product identity or currency mismatch")
    if not product.get("isEndOfLifeComplete"):
        return None
    repayments = [row for row in data.get("disclaimers", []) if row.get("repaymentPrice") is not None]
    fixings = [row for row in data.get("lifeCycle", []) if row.get("type") == 7]
    if len(repayments) != 1 or len(fixings) != 1:
        return None
    repayment = repayments[0]
    amount = float(repayment["repaymentPrice"])
    fixing_day = date.fromisoformat(fixings[0]["occurrence"][:10])
    payment_day = date.fromisoformat(repayment["repaymentDate"][:10])
    if repayment.get("currency") != "EUR" or not math.isfinite(amount) or amount < 0 or payment_day < fixing_day:
        raise ValueError("Invalid issuer repayment")
    return {"amount": amount, "currency": "EUR", "valuation_date": fixing_day.isoformat(),
            "valuation_at": fixings[0]["occurrence"],
            "payment_date": payment_day.isoformat(), "source_url":
            f"https://markets.vontobel.com/de-de/produkte/hebel/faktor-optionsscheine/{isin}"}
