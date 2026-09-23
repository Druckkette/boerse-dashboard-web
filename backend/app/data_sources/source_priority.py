"""Canonical source order for each independently refreshed data group."""
SOURCE_PRIORITY = {
    "statements": ("local_snapshot", "sec_bulk_cache", "sec_companyfacts_live", "yfinance", "fmp"),
    "beta": ("local_price_cache", "yfinance"),
    "earnings_date": ("nasdaq", "yfinance", "fmp"),
}


def source_rank(group: str, source: str) -> int:
    try:
        return SOURCE_PRIORITY[group].index(source)
    except (KeyError, ValueError):
        return 99
