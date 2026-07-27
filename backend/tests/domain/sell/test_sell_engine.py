from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data_sources.yfinance_client import FetchedLiveQuote
from app.domain.sell import service as sell_service
from app.domain.sell.rules import (
    LEGACY_CUSTOM_STRATEGY_STEPS,
    RuleFeature,
    StrategyRecommendation,
    _build_strategy_result,
    _peak_drawdown_strategy,
)
from app.domain.sell.schemas import SellEvaluationRequest, SellManualInput, SnoozeRequest, TrancheLogEntry
from app.domain.sell.service import (
    clear_sell_engine_state,
    create_tranche_log_entry,
    evaluate_position_sell_decision,
    get_sell_metrics_for_position,
    get_sell_position_ranking,
    snooze_sell_signal,
)
from app.repositories.portfolio import PortfolioPositionRow
from tests.helpers.sell_fixture_data import fixture_positions, fixture_price_bars


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "sell"


@pytest.fixture(autouse=True)
def reset_sell_state(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_sell_engine_state()
    monkeypatch.setattr(sell_service.portfolio_repository, "list_open_positions", fixture_positions)
    monkeypatch.setattr(sell_service.prices_repository, "list_price_bars", fixture_price_bars)


def _load_fixture(name: str) -> dict:
    with (FIXTURE_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def test_sell_engine_imports_without_streamlit() -> None:
    import app.domain.sell.metrics  # noqa: F401
    import app.domain.sell.rules  # noqa: F401
    import app.domain.sell.strategies  # noqa: F401

    assert "streamlit" not in sys.modules


@pytest.mark.parametrize(
    "fixture_name",
    [
        "nvda_profit_position.json",
        "losing_position.json",
        "ema21_break_position.json",
        "climax_like_position.json",
    ],
)
def test_golden_master_fixtures_keep_stable_sell_contracts(fixture_name: str) -> None:
    fixture = _load_fixture(fixture_name)
    ticker = fixture["ticker"]
    expected = fixture["expected"]

    metrics = get_sell_metrics_for_position(ticker)
    evaluation = evaluate_position_sell_decision(ticker)

    assert metrics.ticker == ticker
    assert metrics.current_price is not None
    assert evaluation.ticker == ticker
    assert evaluation.health.health_score == metrics.health.health_score

    if "status" in expected:
        assert metrics.health.status == expected["status"]
    if "recommendation_label" in expected:
        assert evaluation.recommendation_label == expected["recommendation_label"]
    if "minimum_health_score" in expected:
        assert metrics.health.health_score >= expected["minimum_health_score"]
    if "minimum_days_under_ema21" in expected:
        assert metrics.days_under_ema21 >= expected["minimum_days_under_ema21"]
    if "minimum_recommendation_percent" in expected:
        assert evaluation.recommendation_percent >= expected["minimum_recommendation_percent"]


def test_health_score_is_reproducible() -> None:
    first = get_sell_metrics_for_position("NVDA").health
    second = get_sell_metrics_for_position("NVDA").health

    assert second.health_score == first.health_score
    assert second.status == first.status
    assert second.reasons == first.reasons


def test_tranche_log_reduces_follow_up_sale() -> None:
    before = evaluate_position_sell_decision("PLTR")
    assert before.sell_now_percent > 0

    create_tranche_log_entry(
        "PLTR",
        TrancheLogEntry(ticker="PLTR", pct=25, reason="Golden-master partial sale"),
    )
    after = evaluate_position_sell_decision("PLTR")

    assert after.already_sold_percent == 25
    assert after.sell_now_percent < before.sell_now_percent
    assert after.tranche_log[0].reason == "Golden-master partial sale"


def test_sell_rule_categories_and_strategy_are_exposed() -> None:
    evaluation = evaluate_position_sell_decision("PLTR")

    assert evaluation.emergency_features
    assert evaluation.offensive_features
    assert evaluation.defensive_features
    assert any(feature.id == "emergency_loss_limit" and feature.active for feature in evaluation.emergency_features)
    assert evaluation.strategy.strategy_key == "rs_line"
    assert evaluation.strategy.recommendations


def test_per_stock_sell_setup_overrides_defaults() -> None:
    request = SellEvaluationRequest(
        manual=SellManualInput(
            ticker="NVDA",
            sell_setup={
                "strategy_key": "custom",
                "profit_target_value": 80,
                "custom_strategy_steps": [{"feature_id": "offensive_profit_target", "tranche_percent": 33}],
            },
        )
    )

    evaluation = evaluate_position_sell_decision("NVDA", request)
    profit_feature = next(feature for feature in evaluation.offensive_features if feature.id == "offensive_profit_target")

    assert profit_feature.active is False
    assert evaluation.sell_now_percent == 0


def test_custom_strategy_uses_configured_tranche_percent() -> None:
    request = SellEvaluationRequest(
        manual=SellManualInput(
            ticker="NVDA",
            sell_setup={
                "strategy_key": "custom",
                "custom_strategy_steps": [{"feature_id": "offensive_profit_target", "tranche_percent": 33}],
            },
        )
    )

    evaluation = evaluate_position_sell_decision("NVDA", request)

    assert evaluation.strategy.recommendation_percent == 33
    assert evaluation.sell_now_percent == 33


def test_predefined_strategy_stages_are_cumulative() -> None:
    strategy = _build_strategy_result(
        "rs_line",
        [
            StrategyRecommendation(
                id="one",
                label="Erste",
                active=True,
                tranche_percent=25,
                detail="",
                trigger="",
            ),
            StrategyRecommendation(
                id="two",
                label="Zweite",
                active=True,
                tranche_percent=25,
                detail="",
                trigger="",
            ),
        ],
    )

    assert strategy["recommendation_percent"] == 50


def test_full_exit_stage_caps_cumulative_strategy_at_100_percent() -> None:
    strategy = _build_strategy_result(
        "ma_breaks",
        [
            StrategyRecommendation(
                id="partial",
                label="Teilverkauf",
                active=True,
                tranche_percent=50,
                detail="",
                trigger="",
            ),
            StrategyRecommendation(
                id="final",
                label="Final",
                active=True,
                tranche_percent=100,
                detail="",
                trigger="",
            ),
        ],
    )

    assert strategy["recommendation_percent"] == 100


def test_peak_drawdown_strategy_uses_numeric_second_threshold() -> None:
    peak = RuleFeature(
        id="offensive_peak_drop",
        category="offensive",
        label="Peak",
        active=True,
        severity="tranche",
        value="16.0% unter 20T-Hoch",
        threshold="8%",
        detail="",
        signal_date="",
        contribution_percent=25,
        setup={"distance_pct": 16.0, "distance_abs": 16.0, "atr": 2.0},
    )

    recommendations = _peak_drawdown_strategy(
        {
            "peak_drawdown_first_unit": "pct",
            "peak_drawdown_first_value": 8,
            "peak_drawdown_second_unit": "pct",
            "peak_drawdown_second_value": 15,
        },
        {"offensive_peak_drop": peak},
    )

    assert recommendations[0].active is True
    assert recommendations[1].active is True


def test_old_default_custom_strategy_steps_switch_to_rs_default() -> None:
    request = SellEvaluationRequest(
        manual=SellManualInput(
            ticker="NVDA",
            sell_setup={"strategy_key": "custom", "custom_strategy_steps": LEGACY_CUSTOM_STRATEGY_STEPS},
        )
    )

    evaluation = evaluate_position_sell_decision("NVDA", request)

    assert evaluation.strategy.strategy_key == "rs_line"
    assert len(evaluation.manual.sell_setup["custom_strategy_steps"]) == 1
    assert evaluation.manual.sell_setup["custom_strategy_steps"][0]["feature_id"] == "emergency_loss_limit"


def test_custom_strategy_default_starts_with_nothalt_only() -> None:
    request = SellEvaluationRequest(
        manual=SellManualInput(
            ticker="NVDA",
            sell_setup={"strategy_key": "custom"},
        )
    )

    evaluation = evaluate_position_sell_decision("NVDA", request)

    assert evaluation.strategy.strategy_key == "custom"
    assert len(evaluation.strategy.recommendations) == 1
    assert evaluation.strategy.recommendations[0].feature_ids == ["emergency_loss_limit"]


def test_snooze_state_changes_pending_status() -> None:
    before = evaluate_position_sell_decision("EMAB")
    assert before.sell_now_percent > 0

    snooze_sell_signal("EMAB", SnoozeRequest(snoozed_pct=100, days=5))
    after = evaluate_position_sell_decision("EMAB")

    assert after.pending_status == "snoozed"
    assert after.next_recommendation_state.snoozed_pct == 100


def test_sell_ranking_exposes_persisted_recommendation_state() -> None:
    snooze_sell_signal("EMAB", SnoozeRequest(snoozed_pct=100, days=5))

    ranking = get_sell_position_ranking()
    emab = next(row for row in ranking.rows if row.ticker == "EMAB")

    assert emab.pending_status == "snoozed"
    assert emab.snoozed_pct == 100
    assert emab.snoozed_until
    assert emab.consecutive_days >= 0


def test_sell_ranking_prefers_imported_portfolio_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        PortfolioPositionRow(
            ticker="AAPL",
            name="Apple",
            shares=3,
            entry_price=100,
            current_price=130,
            currency="USD",
            buy_date=date(2025, 1, 15),
            broker="Test",
            account="Main",
        )
    ]
    monkeypatch.setattr(sell_service.portfolio_repository, "list_open_positions", lambda: rows)
    monkeypatch.setattr(
        sell_service.prices_repository,
        "list_price_bars",
        lambda ticker, *args, **kwargs: _price_bars(start=410, step=0.12)
        if ticker.upper() == "SPY"
        else _price_bars(start=100, step=0.20),
    )

    ranking = get_sell_position_ranking()
    metrics = get_sell_metrics_for_position("AAPL")
    evaluation = evaluate_position_sell_decision("AAPL")

    assert [row.ticker for row in ranking.rows] == ["AAPL"]
    assert ranking.rows[0].name == "Apple"
    assert metrics.current_price == pytest.approx(100 + 279 * 0.20, abs=0.01)
    assert metrics.pnl_pct == pytest.approx((metrics.current_price / 100 - 1) * 100, abs=0.01)
    assert evaluation.ticker == "AAPL"


def test_sell_metrics_use_price_cache_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        PortfolioPositionRow(
            ticker="AAPL",
            name="Apple",
            shares=3,
            entry_price=100,
            current_price=145,
            currency="USD",
            buy_date=date(2025, 1, 15),
            broker="Test",
            account="Main",
        )
    ]

    def fake_price_bars(ticker: str, *, start_date=None):
        if ticker.upper() == "SPY":
            return _price_bars(start=410, step=0.12)
        return _price_bars(start=100, step=0.20)

    monkeypatch.setattr(sell_service.portfolio_repository, "list_open_positions", lambda: rows)
    monkeypatch.setattr(sell_service.prices_repository, "list_price_bars", fake_price_bars)

    metrics = get_sell_metrics_for_position("AAPL")

    assert metrics.raw_payload.metrics["price_data_source"] == "database"
    assert metrics.raw_payload.metrics["benchmark_data_source"] == "database"
    assert metrics.current_price == pytest.approx(100 + 279 * 0.20, abs=0.01)
    assert metrics.pnl_pct == pytest.approx((metrics.current_price / 100 - 1) * 100, abs=0.01)


def test_monitor_open_positions_persists_recommendation_state(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        PortfolioPositionRow(
            ticker="AAPL",
            name="Apple",
            shares=3,
            entry_price=100,
            current_price=130,
            currency="USD",
            buy_date=date(2025, 1, 15),
            broker="Test",
            account="Main",
        )
    ]
    monkeypatch.setattr(sell_service.portfolio_repository, "list_open_positions", lambda: rows)
    monkeypatch.setattr(
        sell_service.prices_repository,
        "list_price_bars",
        lambda ticker, *args, **kwargs: _price_bars(start=410, step=0.12)
        if ticker.upper() == "SPY"
        else _price_bars(start=100, step=0.20),
    )

    result = sell_service.monitor_open_positions()
    ranking = get_sell_position_ranking()

    assert result["ok"] is True
    assert result["records_seen"] == 1
    assert result["ranking_snapshot_written"] == 1
    assert result["items"][0]["ticker"] == "AAPL"
    assert result["items"][0]["recommendation_percent"] >= 0
    assert ranking.source == "snapshot"
    assert [row.ticker for row in ranking.rows] == ["AAPL"]


def test_monitor_open_positions_reports_atr_threshold_crossing(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        PortfolioPositionRow(
            ticker="AAPL",
            name="Apple",
            shares=3,
            entry_price=100,
            current_price=65,
            currency="USD",
            buy_date=date(2025, 1, 15),
            broker="Test",
            account="Main",
        )
    ]

    def fake_price_bars(ticker: str, *, start_date=None):
        if ticker.upper() == "SPY":
            return _price_bars(start=410, step=0.12)
        return _price_bars(start=120, step=-0.2)

    monkeypatch.setattr(sell_service.portfolio_repository, "list_open_positions", lambda: rows)
    monkeypatch.setattr(sell_service.prices_repository, "list_price_bars", fake_price_bars)
    monkeypatch.setattr(
        sell_service,
        "_position_monitor_live_quotes",
        lambda rows: {
            "AAPL": FetchedLiveQuote(
                ticker="AAPL",
                price=65,
                quote_at=datetime(2026, 6, 18, tzinfo=UTC),
                trade_date=date(2026, 6, 18),
                source="test",
                fetched_at=datetime(2026, 6, 18, tzinfo=UTC),
                error_message="",
            )
        },
    )

    result = sell_service.monitor_open_positions(
        monitor_settings={
            "position_monitor_enabled": True,
            "position_monitor_reference": "high_since_buy",
            "position_monitor_threshold_atr": 1.0,
            "position_monitor_atr_period": 21,
            "position_monitor_lookback_days": 280,
            "position_monitor_cooldown_hours": 12,
        }
    )

    monitor = result["items"][0]["monitor"]
    assert monitor["reference"] == "high_since_buy"
    assert monitor["atr_period"] == 21
    assert monitor["threshold_crossed"] is True
    assert monitor["distance_atr"] >= 1.0


def test_lightweight_atr_monitor_avoids_full_sell_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        PortfolioPositionRow(
            ticker="AAPL",
            name="Apple",
            shares=3,
            entry_price=100,
            current_price=100,
            currency="USD",
            buy_date=date(2025, 1, 15),
            broker="Test",
            account="Main",
        )
    ]
    dates = pd.date_range("2026-05-01", periods=40, freq="D")
    closes = pd.Series([100.0 + offset * 0.1 for offset in range(40)], index=dates)
    frame = pd.DataFrame(
        {
            "Open": closes,
            "High": closes + 1.0,
            "Low": closes - 1.0,
            "Close": closes,
            "Volume": 1_000_000,
        },
        index=dates,
    )
    live_trade_date = dates[-1].date() + timedelta(days=1)
    live_price = float(closes.iloc[-1] - 3.0)
    monkeypatch.setattr(sell_service, "_portfolio_positions", lambda: rows)
    monkeypatch.setattr(sell_service, "_price_frame_from_cache", lambda ticker: frame)
    monkeypatch.setattr(
        sell_service,
        "_position_monitor_live_quotes",
        lambda rows: {
            "AAPL": FetchedLiveQuote(
                ticker="AAPL",
                price=live_price,
                quote_at=datetime.combine(live_trade_date, datetime.min.time(), UTC),
                trade_date=live_trade_date,
                source="test_live_batch",
                fetched_at=datetime.combine(live_trade_date, datetime.min.time(), UTC),
            )
        },
    )
    monkeypatch.setattr(
        sell_service,
        "get_sell_metrics_for_position",
        lambda *args, **kwargs: pytest.fail("lightweight ATR monitor must not run the full sell engine"),
    )

    result = sell_service.monitor_open_position_atr(
        monitor_settings={
            "position_monitor_enabled": True,
            "position_monitor_reference": "previous_close",
            "position_monitor_threshold_atr": 1.0,
            "position_monitor_atr_period": 14,
            "position_monitor_lookback_days": 90,
        }
    )

    monitor = result["items"][0]["monitor"]
    assert result["live_quotes_available"] == 1
    assert monitor["current_price_source"] == "test_live_batch"
    assert monitor["reference_price"] == round(float(closes.iloc[-1]), 2)
    assert monitor["threshold_crossed"] is True


def test_monitor_reference_price_uses_previous_close() -> None:
    row = PortfolioPositionRow(
        ticker="AAPL",
        name="Apple",
        shares=3,
        entry_price=95,
        current_price=90,
        currency="USD",
        buy_date=date(2025, 1, 15),
        broker="Test",
        account="Main",
    )
    frame = pd.DataFrame(
        {"high": [102.0, 103.0, 94.0], "low": [98.0, 99.0, 88.0], "close": [100.0, 101.5, 90.0]},
        index=pd.to_datetime(["2025-02-03", "2025-02-04", "2025-02-05"]),
    )

    assert (
        sell_service._monitor_reference_price(
            daily_frame=frame,
            row=row,
            current_price=90.0,
            reference_mode="previous_close",
            lookback_days=420,
        )
        == 101.5
    )


def test_monitor_reference_price_uses_latest_cached_close_before_live_trade_date() -> None:
    row = PortfolioPositionRow(
        ticker="AAPL",
        name="Apple",
        shares=3,
        entry_price=95,
        current_price=88,
        currency="USD",
        buy_date=date(2025, 1, 15),
        broker="Test",
        account="Main",
    )
    frame = pd.DataFrame(
        {"high": [103.0, 94.0], "low": [99.0, 88.0], "close": [101.5, 90.0]},
        index=pd.to_datetime(["2025-02-04", "2025-02-05"]),
    )

    assert (
        sell_service._monitor_reference_price(
            daily_frame=frame,
            row=row,
            current_price=88,
            reference_mode="previous_close",
            lookback_days=90,
            current_trade_date=date(2025, 2, 6),
        )
        == 90.0
    )


def _price_bars(*, start: float, step: float, periods: int = 280):
    return [
        SimpleNamespace(
            date=date.fromordinal(date(2025, 1, 1).toordinal() + offset),
            open=start + offset * step - 0.1,
            high=start + offset * step + 1.0,
            low=start + offset * step - 1.0,
            close=start + offset * step,
            adj_close=start + offset * step,
            volume=1_000_000 + offset * 1_000,
        )
        for offset in range(periods)
    ]
