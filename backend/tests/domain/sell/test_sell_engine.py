from __future__ import annotations

from datetime import date
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.sell import service as sell_service
from app.domain.sell.schemas import SnoozeRequest, TrancheLogEntry
from app.domain.sell.service import (
    clear_sell_engine_state,
    create_tranche_log_entry,
    evaluate_position_sell_decision,
    get_sell_metrics_for_position,
    get_sell_position_ranking,
    snooze_sell_signal,
)
from app.repositories.portfolio import PortfolioPositionRow


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "sell"


@pytest.fixture(autouse=True)
def reset_sell_state() -> None:
    clear_sell_engine_state()


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
    before = evaluate_position_sell_decision("NVDA")
    assert before.sell_now_percent > 0

    create_tranche_log_entry(
        "NVDA",
        TrancheLogEntry(ticker="NVDA", pct=25, reason="Golden-master partial sale"),
    )
    after = evaluate_position_sell_decision("NVDA")

    assert after.already_sold_percent == 25
    assert after.sell_now_percent < before.sell_now_percent
    assert after.tranche_log[0].reason == "Golden-master partial sale"


def test_snooze_state_changes_pending_status() -> None:
    before = evaluate_position_sell_decision("NVDA")
    assert before.sell_now_percent > 0

    snooze_sell_signal("NVDA", SnoozeRequest(snoozed_pct=100, days=5))
    after = evaluate_position_sell_decision("NVDA")

    assert after.pending_status == "snoozed"
    assert after.next_recommendation_state.snoozed_pct == 100


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
    monkeypatch.setattr(sell_service.prices_repository, "list_price_bars", lambda *args, **kwargs: [])

    ranking = get_sell_position_ranking()
    metrics = get_sell_metrics_for_position("AAPL")
    evaluation = evaluate_position_sell_decision("AAPL")

    assert [row.ticker for row in ranking.rows] == ["AAPL"]
    assert ranking.rows[0].name == "Apple"
    assert metrics.current_price == pytest.approx(130, abs=0.01)
    assert metrics.pnl_pct == pytest.approx(30, abs=0.01)
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
    monkeypatch.setattr(sell_service.prices_repository, "list_price_bars", lambda *args, **kwargs: [])

    result = sell_service.monitor_open_positions()

    assert result["ok"] is True
    assert result["records_seen"] == 1
    assert result["items"][0]["ticker"] == "AAPL"
    assert result["items"][0]["recommendation_percent"] >= 0


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
