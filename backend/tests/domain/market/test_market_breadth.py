from datetime import date, timedelta

import pytest

from app.domain.market.ampel import TrendAmpelBar, TrendAmpelPoint, compute_trend_ampel
from app.domain.market.volatility import compute_volatility_dashboard, summarize_volatility_points
from app.repositories.market import MarketPricePoint
from app.services.market import build_market_snapshot, compute_breadth_series, compute_sector_ranking


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
    assert snapshot.metrics_json["kpis"][0]["label"] == "Aktien > 50-SMA"
    assert snapshot.metrics_json["kpis"][0]["detail"] == "Anteil Universe, nicht SPY-Abstand"


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


def test_market_snapshot_uses_trend_ampel_when_available() -> None:
    start = date(2025, 1, 2)
    series = {
        "AAA": _series("AAA", start, [100 + index * 0.5 for index in range(220)]),
        "BBB": _series("BBB", start, [80 + index * 0.4 for index in range(220)]),
        "CCC": _series("CCC", start, [50 + index * 0.3 for index in range(220)]),
    }
    trend_point = TrendAmpelPoint(
        date="2025-08-12",
        phase="aufwaertstrend",
        close=550.0,
        ema21=532.0,
        sma50=510.0,
        sma200=470.0,
        pct_change=1.2,
        closing_range=0.82,
        dist_count_25=1,
        anchor_date="2025-07-18",
        floor_mark=498.5,
        startschuss_low=515.2,
        startschuss_bonus=True,
    )

    latest = compute_breadth_series(series, universe="test_universe", universe_size=3)[-1]
    snapshot = build_market_snapshot(latest, trend_point=trend_point, trend_ticker="SPY")

    assert snapshot.ampel_phase == "aufwaertstrend"
    assert snapshot.metrics_json["breadth_phase"] == "gruen"
    assert snapshot.metrics_json["trend_ampel"]["ticker"] == "SPY"
    assert snapshot.metrics_json["trend_ampel"]["phase_label"] == "Aufwärtstrend"
    assert "Trend-Ampel Aufwärtstrend" in snapshot.metrics_json["action"]


def test_trend_ampel_exposes_streamlit_market_indicators() -> None:
    start = date(2025, 1, 2)
    bars = [
        TrendAmpelBar(
            date=start + timedelta(days=index),
            open=100 + index * 0.25,
            high=101 + index * 0.25,
            low=99 + index * 0.25,
            close=100 + index * 0.25,
            volume=1_000_000 + index * 100,
        )
        for index in range(260)
    ]

    latest = compute_trend_ampel(bars)[-1]

    assert latest.sma10 is not None
    assert latest.sma50 is not None
    assert latest.sma200 is not None
    assert latest.dist_50sma_pct is not None
    assert latest.dist_200sma_pct is not None
    assert latest.dist_52w_pct is not None
    assert latest.ma_order is True
    assert latest.neg_reversals_10d == 0
    assert latest.low_cr_5d == 0


def test_volatility_dashboard_returns_empty_without_benchmark() -> None:
    start = date(2025, 1, 2)
    series = {"^VIX": _series("^VIX", start, [14 + index * 0.1 for index in range(80)])}

    points = compute_volatility_dashboard(series)

    assert points == []


def test_sector_ranking_orders_latest_daily_return() -> None:
    start = date(2025, 1, 2)
    series = {
        "XLK": _series("XLK", start, [100, 101, 104, 108, 115]),
        "XLP": _series("XLP", start, [100, 101, 101.5, 102, 102.2]),
        "XLE": _series("XLE", start, [100, 98, 96, 94, 90]),
    }

    rows, history = compute_sector_ranking(series, mode="daily", periods=4)

    assert rows[0].ticker == "XLK"
    assert rows[0].rank == 1
    assert rows[-1].ticker == "XLE"
    assert rows[0].return_5d_pct is None
    assert {point.ticker for point in history} == {"XLK", "XLP", "XLE"}


def _series(ticker: str, start: date, closes: list[float]) -> list[MarketPricePoint]:
    return [
        MarketPricePoint(ticker=ticker, date=start + timedelta(days=index), close=close)
        for index, close in enumerate(closes)
    ]
