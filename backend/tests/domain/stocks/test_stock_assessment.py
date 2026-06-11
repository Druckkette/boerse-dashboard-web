from __future__ import annotations

from datetime import date, timedelta

from app.domain.stocks.assessment import StockAssessmentBar, compute_stock_assessment


def test_stock_assessment_scores_constructive_leader() -> None:
    bars = _synthetic_bars(start_price=35, drift=0.004, volume=2_500_000)
    result = compute_stock_assessment(
        "LEAD",
        bars,
        rs_context={
            "rating": 92,
            "percentile": 94.0,
            "above_21": True,
            "above_50": True,
            "trend_5w": True,
            "trend_13w": True,
            "near_high_52w": True,
            "new_high_52w": True,
            "excess_return_3m_pct": 18.0,
            "excess_return_6m_pct": 32.0,
        },
    )

    assert result.source == "database"
    assert result.scores.overall >= 60
    assert result.scores.technical >= 60
    assert result.metrics.rs_rating == 92
    assert any(check.label == "RS-Bewertung >=80" and check.passed for check in result.checks)
    assert result.drivers


def test_stock_assessment_flags_weak_position() -> None:
    bars = _synthetic_bars(start_price=80, drift=-0.003, volume=180_000)
    result = compute_stock_assessment(
        "WEAK",
        bars,
        rs_context={
            "rating": 38,
            "percentile": 30.0,
            "above_21": False,
            "above_50": False,
            "trend_5w": False,
            "trend_13w": False,
            "near_high_52w": False,
            "distance_to_high_pct": -24.0,
        },
    )

    assert result.scores.overall < 60
    assert result.verdict_tone in {"warning", "bad"}
    assert any("Dollar-Volumen" in warning for warning in result.warnings)
    assert any(signal.category == "negative" for signal in result.chart_signals)


def test_stock_assessment_missing_payload_is_stable() -> None:
    result = compute_stock_assessment("MISS", [])

    assert result.source == "missing"
    assert result.data_status == "missing"
    assert result.verdict_label == "Nicht bewertbar"
    assert result.scores.overall == 0
    assert result.warnings


def _synthetic_bars(*, start_price: float, drift: float, volume: float) -> list[StockAssessmentBar]:
    bars: list[StockAssessmentBar] = []
    current = start_price
    current_date = date.today() - timedelta(days=360)
    index = 0
    while len(bars) < 260:
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        wobble = 0.012 if index % 17 == 0 else -0.006 if index % 11 == 0 else 0.0
        previous = current
        current = max(2.0, current * (1 + drift + wobble))
        high = max(previous, current) * 1.015
        low = min(previous, current) * 0.985
        bars.append(
            StockAssessmentBar(
                date=current_date,
                open=round(previous, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(current, 2),
                volume=volume * (1.4 if index % 13 == 0 else 1.0),
            )
        )
        current_date += timedelta(days=1)
        index += 1
    return bars
