from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.domain.stocks.assessment import (
    CHART_WEIGHTS,
    K4_WEIGHTS,
    MOVING_AVERAGE_WEIGHTS,
    OVERALL_WEIGHTS,
    TECHNICAL_WEIGHTS,
    ChartSignal,
    StockAssessmentBar,
    _chart_score_v2,
    _decorate_chart_signals,
    _k13_rs_dynamics,
    _k35_down_week_quality,
    _k38_hh_hl_good_close,
    _k4_rs_leadership,
    _k9_eps_sales_alignment,
    _k9_quarter_score,
    _ma_slope_score,
    _moving_average_score_v2,
    _overall_score_v2,
    compute_stock_assessment,
)
from app.services.stocks import _to_response


def test_v2_weight_sets_are_exact_integer_ratios() -> None:
    assert OVERALL_WEIGHTS == {"technical": 3, "fundamental": 3, "chart": 3, "moving_average": 1}
    assert sum(TECHNICAL_WEIGHTS.values()) == 120
    assert K4_WEIGHTS == {"above_21_ema": 25, "above_50_sma": 15, "persistence": 20, "rs_52w_high": 30, "white_space": 10}
    assert sum(CHART_WEIGHTS.values()) == 6
    assert sum(MOVING_AVERAGE_WEIGHTS.values()) == 100


def test_k4_uses_position_persistence_high_and_capped_white_space_only() -> None:
    context = _strong_rs_context()
    result = _k4_rs_leadership(context)

    assert result["score"] == pytest.approx(100)
    assert result["components"]["persistence"]["raw"]["combined_persistence_pct"] == pytest.approx(100)
    assert result["components"]["white_space"]["raw"]["current_separation"] == pytest.approx(100)

    # Explicitly excluded legacy fields must never affect K4.
    excluded_changed = {**context, "above_200": False, "trend_5w": False, "trend_13w": False,
                        "rs_3m_rating": 1, "rs_6m_rating": 50, "rs_12m_rating": 99}
    assert _k4_rs_leadership(excluded_changed)["score"] == pytest.approx(result["score"])


def test_k4_weights_rs_21_position_more_than_rs_50_position() -> None:
    context = _strong_rs_context()
    lose_21 = _k4_rs_leadership({**context, "above_21": False})["score"]
    lose_50 = _k4_rs_leadership({**context, "above_50": False})["score"]
    assert lose_21 == pytest.approx(75)
    assert lose_50 == pytest.approx(85)


def test_k4_rs_high_distance_reduces_score_and_white_space_does_not_exceed_100() -> None:
    context = _strong_rs_context()
    context["distance_to_high_pct"] = -12
    context["new_high_52w"] = False
    result = _k4_rs_leadership(context)
    assert result["components"]["rs_52w_high"]["score"] == 35
    assert result["components"]["white_space"]["score"] <= 100


def test_k13_scores_acceleration_without_absolute_rating_or_k4_inputs() -> None:
    rising = {"rs_3m_rating": 95, "rs_6m_rating": 80, "rs_12m_rating": 65}
    falling = {"rs_3m_rating": 65, "rs_6m_rating": 80, "rs_12m_rating": 95}
    high = _k13_rs_dynamics({**rising, "rating": 99, "above_21": True, "new_high_52w": True})
    same = _k13_rs_dynamics({**rising, "rating": 1, "above_21": False, "new_high_52w": False})
    low = _k13_rs_dynamics(falling)
    assert high["score"] == pytest.approx(100)
    assert same["score"] == pytest.approx(high["score"])
    assert low["score"] == pytest.approx(0)


@pytest.mark.parametrize(
    ("eps", "sales", "score", "trigger"),
    [
        (30, 28, 100, False),
        (30, 18, 85, False),
        (45, 8, 55, True),
        (38, -5, 20, True),
        (20, -15, 10, True),
        (-10, 20, 30, True),
        (-20, -18, 25, False),
        (3, -3, 50, False),
    ],
)
def test_k9_quarter_matrix(eps: float, sales: float, score: float, trigger: bool) -> None:
    actual_score, actual_trigger, _ = _k9_quarter_score(eps, sales, noise_pct=3)
    assert actual_score == score
    assert actual_trigger is trigger


def test_k9_matches_periods_not_array_positions_and_caps_persistent_divergence() -> None:
    fundamentals = {
        "eps_quarter_history": [
            {"fiscal_year": "2026", "fiscal_period": "Q3", "eps_growth_yoy_pct": 38},
            {"fiscal_year": "2026", "fiscal_period": "Q2", "eps_growth_yoy_pct": 32},
            {"fiscal_year": "2026", "fiscal_period": "Q1", "eps_growth_yoy_pct": 28},
        ],
        "revenue_quarter_history": [
            {"fiscal_year": "2026", "fiscal_period": "Q1", "revenue_growth_yoy_pct": -4},
            {"fiscal_year": "2026", "fiscal_period": "Q3", "revenue_growth_yoy_pct": -5},
            {"fiscal_year": "2026", "fiscal_period": "Q2", "revenue_growth_yoy_pct": -6},
        ],
    }
    result = _k9_eps_sales_alignment(fundamentals)
    assert [item["period"] for item in result["matched_quarters"]] == ["Q3 2026", "Q2 2026", "Q1 2026"]
    assert result["persistent_divergence"] is True
    assert result["score"] <= 20


def test_k9_renormalizes_two_quarters_and_rejects_one() -> None:
    two = _alignment_history([(30, 28), (30, 18)])
    result = _k9_eps_sales_alignment(two)
    assert result["status"] == "partial"
    assert result["score"] == pytest.approx((100 * 50 + 85 * 30) / 80)

    one = _alignment_history([(30, 28)])
    result = _k9_eps_sales_alignment(one)
    assert result["status"] == "insufficient_history"
    assert result["score"] is None


def test_moving_average_v2_rewards_established_rising_trend_and_keeps_weights_exact() -> None:
    frame = _trend_frame(260, start=20, end=120)
    result = _moving_average_score_v2(frame)
    assert result["score"] >= 95
    assert result["components"]["slope"]["score"] == 100
    assert result["components"]["persistence"]["raw"]["sma50"]["above_streak_days"] >= 20


def test_moving_average_v2_scores_both_falling_slopes_as_ten() -> None:
    result = _moving_average_score_v2(_trend_frame(260, start=120, end=20))
    assert result["components"]["slope"]["score"] == 10


@pytest.mark.parametrize(
    ("direction_21", "direction_50", "score"),
    [
        ("up", "up", 100), ("up", "flat", 80), ("flat", "up", 85),
        ("up", "down", 55), ("down", "up", 60), ("flat", "flat", 50),
        ("down", "flat", 30), ("flat", "down", 25), ("down", "down", 10),
    ],
)
def test_moving_average_slope_matrix(direction_21: str, direction_50: str, score: float) -> None:
    assert _ma_slope_score(direction_21, direction_50) == score  # type: ignore[arg-type]


def test_k35_scores_last_down_weeks_and_neutral_does_not_create_zero() -> None:
    weekly = _weekly_frame()
    # Newest week is down, but closes at 80% of its range.
    weekly.iloc[-1, weekly.columns.get_loc("Close")] = 99
    weekly.iloc[-1, weekly.columns.get_loc("High")] = 100
    weekly.iloc[-1, weekly.columns.get_loc("Low")] = 95
    result = _k35_down_week_quality(weekly)
    assert result["down_weeks"][0]["closing_range_pct"] == pytest.approx(80)
    assert result["down_weeks"][0]["score"] == 100

    rising = _weekly_frame()
    rising["Close"] = np.arange(100, 114, dtype=float)
    rising["Open"] = rising["Close"] - 1
    rising["High"] = rising["Close"] + 1
    rising["Low"] = rising["Close"] - 2
    neutral = _k35_down_week_quality(rising)
    assert neutral["status"] == "neutral"
    assert neutral["score"] is None


def test_k35_low_close_and_large_loss_rules() -> None:
    weekly = _weekly_frame()
    previous = float(weekly.iloc[-2]["Close"])
    weekly.iloc[-1, weekly.columns.get_loc("High")] = previous
    weekly.iloc[-1, weekly.columns.get_loc("Low")] = previous - 10
    weekly.iloc[-1, weekly.columns.get_loc("Close")] = previous - 8.5
    low_close = _k35_down_week_quality(weekly)
    assert low_close["down_weeks"][0]["closing_range_pct"] == pytest.approx(15)
    assert low_close["down_weeks"][0]["score"] == 0  # loss is also worse than -4%

    weekly.iloc[-1, weekly.columns.get_loc("Close")] = previous - 1.5
    weekly.iloc[-1, weekly.columns.get_loc("High")] = previous + 8.5
    weekly.iloc[-1, weekly.columns.get_loc("Low")] = previous - 3
    modest_loss = _k35_down_week_quality(weekly)
    assert modest_loss["down_weeks"][0]["score"] == 10


def test_k35_one_down_week_is_partial_and_uses_no_implicit_missing_zero() -> None:
    weekly = _weekly_frame()
    weekly["Close"] = np.arange(100, 114, dtype=float)
    weekly["Open"] = weekly["Close"] - 1
    weekly["High"] = weekly["Close"] + 2
    weekly["Low"] = weekly["Close"] - 3
    weekly.iloc[-1, weekly.columns.get_loc("Close")] = 111.5
    result = _k35_down_week_quality(weekly)
    assert result["status"] == "partial"
    assert result["score"] == result["down_weeks"][0]["score"]


@pytest.mark.parametrize(
    ("weekly_return", "closing_range", "expected"),
    [(4.0, 95, 100), (2.5, 80, 90), (1.0, 65, 75), (-1.0, 40, 50)],
)
def test_k38_deterministic_score_table(weekly_return: float, closing_range: float, expected: float) -> None:
    previous_close = 100.0
    close = previous_close * (1 + weekly_return / 100)
    low = 96.0
    high = low + (close - low) / (closing_range / 100)
    weekly = pd.DataFrame(
        {
            "Open": [99.0, 100.0],
            "High": [101.0, high],
            "Low": [95.0, low],
            "Close": [previous_close, close],
            "Volume": [1_000_000, 1_100_000],
        },
        index=pd.date_range("2026-01-02", periods=2, freq="W-FRI"),
    )
    assert _k38_hh_hl_good_close(weekly)["score"] == expected


def test_k38_is_neutral_without_higher_high_and_higher_low() -> None:
    weekly = _weekly_frame().tail(2)
    weekly.iloc[-1, weekly.columns.get_loc("High")] = weekly.iloc[-2]["High"]
    result = _k38_hh_hl_good_close(weekly)
    assert result["status"] == "neutral"
    assert result["score"] is None


def test_chart_excludes_ma_rs_and_setup_signals_but_keeps_them_for_display() -> None:
    decorated = _decorate_chart_signals(
        [
            ChartSignal("positive", "Durchschnitte in richtiger Ordnung"),
            ChartSignal("positive", "RS-Linie über 21-EMA"),
            ChartSignal("neutral", "Natürliche Reaktion"),
            ChartSignal("positive", "Shake-out"),
        ]
    )
    assert all(signal.display_relevant for signal in decorated)
    assert [signal.score_relevant for signal in decorated] == [False, False, False, True]
    chart = _chart_score_v2(decorated, _weekly_frame())
    assert chart["components"]["price_action_core"]["raw"]["scored_signal_keys"] == ["shake_out"]


def test_non_score_relevant_signals_never_change_chart_numeric_result() -> None:
    weekly = _weekly_frame()
    price_action = _decorate_chart_signals([ChartSignal("positive", "Shake-out")])
    contextual = _decorate_chart_signals([
        ChartSignal("positive", "Shake-out"),
        ChartSignal("positive", "Durchschnitte in richtiger Ordnung"),
        ChartSignal("negative", "RS-Linie fällt"),
    ])
    assert _chart_score_v2(price_action, weekly)["score"] == _chart_score_v2(contextual, weekly)["score"]


def test_overall_is_30_30_30_10_and_reports_limited_weight() -> None:
    available = {"score": 80.0, "status": "available", "data_coverage": 1.0}
    result = _overall_score_v2(
        technical_v2=available,
        fundamental_v2={"score": None, "status": "missing", "data_coverage": 0.0},
        chart_v2=available,
        moving_average_v2=available,
    )
    assert result["score"] == 80
    assert result["status"] == "limited"
    assert result["available_weight"] == pytest.approx(0.7)


def test_overall_complete_weighted_score_is_available() -> None:
    def score(value: float) -> dict:
        return {"score": value, "status": "available", "data_coverage": 1.0}

    result = _overall_score_v2(
        technical_v2=score(100),
        fundamental_v2=score(80),
        chart_v2=score(60),
        moving_average_v2=score(40),
    )
    assert result["score"] == pytest.approx(76)
    assert result["status"] == "available"
    assert result["available_weight"] == 1


def test_price_and_dollar_volume_change_eligibility_not_technical_score() -> None:
    bars = _bars(price_scale=1.0, volume_scale=1.0)
    low_price = _bars(price_scale=0.1, volume_scale=1.0)
    low_liquidity = _bars(price_scale=1.0, volume_scale=0.001)
    base = compute_stock_assessment("BASE", bars)
    cheap = compute_stock_assessment("CHEAP", low_price)
    illiquid = compute_stock_assessment("ILLIQ", low_liquidity)
    assert cheap.scores.technical == pytest.approx(base.scores.technical)
    assert illiquid.scores.technical == pytest.approx(base.scores.technical)
    assert cheap.eligibility["status"] == "failed"
    assert illiquid.eligibility["status"] == "failed"


def test_display_only_signals_remain_in_api_with_relevance_metadata() -> None:
    result = compute_stock_assessment(
        "DISPLAY",
        _bars(price_scale=1.0, volume_scale=1.0),
        rs_context={
            "rating": 90,
            "above_21": True,
            "above_50": True,
            "trend_5w": True,
            "near_high_52w": True,
            "distance_to_high_pct": -1,
        },
    )
    payload = _to_response(result).model_dump(mode="json")
    by_label = {signal["label"]: signal for signal in payload["chart_signals"]}
    assert by_label["RS-Linie über 21-EMA"]["score_relevant"] is False
    assert by_label["RS-Linie über 21-EMA"]["display_relevant"] is True
    assert by_label["Durchschnitte in richtiger Ordnung"]["source"] == "moving_average"
    assert payload["technical_v2"]["components"]
    assert payload["setup"]["moving_average_distances"]
    assert payload["eligibility"]["rules"]


def _strong_rs_context() -> dict:
    return {
        "rs_line_last": 110.0,
        "ema21": 100.0,
        "sma50": 100.0,
        "above_21": True,
        "above_50": True,
        "distance_to_high_pct": 0.0,
        "new_high_52w": True,
        "rs_history": [
            {"date": f"2026-01-{index + 1:02d}", "rs": 110.0, "rs_ema21": 100.0, "rs_sma50": 100.0}
            for index in range(63)
        ],
    }


def _alignment_history(values: list[tuple[float, float]]) -> dict:
    eps = []
    revenue = []
    for index, (eps_growth, sales_growth) in enumerate(values):
        period = f"Q{len(values) - index} 2026"
        eps.append({"fiscal_period": period, "eps_growth_yoy_pct": eps_growth})
        revenue.append({"fiscal_period": period, "revenue_growth_yoy_pct": sales_growth})
    return {"eps_quarter_history": eps, "revenue_quarter_history": revenue}


def _trend_frame(days: int, *, start: float, end: float) -> pd.DataFrame:
    close = np.linspace(start, end, days)
    index = pd.bdate_range("2025-01-02", periods=days)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000.0},
        index=index,
    )


def _weekly_frame() -> pd.DataFrame:
    close = np.array([100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108], dtype=float)
    return pd.DataFrame(
        {"Open": close + 0.5, "High": close + 2, "Low": close - 3, "Close": close, "Volume": 1_000_000.0},
        index=pd.date_range("2026-01-02", periods=len(close), freq="W-FRI"),
    )


def _bars(*, price_scale: float, volume_scale: float) -> list[StockAssessmentBar]:
    start = date(2025, 1, 2)
    bars = []
    for index in range(260):
        close = (40 + index * 0.2) * price_scale
        bars.append(
            StockAssessmentBar(
                date=start + timedelta(days=index),
                open=close * 0.995,
                high=close * 1.01,
                low=close * 0.99,
                close=close,
                volume=2_000_000 * volume_scale,
            )
        )
    return bars
