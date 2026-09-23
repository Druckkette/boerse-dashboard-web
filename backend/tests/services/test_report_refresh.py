from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

from app.data_sources.provider_guard import retry_seconds
from app.repositories.fundamentals import FundamentalSnapshotWrite
from app.services.filing_events import parse_daily_index
from app.services import report_refresh
from app.services.report_refresh import content_revision, merge_history
from app.workers.tasks.refresh_report_data import retry_delay


def test_partial_history_preserves_periods_but_clears_invalid_growth():
    old = [{"fiscal_period": "2026 Q1", "eps": 1, "growth_yoy_pct": 30}, {"fiscal_period": "2025 Q4", "eps": 2}]
    new = [{"fiscal_period": "2026 Q1", "eps": -1, "growth_yoy_pct": None}]
    merged = merge_history(old, new)
    assert len(merged) == 2
    assert merged[0]["eps"] == -1
    assert merged[0]["growth_yoy_pct"] is None


def test_checks_do_not_invalidate_content_but_actual_values_do():
    row = FundamentalSnapshotWrite("TEST", date(2026, 9, 1), beta=1.2, metadata_json={"report_refresh": {"checked_at": "yesterday"}})
    checked = replace(row, as_of=date(2026, 9, 14), metadata_json={"report_refresh": {"checked_at": "today"}})
    assert content_revision(row) == content_revision(checked)
    assert content_revision(row) != content_revision(replace(row, beta=1.3))


def test_filing_discovery_filters_and_deduplicates():
    text = "\n".join([
        "CIK|Company Name|Form Type|Date Filed|Filename",
        "123|Test|10-Q|2026-09-11|edgar/data/123/0001.txt",
        "123|Test|10-Q/A|2026-09-12|edgar/data/123/0002.txt",
        "123|Test|4|2026-09-13|edgar/data/123/0003.txt",
        "999|Other|10-K|2026-09-13|edgar/data/999/0004.txt",
    ])
    requests = parse_daily_index(text, {"0000000123": ["TEST"]})
    assert len(requests) == 1
    assert requests[0].payload["form"] == "10-Q/A"
    assert requests[0].payload["event_date"] == "2026-09-12"
    assert "0002" in requests[0].revision


def test_backoff_is_bounded_and_honors_retry_after():
    assert retry_seconds("120") == 120
    assert retry_seconds("bad") == 900
    assert retry_seconds("999999") == 86400
    assert retry_delay(1).total_seconds() == 7200
    assert retry_delay(100).days == 7


def test_missing_beta_is_source_wait_not_worker_failure(monkeypatch):
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: SimpleNamespace(beta=None))
    monkeypatch.setattr(report_refresh, "cached_price_beta", lambda ticker: None)
    monkeypatch.setattr(report_refresh, "fetch_fundamentals", lambda *args, **kwargs: SimpleNamespace(beta=None))

    result = report_refresh.refresh_report_group("SPCX", "beta", {})

    assert result["complete"] is False
    assert result["changed"] is False
    assert "Kein Anbieter-Beta" in result["reason"]


def test_cached_price_beta_uses_aligned_adjusted_returns(monkeypatch):
    first = date.today() - timedelta(days=100)
    market = [100.0]
    stock = [50.0]
    for index in range(1, 101):
        change = 0.001 + (index % 11 - 5) * 0.003
        market.append(market[-1] * (1 + change))
        stock.append(stock[-1] * (1 + 1.5 * change))
    bars = {
        "TEST": [SimpleNamespace(date=first + timedelta(days=index), adj_close=value) for index, value in enumerate(stock)],
        "SPY": [SimpleNamespace(date=first + timedelta(days=index), adj_close=value) for index, value in enumerate(market)],
    }
    monkeypatch.setattr(report_refresh.prices, "list_price_bars_for_tickers", lambda *args, **kwargs: bars)
    assert report_refresh.cached_price_beta("TEST") == 1.5
    assert report_refresh.cached_price_beta("SPY") == 1.0


def test_cached_beta_avoids_provider_request(monkeypatch):
    previous = FundamentalSnapshotWrite("TEST", date.today(), beta=None, metadata_json={})
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: previous)
    monkeypatch.setattr(report_refresh, "cached_price_beta", lambda ticker: 1.25)
    monkeypatch.setattr(report_refresh, "fetch_fundamentals", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")))
    monkeypatch.setattr(report_refresh.fundamentals, "upsert_fundamentals", lambda write: write)
    result = report_refresh.refresh_report_group("TEST", "beta", {})
    assert result["complete"] and result["changed"]
    assert result["beta"] == 1.25


def test_missing_statement_history_is_source_wait_not_worker_failure(monkeypatch):
    monkeypatch.setattr(report_refresh.fundamentals, "get_latest_fundamentals", lambda ticker: None)
    monkeypatch.setattr(report_refresh, "get_runtime_config_value", lambda key: "")
    monkeypatch.setattr(report_refresh, "fetch_fundamental_enrichment", lambda *args, **kwargs: SimpleNamespace(**{
        key: [] for key in report_refresh.HISTORIES
    }))

    result = report_refresh.refresh_report_group("SPCX", "statements", {})

    assert result["complete"] is False
    assert result["changed"] is False
    assert "Keine verwertbaren Statements" in result["reason"]


def test_non_periodic_filing_does_not_require_new_quarter():
    enrichment = SimpleNamespace(fiscal_period="2026 Q2", metadata={"report_ends": {}})
    base = {"event_date": "2026-09-16", "baseline_period": "2026 Q2"}

    assert report_refresh.expected_report_arrived(enrichment, {**base, "form": "8-K"})
    assert report_refresh.expected_report_arrived(enrichment, {**base, "form": "6-K"})
    assert report_refresh.expected_report_arrived(enrichment, {**base, "form": "10-Q/A"})
    assert not report_refresh.expected_report_arrived(enrichment, {**base, "form": "10-Q"})
    assert not report_refresh.expected_report_arrived(enrichment, {**base, "form": "10-K"})


def test_expected_period_remains_required_for_any_filing():
    enrichment = SimpleNamespace(fiscal_period="2026 Q2", metadata={"report_ends": {"DilutedEPS": "2026-06-30"}})
    payload = {"form": "8-K", "event_date": "2026-09-16", "expected_period": "2026-09-30"}

    assert not report_refresh.expected_report_arrived(enrichment, payload)
