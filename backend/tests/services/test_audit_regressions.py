from datetime import UTC, date, datetime

import pandas as pd
import pytest

from app.domain.sell import service as sell
from app.repositories.market import MarketOhlcvPoint
from app.schemas import VolatilityResponse
from app.services import market, portfolio, settings, refresh_attempts, fx
from app.services.market_calendar import daily_bar_is_final, price_is_current
from app.services.assessment_quality import dependency_quality
from app.services.freshness import _earnings_schedule_lag_minutes


def test_intraday_bar_does_not_become_final_without_an_evening_fetch():
    day = date(2026, 9, 11)
    intraday_fetch = datetime(2026, 9, 11, 14, tzinfo=UTC)
    weekend = datetime(2026, 9, 13, 12, tzinfo=UTC)
    assert not daily_bar_is_final(day, intraday_fetch, now=weekend)
    assert not price_is_current(day, intraday_fetch, now=weekend)
    assert daily_bar_is_final(day, datetime(2026, 9, 11, 20, 30, tzinfo=UTC), now=weekend)
    assert not daily_bar_is_final(day, None, now=weekend)


def test_intraday_quote_is_current_but_not_a_confirmed_daily_bar():
    now = datetime(2026, 9, 11, 14, 30, tzinfo=UTC)
    assert price_is_current(now.date(), now, now=now)
    assert not daily_bar_is_final(now.date(), now, now=now)


def test_ampel_cycle_does_not_depend_on_chart_window(monkeypatch):
    dates = pd.bdate_range("2024-01-02", periods=650)
    bars = [MarketOhlcvPoint(
        ticker="^GSPC", date=day.date(), open=100 + i / 10,
        high=102 + i / 10, low=99 + i / 10, close=101 + i / 10, volume=1000,
    ) for i, day in enumerate(dates)]
    starts = []

    def load(ticker, *, start_date):
        starts.append(start_date)
        return bars, ticker

    monkeypatch.setattr(market, "_load_cached_index_ohlcv", load)
    monkeypatch.setattr(market, "daily_bar_is_final", lambda *args, **kwargs: True)
    monkeypatch.setattr(market.market_repository, "get_latest_market_snapshot", lambda: None)
    monkeypatch.setattr(market, "get_volatility", lambda: VolatilityResponse(as_of="2026-09-11", source="missing", regime="n/a", status_cards=[], points=[]))
    monkeypatch.setattr(market, "_cached_intermarket_divergence", lambda: [])
    monkeypatch.setattr(market, "_cached_sector_rotation", lambda: ([], None, None))
    responses = [market.get_market_ampel(days=days) for days in (60, 90, 130, 200)]
    assert starts == [date(1900, 1, 1)] * 4
    assert len({response.phase_info.model_dump_json() for response in responses}) == 1
    assert len({response.cycle.model_dump_json() for response in responses}) == 1
    assert [len(response.chart_points) for response in responses] == [60, 90, 130, 200]


def test_sell_ohlc_and_entry_share_the_same_currency(monkeypatch):
    frame = pd.DataFrame({"Open": [45.0], "High": [46.0], "Low": [44.0], "Close": [44.25], "Volume": [1000]})
    monkeypatch.setattr(sell, "cached_currency_usd_factor", lambda currency: {"EUR": 1.1597, "USD": 1.0}[currency])
    result = sell._sell_frame_in_currency(frame, "ZPDH.DE", "USD")
    assert result.Close.iloc[-1] == pytest.approx(44.25 * 1.1597)
    assert result.High.iloc[-1] - result.Low.iloc[-1] == pytest.approx(2 * 1.1597)
    assert result.Volume.iloc[-1] == 1000
    assert frame.Close.iloc[-1] == 44.25


def test_missing_fx_never_produces_a_sell_recommendation(monkeypatch):
    monkeypatch.setattr(sell, "cached_currency_usd_factor", lambda currency: None)
    with pytest.raises(sell.SellMarketDataUnavailableError):
        sell._sell_frame_in_currency(pd.DataFrame({"Close": [44.25]}), "ZPDH.DE", "USD")


def test_monitor_does_not_convert_usd_metrics_twice(monkeypatch):
    from app.repositories.portfolio import PortfolioPositionRow
    row = PortfolioPositionRow(ticker="ZPDH.DE", name="Test", shares=10, entry_price=50, current_price=44.25, currency="USD", buy_date=date(2026, 1, 1))
    monkeypatch.setattr(sell, "cached_currency_usd_factor", lambda currency: 1.1597 if currency == "EUR" else 1.0)
    monkeypatch.setattr(sell, "currency_to_usd", lambda value, currency: float(value) * (1.1597 if currency == "EUR" else 1.0))
    monkeypatch.setattr(sell, "_monitor_reference_price", lambda **kwargs: 52.0)
    monkeypatch.setattr(sell, "_monitor_atr", lambda *args: 2.0)
    result = sell._monitor_state_from_frame(row, pd.DataFrame(), {}, current_price_override=44.25,
        current_price_source="test", current_trade_date=date(2026, 9, 11), frame_currency="USD")
    assert result["reference_price"] == 52.0
    assert result["atr_value"] == 2.0
    assert result["distance_atr"] == pytest.approx(round((52 - 44.25 * 1.1597) / 2, 2))


def test_pence_conversion_is_not_pounds(monkeypatch):
    monkeypatch.setattr(fx, "_latest_cached_fx_rate", lambda *args, **kwargs: fx.FxRate("GBP/USD", 1.3, date(2099, 1, 1), "test"))
    assert fx.cached_currency_usd_factor("GBP") == 1.3
    assert fx.cached_currency_usd_factor("GBp") == pytest.approx(0.013)
    assert fx.cached_currency_usd_factor("GBX") == pytest.approx(0.013)


def test_old_fundamentals_and_13f_are_not_current():
    quality = dependency_quality({"as_of": "2026-01-01"}, {"report_period": "2026-03-31"}, {}, today=date(2026, 9, 13))
    assert quality["fundamentals"]["status"] == "stale"
    assert quality["institutional"]["status"] == "stale"
    assert quality["institutional"]["expected"] == "2026-06-30"
    assert quality["rs"]["status"] == "missing"


def test_curve_failure_does_not_fall_back_to_current_holdings(monkeypatch):
    def fail(**kwargs):
        raise ValueError("duplicate labels")
    monkeypatch.setattr(portfolio, "_get_trade_republic_curve", fail)
    monkeypatch.setattr(portfolio.portfolio_repository, "list_open_positions", lambda: pytest.fail("Historical failure must not load current holdings"))
    result = portfolio.get_portfolio_curve()
    assert result.data_status == "missing"
    assert "duplicate labels" in result.message


def test_header_does_not_compute_a_full_diagnosis(monkeypatch):
    monkeypatch.setattr(settings.settings_repository, "_read_json_setting", lambda key: {"decision_status": "trusted", "generated_at": "2026-01-01T00:00:00+00:00"})
    monkeypatch.setattr(settings, "get_data_diagnostics", lambda: pytest.fail("Expensive diagnosis in header"))
    from app.services import system_quality
    monkeypatch.setattr(system_quality, "get_system_quality", lambda: {"decision_status": "trusted"})
    assert settings.get_data_quality_summary()["decision_status"] == "trusted"


def test_retry_history_is_persistent_and_backs_off(monkeypatch):
    state = {}
    monkeypatch.setattr(refresh_attempts, "_read_json_setting", lambda key: dict(state.get(key, {})))
    monkeypatch.setattr(refresh_attempts, "_write_json_setting", lambda key, values, **kwargs: state.update({key: values}))
    refresh_attempts.record_attempt("FAILED", error="provider unavailable")
    first = state[refresh_attempts.KEY + "FAILED"]
    refresh_attempts.record_attempt("FAILED", error="provider unavailable")
    assert state[refresh_attempts.KEY + "FAILED"]["failures"] == 2
    assert state[refresh_attempts.KEY + "FAILED"]["next_attempt"] > first["next_attempt"]
    assert not refresh_attempts.retry_due(state[refresh_attempts.KEY + "FAILED"], datetime.now(UTC))


def test_earnings_freshness_respects_weekend():
    sunday = datetime(2026, 9, 13, 12, tzinfo=UTC)
    assert _earnings_schedule_lag_minutes(sunday) > 26 * 60


def test_failing_priority_symbol_does_not_starve_pending_universe(monkeypatch):
    from app.workers.tasks import smart_refresh_market_data as smart
    monkeypatch.setattr(smart, "read_attempts", lambda: {"FAILED": {"next_attempt": "2099-01-01T00:00:00+00:00"}})
    selected, skipped, deferred = smart._select_fundamental_work(
        ["FAILED", "NEW"], latest_states={}, incremental=True, max_refresh_count=1,
        freshness_days=14, priority_tickers=["FAILED"],
    )
    assert selected == ["NEW"]
    assert deferred == 1
    assert skipped == 0


def test_13f_universe_is_not_truncated_to_5000():
    from app.services.sec13f import _resolve_universe
    tickers = [f"TEST{i}" for i in range(5593)]
    assert _resolve_universe({"tickers": tickers, "limit": 10000}) == tickers


def test_unchanged_13f_artifacts_are_not_written_again(monkeypatch):
    from app.services import sec13f
    from app.data_sources.sec13f_client import Sec13FBuildResult
    monkeypatch.setattr(sec13f, "_resolve_universe", lambda payload: ["NVDA"])
    monkeypatch.setattr(sec13f, "_load_manual_overrides", lambda: {})
    monkeypatch.setattr(sec13f, "get_runtime_config_value", lambda key: "test")
    monkeypatch.setattr(sec13f, "_read_json_setting", lambda key: {"revision": "same"})
    monkeypatch.setattr(sec13f, "build_institutional_13f_payload", lambda **kwargs: Sec13FBuildResult(
        payload={"tickers": {"NVDA": {}}}, mapping_rows=[], unmatched_rows=[],
        metadata={"artifact_revision": "same", "current_period": "2026-03-31"},
    ))
    monkeypatch.setattr(sec13f, "_ticker_breakdown", lambda **kwargs: [])
    monkeypatch.setattr(sec13f, "ingest_institutional_13f_payload", lambda payload: pytest.fail("Unchanged aggregates rewritten"))
    result = sec13f.refresh_institutional_13f_from_sec({})
    assert result["records_written"] == 0
    assert result["source_unchanged"]
    assert result["metadata"]["current_period"] == "2026-03-31"
