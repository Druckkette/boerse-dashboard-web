from datetime import date, timedelta

from app.repositories.market import MarketOhlcvPoint, MarketPricePoint
from app.services.market import compute_intermarket_divergence, compute_sector_rotation


def test_intermarket_divergence_marks_lagging_index() -> None:
    start = date(2025, 1, 2)
    series = {
        "^GSPC": _ohlcv_series("^GSPC", start, [100 + index for index in range(30)]),
        "^IXIC": _ohlcv_series("^IXIC", start, [120 + index * 1.2 for index in range(30)]),
        "^RUT": _ohlcv_series("^RUT", start, [95 + index * 0.2 for index in range(25)] + [90, 89, 88, 87, 86]),
    }

    items = compute_intermarket_divergence(series)

    assert len(items) == 3
    assert next(item for item in items if item.ticker == "^GSPC").at_20d_high is True
    rut = next(item for item in items if item.ticker == "^RUT")
    assert rut.at_20d_high is False
    assert rut.dist_to_20d_high_pct is not None
    assert rut.tone in {"warning", "bad"}


def test_sector_rotation_detects_defensive_leadership() -> None:
    start = date(2025, 1, 2)
    series = {
        "XLU": _price_series("XLU", start, [100 + index * 0.6 for index in range(20)]),
        "XLP": _price_series("XLP", start, [100 + index * 0.5 for index in range(20)]),
        "XLK": _price_series("XLK", start, [100 + index * 0.1 for index in range(20)]),
        "XLY": _price_series("XLY", start, [100 - index * 0.1 for index in range(20)]),
    }

    groups, defensive_lead, spread = compute_sector_rotation(series, lookback_days=10)

    assert defensive_lead is True
    assert spread is not None and spread > 0
    assert [group.group for group in groups] == ["defensive", "offensive"]
    defensive = next(group for group in groups if group.group == "defensive")
    assert defensive.avg_return_10d_pct is not None
    assert {item.ticker for item in defensive.items} == {"XLU", "XLP"}


def _ohlcv_series(ticker: str, start: date, closes: list[float]) -> list[MarketOhlcvPoint]:
    return [
        MarketOhlcvPoint(
            ticker=ticker,
            date=start + timedelta(days=index),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    ]


def _price_series(ticker: str, start: date, closes: list[float]) -> list[MarketPricePoint]:
    return [
        MarketPricePoint(ticker=ticker, date=start + timedelta(days=index), close=close)
        for index, close in enumerate(closes)
    ]
