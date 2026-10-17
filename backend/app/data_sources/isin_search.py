"""ISIN-only Yahoo lookup for TR imports; never guess from a product name."""
from __future__ import annotations

from functools import lru_cache
import re
import time

from app.data_sources.provider_usage import record_provider_event


def valid_isin(value: str) -> bool:
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
        return False
    digits = "".join(str(int(char, 36)) for char in value)
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char) * (2 if index % 2 else 1)
        total += number // 10 + number % 10
    return total % 10 == 0


@lru_cache(maxsize=512)
def _search(isin: str, cache_window: int) -> tuple[dict, ...]:
    import yfinance as yf

    record_provider_event("yahoo_requests")
    result = yf.Search(
        isin, max_results=20, news_count=0, lists_count=0, recommended=0,
        enable_fuzzy_query=False, timeout=5,
    )
    return tuple(result.quotes)


def search_isin(isin: str, asset_class: str) -> dict:
    """Only a unique security result for an exact ISIN query is automatic.

    Alternative listings remain explicit choices. Derivatives are deliberately
    excluded: an underlying share is not the purchased certificate.
    """
    if asset_class not in {"STOCK", "FUND"} or not valid_isin(isin):
        return {"ticker": "", "candidates": [], "message": "Keine gültige Aktien-/Fonds-ISIN für die automatische Suche."}
    try:
        quotes = _search(isin, int(time.monotonic() // 600))
    except Exception:
        # Provider outages must not abort an otherwise valid report. Exceptions
        # are not cached, allowing a retry via the preview button.
        return {"ticker": "", "candidates": [], "message": "Automatische Suche derzeit nicht erreichbar. Vorschau erneut prüfen oder Ticker ergänzen."}
    allowed_types = {"EQUITY"} if asset_class == "STOCK" else {"ETF", "MUTUALFUND"}
    candidates = {}
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        symbol = str(quote.get("symbol") or "").strip().upper()
        if (not re.fullmatch(r"[A-Z0-9][A-Z0-9.=_^-]{0,31}", symbol)
                or quote.get("quoteType") not in allowed_types
                or quote.get("isYahooFinance") is False
                or (quote.get("isin") and str(quote["isin"]).upper() != isin)):
            continue
        candidates[symbol] = {
            "ticker": symbol,
            "name": str(quote.get("longname") or quote.get("shortname") or symbol),
            "exchange": str(quote.get("exchDisp") or quote.get("exchange") or ""),
        }
    items = list(candidates.values())
    return {
        "ticker": items[0]["ticker"] if len(items) == 1 else "",
        "candidates": items,
        "message": "Automatisch über die ISIN gefunden." if len(items) == 1 else (
            "Mehrere Börsenplätze gefunden. Bitte einen Ticker auswählen." if items
            else "Kein eindeutiger Yahoo-Ticker gefunden. Bitte einmalig ergänzen."
        ),
    }
