"""Service integration: actual detector, safe segments, maintenance budgets."""

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, UTC
from types import SimpleNamespace

import pytest

from app.services import chart_analysis as service
from app.workers.tasks.common import JobCancelled
from tests.domain.test_chart_patterns import fixture


@pytest.fixture
def setup(monkeypatch):
    store = {}
    bars = fixture()
    rows = {"TEST": [SimpleNamespace(**b.__dict__) for b in bars]}
    monkeypatch.setattr(
        service.repository, "_read_json_setting", lambda key: deepcopy(store.get(key, {}))
    )
    monkeypatch.setattr(
        service.repository,
        "_write_json_setting",
        lambda key, value, **kw: store.update({key: deepcopy(value)}),
    )
    monkeypatch.setattr(
        service, "_scan_stocks", lambda: [(ticker, ticker, ticker, {}) for ticker in rows]
    )
    monkeypatch.setattr(
        service,
        "completed_ticker_market_session",
        lambda ticker: SimpleNamespace(date=bars[-1].date),
    )
    monkeypatch.setattr(
        service, "list_price_bars_for_tickers", lambda tickers, **kw: {t: rows[t] for t in tickers}
    )
    monkeypatch.setattr(service, "list_price_bars", lambda ticker, **kw: rows[ticker])
    monkeypatch.setattr(service, "_split_events", lambda ticker: {})
    return SimpleNamespace(store=store, bars=bars, rows=rows)


def test_clean_scan_matches_chart_and_old_algorithm_is_obsolete(setup):
    service.scan_universe()
    result = service.get_results()
    assert result["analysed_count"] == 1 and result["partial_count"] == 0
    assert result["quality_issues"] == [] and not result["obsolete"]
    assert {p["id"] for p in result["rows"]} == {
        p["id"] for p in service.analyse("TEST")["patterns"]
    }
    setup.store[service.RESULT_KEY]["algorithm_version"] = "old"
    assert service.get_results()["obsolete"]


def test_partial_history_preserves_clean_cup_without_crossing_broken_row(setup):
    # A bad first observation leaves the known later cup wholly intact.
    setup.rows["TEST"][0].high = float("nan")
    chart = service.analyse("TEST")
    assert chart["quality"]["partial"]
    assert any(p["kind"] == "cup_with_handle" for p in chart["patterns"])
    assert all(p["start_date"] > setup.bars[0].date.isoformat() for p in chart["patterns"])
    service.scan_universe()
    result = service.get_results()
    assert result["analysed_count"] == 1 and result["partial_count"] == 1
    assert result["skipped_count"] == 0 and result["quality_counts"]["invalid_ohlc"] == 1


def test_broken_cup_cannot_be_recovered_by_connecting_sections(setup):
    setup.rows["TEST"][92].high = 0
    chart = service.analyse("TEST")
    assert not any(p["kind"] == "cup_with_handle" for p in chart["patterns"])


def test_ended_section_labels_status_limit_and_preserves_causal_geometry(setup, monkeypatch):
    before = service.analyse("TEST")
    bad = replace(setup.bars[-1], date=setup.bars[-1].date + timedelta(days=1), high=0)
    setup.rows["TEST"].append(SimpleNamespace(**bad.__dict__))
    monkeypatch.setattr(
        service, "completed_ticker_market_session", lambda t: SimpleNamespace(date=bad.date)
    )
    after = service.analyse("TEST")
    assert [p["id"] for p in before["patterns"]] == [p["id"] for p in after["patterns"]]
    assert all(p["continuity_limited"] for p in after["patterns"])
    assert all("Spätere Gültigkeit unbekannt" in p["warnings"][-1] for p in after["patterns"])


def test_repair_is_worker_only_and_success_is_rechecked_from_cache(setup, monkeypatch):
    setup.rows["TEST"][0].high = 0
    calls = []

    def repair(*args, **kwargs):
        calls.append(args[0])
        setup.rows["TEST"][0].high = setup.bars[0].high
        return {"records_written": len(setup.bars), "reason_code": "repaired"}

    monkeypatch.setattr(service, "repair_chart_history", repair)
    service.analyse("TEST")
    assert not calls
    service.scan_universe(repair_prices=True)
    assert calls == ["TEST"]
    assert service.get_results()["repair_summary"]["succeeded"] == 1
    assert service.get_results()["partial_count"] == 0


def test_budget_priority_and_cooldown_preserve_usable_sections(setup, monkeypatch):
    setup.rows["TEST"][0].high = 0
    setup.rows["EMPTY"] = []
    calls = []
    monkeypatch.setattr(
        service,
        "repair_chart_history",
        lambda ticker, *a, **kw: calls.append(ticker) or {"reason_code": "provider_empty"},
    )
    service.scan_universe(repair_prices=True, repair_limit=1)
    assert calls == ["TEST"]
    summary = service.get_results()["repair_summary"]
    assert summary["attempted"] == 1 and summary["deferred"] == 1 and summary["failed"] == 1
    calls.clear()
    service.scan_universe(repair_prices=True, repair_limit=1)
    assert calls == ["EMPTY"]
    assert service.get_results()["repair_summary"]["cooldown"] == 1


def test_rate_limit_stops_remaining_requests_and_snapshot_still_completes(setup, monkeypatch):
    setup.rows["TEST"][0].high = 0
    setup.rows["EMPTY"] = []
    calls = []
    monkeypatch.setattr(
        service,
        "repair_chart_history",
        lambda ticker, *a, **kw: calls.append(ticker) or {"reason_code": "rate_limited"},
    )
    service.scan_universe(repair_prices=True)
    assert len(calls) == 1
    assert service.get_results()["repair_summary"]["deferred"] == 1
    assert service.get_results()["available"]


def test_new_issue_bypasses_previous_success_cooldown_but_same_issue_waits(setup, monkeypatch):
    setup.rows["TEST"][0].high = 0
    calls = []

    def repair(*args, **kwargs):
        calls.append(args[0])
        setup.rows["TEST"][0].high = setup.bars[0].high
        return {"records_written": len(setup.bars), "reason_code": "repaired"}

    monkeypatch.setattr(service, "repair_chart_history", repair)
    service.scan_universe(repair_prices=True)
    assert calls == ["TEST"]
    assert setup.store[service.REPAIR_KEY]["TEST"]["issue_signature"] == []
    # A newly broken observation is independent of the successful prior repair.
    setup.rows["TEST"][1].high = 0
    monkeypatch.setattr(
        service,
        "repair_chart_history",
        lambda ticker, *a, **kw: calls.append(ticker) or {"reason_code": "provider_empty"},
    )
    service.scan_universe(repair_prices=True)
    assert calls == ["TEST", "TEST"]
    service.scan_universe(repair_prices=True)
    assert calls == ["TEST", "TEST"]
    assert service.get_results()["repair_summary"]["cooldown"] == 1


def test_untried_symbols_are_not_starved_by_expired_old_failures(setup, monkeypatch):
    setup.rows["TEST"][0].high = 0
    setup.rows["EMPTY"] = []
    past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    setup.store[service.REPAIR_KEY] = {"TEST": {"checked_at": past, "next_retry_at": past}}
    calls = []
    monkeypatch.setattr(
        service,
        "repair_chart_history",
        lambda ticker, *a, **kw: calls.append(ticker) or {"reason_code": "provider_empty"},
    )
    service.scan_universe(repair_prices=True, repair_limit=1)
    assert calls == ["EMPTY"]


def test_cancellation_does_not_publish_partial_scan(setup, monkeypatch):
    service.scan_universe()
    before = deepcopy(setup.store[service.RESULT_KEY])

    def cancel():
        raise JobCancelled("test")

    with pytest.raises(JobCancelled):
        service.scan_universe(cancelled=cancel, repair_prices=True)
    assert setup.store[service.RESULT_KEY] == before


def test_split_evidence_never_changes_prices_or_uses_future_events():
    issues = [{"code": "extreme_jump", "date": "2026-10-20", "reason": "Verdachtsfall"}]
    service._split_issues(issues, {"2026-10-19": 0.1, "2026-10-21": 5}, cutoff=date(2026, 10, 20))
    assert issues[0]["split_events"] == [{"date": "2026-10-19", "ratio": 0.1}]
    assert "keine automatische" in issues[0]["reason"]


def test_retry_after_malformed_or_naive_timestamp_is_safe():
    now = datetime.now(UTC)
    assert service._retry_due({}, now)
    assert not service._retry_due({"next_retry_at": (now + timedelta(days=1)).isoformat()}, now)
    assert service._retry_due({"next_retry_at": "bad"}, now)
