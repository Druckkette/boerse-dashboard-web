"""Daily issuer bid histories, keyed by the product ISIN rather than its underlying."""
from datetime import UTC, date, datetime
import math

from app.repositories.prices import PriceBarWrite


def parse_issuer_history(isin: str, payload: dict, *, today: date | None = None) -> tuple[str, list[PriceBarWrite]]:
    today = today or date.today()
    if "product" in payload:
        product = payload["product"]
        if product.get("Isin") != isin or product.get("Currency") != "EUR":
            raise ValueError("Issuer product identity or quote currency does not match")
        observations = [(datetime.fromisoformat(row["Date"].replace("Z", "+00:00")).date(), row.get("Bid")) for row in payload["history"]]
        source = "societe_generale:EUR:bid"
    else:
        series = [series for series in payload["payload"]["series"] if series.get("priceIdentifier") == isin and series.get("isProduct") is True]
        if len(series) != 1:
            raise ValueError("Expected exactly one matching issuer product series")
        observations = [(datetime.fromtimestamp(row["timestamp"] / 1000, UTC).date(), row.get("bid")) for row in series[0]["points"]]
        source = "vontobel:EUR:bid"
    by_date = {}
    for day, value in observations:
        if value is None or day > today:
            continue
        close = float(value)
        if not math.isfinite(close) or close < 0:
            raise ValueError("Invalid issuer bid")
        if day in by_date and by_date[day] != close:
            raise ValueError("Intraday observations cannot be imported as daily closes")
        by_date[day] = close
    return source, [PriceBarWrite(date=day, close=close, open=None, high=None, low=None, adj_close=None, volume=None) for day, close in sorted(by_date.items())]
