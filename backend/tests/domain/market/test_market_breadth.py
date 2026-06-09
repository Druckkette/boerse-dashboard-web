from datetime import date, timedelta

import pytest

from app.repositories.market import MarketPricePoint
from app.services.market import build_market_snapshot, compute_breadth_series


def test_compute_breadth_series_is_reproducible() -> None:
    start = date(2025, 1, 2)
    series = {
        "AAA": _series("AAA", start, [100 + index * 0.5 for index in range(220)]),
        "BBB": _series("BBB", start, [200 - index * 0.3 for index in range(220)]),
        "CCC": _series("CCC", start, [50 + index * 0.12 for index in range(220)]),
    }

    points = compute_breadth_series(series, universe="test_universe", universe_size=3)

    assert len(points) == 220
    latest = points[-1]
    assert latest.date == start + timedelta(days=219)
    assert latest.advancers == 2
    assert latest.decliners == 1
    assert latest.coverage_ratio == pytest.approx(1.0)
    assert latest.pct_above_50sma == pytest.approx(2 / 3 * 100)
    assert latest.pct_above_200sma == pytest.approx(2 / 3 * 100)
    assert latest.mcclellan > 0


def test_market_snapshot_classifies_constructive_breadth() -> None:
    start = date(2025, 1, 2)
    series = {
        "AAA": _series("AAA", start, [100 + index * 0.5 for index in range(220)]),
        "BBB": _series("BBB", start, [80 + index * 0.4 for index in range(220)]),
        "CCC": _series("CCC", start, [50 + index * 0.3 for index in range(220)]),
    }

    latest = compute_breadth_series(series, universe="test_universe", universe_size=3)[-1]
    snapshot = build_market_snapshot(latest)

    assert snapshot.ampel_phase == "gruen"
    assert snapshot.breadth_mode == "rueckenwind"
    assert snapshot.warning_count == 0
    assert snapshot.metrics_json["coverage_ratio"] == pytest.approx(1.0)
    assert snapshot.metrics_json["kpis"][0]["label"] == "Breite 50-SMA"


def _series(ticker: str, start: date, closes: list[float]) -> list[MarketPricePoint]:
    return [
        MarketPricePoint(ticker=ticker, date=start + timedelta(days=index), close=close)
        for index, close in enumerate(closes)
    ]
