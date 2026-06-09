from datetime import date, timedelta

import pytest

from app.repositories.market import MarketPricePoint
from app.services.market import build_market_snapshot, compute_breadth_series
from app.domain.market.volatility import compute_volatility_dashboard, summarize_volatility_points


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


def test_volatility_dashboard_detects_confirmed_risk_off() -> None:
    start = date(2025, 1, 2)
    series = {
        "SPY": _series("SPY", start, [400 + index * 0.1 for index in range(280)]),
        "^VIX": _series("^VIX", start, [14] * 250 + [14 + index * 0.8 for index in range(30)]),
        "VIXY": _series("VIXY", start, [10] * 250 + [10 + index * 0.45 for index in range(30)]),
    }

    points = compute_volatility_dashboard(series, limit=60)
    summary = summarize_volatility_points(points)

    assert points
    assert points[-1].vix_regime == "Stress"
    assert points[-1].vixy_stress_confirmation is True
    assert points[-1].vol_regime == "Risk Off bestätigt"
    assert summary["regime"] == "Risk Off bestätigt"


def test_market_snapshot_includes_volatility_warning() -> None:
    start = date(2025, 1, 2)
    series = {
        "AAA": _series("AAA", start, [100 + index * 0.5 for index in range(220)]),
        "BBB": _series("BBB", start, [80 + index * 0.4 for index in range(220)]),
        "CCC": _series("CCC", start, [50 + index * 0.3 for index in range(220)]),
    }
    volatility_summary = {
        "regime": "Risk Off bestätigt",
        "status_cards": [
            {"title": "Vol Regime", "status": "Risk Off bestätigt", "detail": "VIX und VIXY ziehen an", "tone": "bad"}
        ],
    }

    latest = compute_breadth_series(series, universe="test_universe", universe_size=3)[-1]
    snapshot = build_market_snapshot(latest, volatility_summary=volatility_summary)

    assert snapshot.warning_count == 1
    assert snapshot.volatility_regime == "Risk Off bestätigt"
    assert snapshot.metrics_json["volatility"]["regime"] == "Risk Off bestätigt"
    assert snapshot.metrics_json["kpis"][-1]["label"] == "Vol Regime"


def test_volatility_dashboard_returns_empty_without_benchmark() -> None:
    start = date(2025, 1, 2)
    series = {"^VIX": _series("^VIX", start, [14 + index * 0.1 for index in range(80)])}

    points = compute_volatility_dashboard(series)

    assert points == []


def _series(ticker: str, start: date, closes: list[float]) -> list[MarketPricePoint]:
    return [
        MarketPricePoint(ticker=ticker, date=start + timedelta(days=index), close=close)
        for index, close in enumerate(closes)
    ]
