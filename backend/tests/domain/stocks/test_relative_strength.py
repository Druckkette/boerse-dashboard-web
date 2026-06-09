from __future__ import annotations

from datetime import date, timedelta

from app.domain.stocks.relative_strength import ClosePoint, compute_relative_strength_ratings


def test_relative_strength_ranks_leaders_above_laggards() -> None:
    series = {
        "SPY": _series(0.0010),
        "LEAD": _series(0.0020),
        "MATCH": _series(0.0010),
        "LAG": _series(0.0001),
    }

    ratings = compute_relative_strength_ratings(series, benchmark_ticker="SPY")
    by_ticker = {item.ticker: item for item in ratings}

    assert [item.ticker for item in ratings] == ["LEAD", "MATCH", "LAG"]
    assert by_ticker["LEAD"].rating == 99
    assert by_ticker["LAG"].rating < by_ticker["MATCH"].rating < by_ticker["LEAD"].rating
    assert by_ticker["LEAD"].metadata["excess_return_6m_pct"] > 0
    assert by_ticker["LAG"].metadata["excess_return_6m_pct"] < 0


def test_relative_strength_returns_empty_without_benchmark() -> None:
    ratings = compute_relative_strength_ratings({"NVDA": _series(0.002)}, benchmark_ticker="SPY")

    assert ratings == []


def _series(daily_growth: float, *, days: int = 320) -> list[ClosePoint]:
    start = date(2025, 1, 1)
    price = 100.0
    points: list[ClosePoint] = []
    for offset in range(days):
        price *= 1 + daily_growth
        points.append(ClosePoint(date=start + timedelta(days=offset), close=price))
    return points
