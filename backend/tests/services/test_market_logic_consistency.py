from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from app.db.models import MarketSnapshot, PriceBar
from app.domain.market.ampel import AMPEL_RULESET_VERSION, compute_trend_ampel
from app.repositories import market as repository
from app.repositories.market import MarketOhlcvPoint
from app.services import home, market, trade_journal_backfill as journal
from app.services.settings import DEFAULT_SETTINGS


@pytest.fixture
def market_inputs(monkeypatch):
    closes = [100.0] * 250 + [96, 92, 90, 92, 92.3, 92.6, 94]
    dates = pd.bdate_range(end="2026-10-02", periods=len(closes))
    bars = [dict(date=day.date(), open=closes[max(0, i-1)],
                 high=max(close, closes[max(0, i-1)]) + .5,
                 low=min(close, closes[max(0, i-1)]) - .5, close=close,
                 volume=1_500_000 if i == len(closes)-1 else 1_000_000)
            for i, (day, close) in enumerate(zip(dates, closes))]
    state = {"logic": "current"}
    snapshot = MarketSnapshot(date=dates[-1].date(), ampel_phase="rot", warning_count=0,
                              breadth_mode="wachsam", volatility_regime="Risk On / ruhig", metrics_json={})
    rows = [MarketOhlcvPoint(ticker="^GSPC", **bar) for bar in bars]
    monkeypatch.setattr(market, "get_app_settings", lambda: DEFAULT_SETTINGS.model_copy(
        update={"market_ampel_logic": state["logic"]}))
    monkeypatch.setattr(repository, "get_latest_market_snapshot", lambda: snapshot)
    monkeypatch.setattr(repository, "list_breadth_daily", lambda *a, **k: [])
    monkeypatch.setattr(repository, "load_latest_close_pairs", lambda *a, **k: {})
    monkeypatch.setattr(market, "_load_cached_index_ohlcv", lambda *a, **k: (rows, "^GSPC"))
    monkeypatch.setattr(market, "_confirmed_ampel_bars", lambda bars: bars)
    monkeypatch.setattr(journal, "_bars_for_ticker", lambda *a: [PriceBar(**bar) for bar in bars])
    return state, snapshot, bars


def test_setting_switch_updates_home_without_worker_snapshot(market_inputs):
    state, snapshot, _bars = market_inputs
    assert home._market_summary()["phase"] == "rot"
    state["logic"] = "ibd"
    assert market.get_market_overview().phase == "gelb_startschuss"
    summary = home._market_summary()
    assert summary["phase"] == "gelb_startschuss"
    assert summary["logic"] == "ibd"
    assert snapshot.ampel_phase == "rot"


def test_home_cache_changes_immediately_with_logic(monkeypatch):
    state = {"logic": "current"}
    calls = []
    monkeypatch.setattr(home, "_selected_market_ampel_logic", lambda: state["logic"])
    monkeypatch.setattr(home, "_home_cache", None)

    def dashboard():
        calls.append(state["logic"])
        return {"market": {"logic": state["logic"]}}

    monkeypatch.setattr(home, "get_home_dashboard", dashboard)
    assert home.get_cached_home_dashboard()["market"]["logic"] == "current"
    state["logic"] = "ibd"
    assert home.get_cached_home_dashboard()["market"]["logic"] == "ibd"
    assert home.get_cached_home_dashboard()["market"]["logic"] == "ibd"
    assert calls == ["current", "ibd"]


def test_home_does_not_use_snapshot_of_other_logic(market_inputs, monkeypatch):
    state, _snapshot, _bars = market_inputs
    state["logic"] = "ibd"
    monkeypatch.setattr(home, "_market_trend_ampel_for_ticker", lambda *a, **k: None)
    assert home._market_summary()["phase"] is None


def test_overview_does_not_use_snapshot_of_other_logic(market_inputs, monkeypatch):
    state, _snapshot, _bars = market_inputs
    state["logic"] = "ibd"
    monkeypatch.setattr(market, "_market_trend_ampel_for_ticker", lambda *a, **k: None)
    response = market.get_market_overview()
    assert response.data_status == "missing"
    assert response.phase != "rot"


def test_missing_previous_volume_cannot_confirm_ftd(market_inputs):
    _state, _snapshot, bars = market_inputs
    baseline = compute_trend_ampel(bars, logic="ibd")
    assert baseline[-1].phase == "gelb_startschuss"
    bars[-2]["volume"] = None
    assert compute_trend_ampel(bars, logic="ibd")[-1].phase == "rot"


class Database:
    def __init__(self, snapshot):
        self.values = iter([None, snapshot, None, None])

    def scalar(self, statement):
        return next(self.values)


def reconstructed(snapshot):
    return journal._market_context(Database(snapshot), date(2026, 10, 2),
                                   datetime(2026, 10, 3, tzinfo=UTC))


def test_unrecorded_history_uses_selected_logic_with_explicit_notice(market_inputs):
    state, snapshot, _bars = market_inputs
    old = reconstructed(snapshot)
    state["logic"] = "ibd"
    new = reconstructed(snapshot)
    payload = new["payload"]
    assert payload["trend"]["phase"] == "gelb_startschuss"
    assert payload["trend"]["logic"] == "ibd"
    assert payload["trend"]["ruleset_version"] == AMPEL_RULESET_VERSION
    assert payload["logic_origin"] == "current_settings_reconstruction"
    assert not payload["historical_logic_known"]
    assert "historical_market_logic_unknown" in new["reason_codes"]
    assert old["ruleset_hash"] != new["ruleset_hash"]


def test_recorded_historical_logic_survives_settings_switch(market_inputs):
    state, snapshot, _bars = market_inputs
    snapshot.metrics_json = {"market_ampel_logic": "current"}
    state["logic"] = "ibd"
    payload = reconstructed(snapshot)["payload"]
    assert payload["trend"]["phase"] == "rot"
    assert payload["trend"]["logic"] == "current"
    assert payload["historical_logic_known"]
    assert payload["logic_origin"] == "historical_snapshot"


def test_stale_snapshot_cannot_prove_historical_logic(market_inputs):
    state, snapshot, _bars = market_inputs
    snapshot.metrics_json = {"market_ampel_logic": "current"}
    snapshot.date = date(2026, 10, 1)
    state["logic"] = "ibd"
    payload = reconstructed(snapshot)["payload"]
    assert payload["market_ampel_logic"] == "ibd"
    assert not payload["historical_logic_known"]


def test_daily_archive_is_preserved_without_reconstruction(monkeypatch):
    archived = SimpleNamespace(id="archive", session_date=date(2026, 10, 2),
        assessment_version="old", ruleset_hash="old_hash", source="archive",
        payload_json={"market_ampel_logic": "ibd", "trend": {"phase": "gruen"}},
        information_cutoff=datetime(2026, 10, 2, 23, tzinfo=UTC))

    def unexpected(*args, **kwargs):
        raise AssertionError("Archived contexts must not be recalculated")

    monkeypatch.setattr(journal, "_bars_for_ticker", unexpected)
    monkeypatch.setattr(journal, "_selected_market_ampel_logic", unexpected)
    result = journal._market_context(SimpleNamespace(scalar=lambda *a: archived),
        date(2026, 10, 2), datetime(2026, 10, 3, tzinfo=UTC))
    assert result["payload"]["market_ampel_logic"] == "ibd"
    assert result["payload"]["trend"]["phase"] == "gruen"
    assert result["ruleset_hash"] == "old_hash"


def test_manual_market_archive_keeps_logic_when_overview_fails(monkeypatch):
    from app.services import trade_journal

    def unavailable(**kwargs):
        raise RuntimeError("Overview unavailable")

    monkeypatch.setattr(trade_journal, "get_market_overview", unavailable)
    monkeypatch.setattr(trade_journal, "get_market_ampel", lambda **k: market._missing_market_ampel("^GSPC", logic="ibd"))
    archived = trade_journal._market_snapshot()
    assert archived["ampel"]["logic"] == "ibd"
    assert archived["ampel"]["ruleset_version"] == AMPEL_RULESET_VERSION


def test_snapshot_reconstruction_keeps_recorded_logic_and_status(market_inputs):
    state, snapshot, bars = market_inputs
    trend = compute_trend_ampel(bars, logic="ibd")[-1]
    breadth = market.BreadthComputationPoint(
        universe="test", date=snapshot.date, advancers=60, decliners=40, ad_line=20,
        mcclellan=0, pct_above_20sma=60, pct_above_50sma=60, pct_above_200sma=60,
        new_highs=5, new_lows=2, coverage_ratio=1, universe_size=100,
        loaded_universe=100, covered_count=100, valid_for_50sma=100, valid_for_200sma=100,
    )
    write = market.build_market_snapshot(breadth, trend_point=trend)
    snapshot.metrics_json = write.metrics_json
    state["logic"] = "current"
    payload = reconstructed(snapshot)["payload"]
    assert payload["trend"]["logic"] == "ibd"
    assert payload["trend"]["phase"] == trend.phase
    assert payload["historical_logic_known"]
    assert snapshot.metrics_json["trend_ampel"]["ftd_negated"] == trend.ftd_negated
    assert snapshot.metrics_json["trend_ampel"]["powertrend_state"] == trend.powertrend_state


def test_incomplete_ohlc_is_reported_by_ampel_api(market_inputs, monkeypatch):
    state, _snapshot, _bars = market_inputs
    state["logic"] = "ibd"
    rows = [MarketOhlcvPoint("^GSPC", date(2026, 10, day), 100, 101, 100, 100.5, 1000, ohlc_complete=False)
            for day in (1, 2)]
    monkeypatch.setattr(market, "_load_cached_index_ohlcv", lambda *a, **k: (rows, "^GSPC"))
    monkeypatch.setattr(market, "get_volatility", market._empty_volatility)
    monkeypatch.setattr(market, "_cached_intermarket_divergence", lambda: [])
    monkeypatch.setattr(market, "_cached_sector_rotation", lambda: ([], None, None))
    response = market.get_market_ampel()
    assert response.data_status == "partial"
    assert any("OHLC-Daten" in error for error in response.component_errors)
    assert not response.powertrend.formal_active


def test_repository_preserves_missing_low_through_volume_proxy(monkeypatch):
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, statement): return self
        def all(self):
            return [("^GSPC", date(2026, 10, 2), 100, 101, None, 100.5, 0, None)]

    monkeypatch.setattr(repository, "SessionLocal", Session)
    rows = repository.load_cached_ohlcv("^GSPC", start_date=date(2026, 1, 1))
    assert not rows[0].ohlc_complete
    proxy = [MarketOhlcvPoint("SPY", date(2026, 10, 2), 100, 101, 99, 100.5, 1_000)]
    merged = market._merge_proxy_volume(rows, proxy)
    point = compute_trend_ampel([market._trend_bar_from_ohlcv(merged[0])], logic="ibd")[0]
    assert not point.price_data_complete
    assert point.low is None
