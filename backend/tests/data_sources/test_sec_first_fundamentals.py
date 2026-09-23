from __future__ import annotations

import io
import json
import zipfile
from datetime import date

import pandas as pd
import pytest
import requests

from app.data_sources import fundamentals_client as client
from app.data_sources import sec_companyfacts_cache as cache
from app.data_sources import provider_guard
from app.data_sources import sec_request
from app.services.fundamentals import merge_snapshot_write
from app.repositories.fundamentals import FundamentalSnapshotWrite


def _fact(value, end, *, start=None, form="10-Q", fp="Q1", filed="2026-05-01"):
    row = {"val": value, "end": end, "form": form, "fp": fp, "filed": filed}
    if start:
        row["start"] = start
    return row


def _concept(rows, unit):
    return {"units": {unit: rows}}


def test_us_gaap_quarter_annual_and_amendment_mapping():
    facts = {"us-gaap": {
        "EarningsPerShareDiluted": _concept([
            _fact(1.0, "2026-03-31", start="2026-01-01"),
            _fact(1.2, "2026-03-31", start="2026-01-01", form="10-Q/A", filed="2026-06-01"),
            _fact(4.0, "2025-12-31", start="2025-01-01", form="10-K", fp="FY"),
        ], "USD/shares"),
        "RevenueFromContractWithCustomerExcludingAssessedTax": _concept([
            _fact(100, "2026-03-31", start="2026-01-01"),
            _fact(380, "2025-12-31", start="2025-01-01", form="10-K", fp="FY"),
        ], "USD"),
        "NetIncomeLoss": _concept([
            _fact(20, "2026-03-31", start="2026-01-01"),
            _fact(70, "2025-12-31", start="2025-01-01", form="10-K", fp="FY"),
        ], "USD"),
        "StockholdersEquity": _concept([_fact(300, "2026-03-31")], "USD"),
        "LiabilitiesAndStockholdersEquity": _concept([_fact(999, "2026-03-31")], "USD"),
    }}
    raw = client._raw_from_sec_facts(facts)
    assert raw["DilutedEPS"].iloc[0] == 1.2
    assert raw["AnnualDilutedEPS"].iloc[0] == 4.0
    assert raw["TotalRevenue"].iloc[0] == 100
    assert raw["AnnualTotalRevenue"].iloc[0] == 380
    assert raw["NetIncome"].iloc[0] == 20
    assert raw["AnnualNetIncome"].iloc[0] == 70
    assert raw["StockholdersEquity"].iloc[0] == 300


def test_ifrs_20f_6k_and_currency_mapping():
    facts = {"ifrs-full": {
        "DilutedEarningsLossPerShare": _concept([
            _fact(2.0, "2026-03-31", start="2026-01-01", form="6-K"),
            _fact(6.0, "2025-12-31", start="2025-01-01", form="20-F", fp="FY"),
            _fact(6.5, "2025-12-31", start="2025-01-01", form="20-F/A", fp="FY", filed="2026-07-01"),
        ], "EUR/shares"),
        "Revenue": _concept([
            _fact(250, "2026-03-31", start="2026-01-01", form="6-K"),
            _fact(900, "2025-12-31", start="2025-01-01", form="20-F", fp="FY"),
        ], "EUR"),
        "ProfitLoss": _concept([_fact(30, "2026-03-31", start="2026-01-01", form="6-K")], "EUR"),
        "Equity": _concept([_fact(500, "2025-12-31", form="20-F", fp="FY")], "EUR"),
    }}
    currency = client._sec_statement_currency(facts)
    raw = client._raw_from_sec_facts(facts, currency=currency)
    assert currency == "EUR"
    assert raw["DilutedEPS"].iloc[0] == 2
    assert raw["AnnualDilutedEPS"].iloc[0] == 6.5
    assert raw["TotalRevenue"].iloc[0] == 250
    assert raw["AnnualTotalRevenue"].iloc[0] == 900
    assert raw["NetIncome"].iloc[0] == 30
    assert raw["StockholdersEquity"].iloc[0] == 500
    assert client._raw_from_sec_facts({"custom": facts["ifrs-full"]}) == {}


def _complete_raw():
    ends = pd.date_range("2022-03-31", periods=19, freq="QE-DEC")
    def series(scale):
        return pd.Series({stamp: scale * (index + 1) for index, stamp in enumerate(ends)}).sort_index(ascending=False)
    annual = pd.Series({pd.Timestamp(f"{year}-12-31"): float(year - 2020) for year in range(2022, 2026)}).sort_index(ascending=False)
    return {"DilutedEPS": series(0.2), "TotalRevenue": series(100), "NetIncome": series(10),
            "StockholdersEquity": pd.Series({pd.Timestamp("2026-09-30"): 1000.0,
                                             pd.Timestamp("2025-09-30"): 800.0}),
            "AnnualDilutedEPS": annual, "AnnualTotalRevenue": annual * 100,
            "AnnualNetIncome": annual * 10}


def test_local_growth_roe_margin_and_trailing_eps():
    raw = _complete_raw()
    result = client.compute_fundamental_enrichment("TEST", raw)
    assert result.trailing_eps == round(sum(raw["DilutedEPS"].iloc[:4]), 2)
    assert result.roe_pct == round(sum(raw["NetIncome"].iloc[:4]) / 900 * 100, 1)
    assert result.profit_margin_pct == 10.0
    assert result.quarterly_eps_growth_pct is not None
    assert result.annual_revenue_growth_pct is not None
    assert result.quarterly_eps_accelerating is False
    zero = {**raw, "StockholdersEquity": pd.Series({pd.Timestamp("2026-09-30"): 0.0})}
    assert client.compute_fundamental_enrichment("TEST", zero).roe_pct is None
    missing = {**raw, "TotalRevenue": pd.Series(dtype=float)}
    assert client.compute_fundamental_enrichment("TEST", missing).profit_margin_pct is None
    negative = {**raw, "NetIncome": raw["NetIncome"] * -1}
    assert client.compute_fundamental_enrichment("TEST", negative).profit_margin_pct == -10.0
    gap = {**raw, "DilutedEPS": raw["DilutedEPS"].drop(raw["DilutedEPS"].index[1])}
    assert client.compute_fundamental_enrichment("TEST", gap).trailing_eps is None


@pytest.mark.parametrize(("current", "previous", "flag", "growth"), [
    (2.0, 1.0, None, 100.0),
    (2.0, -1.0, "turnaround", None),
    (-2.0, -1.0, "still_neg", None),
    (-1.0, 2.0, "turned_neg", None),
    (2.0, 0.0, "prev_zero", None),
    (2.0, None, "missing_prior", None),
])
def test_growth_special_cases(current, previous, flag, growth):
    point = client._growth_point("2026 Q1", current, previous)
    assert point.flag == flag
    assert point.growth_pct == growth


def test_quarterly_growth_matches_fiscal_dates_across_calendar_boundary():
    # A restaurant's fiscal Q1 ended April 1 last year and March 31 this year.
    # The December 30/31 entries are duplicate provider dates for one period.
    values = pd.Series({
        pd.Timestamp("2026-06-30"): 0.86,
        pd.Timestamp("2026-03-31"): 0.41,
        pd.Timestamp("2025-12-31"): 0.58,
        pd.Timestamp("2025-12-30"): 0.58,
        pd.Timestamp("2025-07-01"): 0.97,
        pd.Timestamp("2025-04-01"): 0.58,
        pd.Timestamp("2024-12-31"): 0.22,
    })
    points = client.quarterly_yoy_growth({"DilutedEPS": values}, "eps")
    assert len(points) == 3
    assert [point.previous for point in points] == [0.97, 0.58, 0.22]
    assert [point.growth_pct for point in points] == [-11.3, -29.3, 163.6]
    assert client._usable_growth_count(points) == 3


def test_nearby_provider_period_dates_do_not_break_ttm_or_replace_sec():
    sec = pd.Series({pd.Timestamp("2025-12-30"): 0.58})
    yahoo = pd.Series({pd.Timestamp("2025-12-31"): 0.59,
                       pd.Timestamp("2025-09-30"): 0.02})
    merged = client.merge_quarterly_raw({"DilutedEPS": sec}, {"DilutedEPS": yahoo})
    assert len(merged["DilutedEPS"]) == 2
    assert merged["DilutedEPS"].loc[pd.Timestamp("2025-12-30")] == 0.58

    with_old_duplicate = pd.Series({
        pd.Timestamp("2026-06-30"): 0.86,
        pd.Timestamp("2026-03-31"): 0.41,
        pd.Timestamp("2025-12-31"): 0.58,
        pd.Timestamp("2025-12-30"): 0.58,
        pd.Timestamp("2025-09-30"): 0.02,
    })
    assert client._trailing_sum(with_old_duplicate, periods=4) == 1.87


def test_complete_sec_avoids_yahoo_and_fmp(monkeypatch):
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *args, **kwargs: (_complete_raw(), "SEC sec_bulk_cache currency=USD"))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *args: pytest.fail("Yahoo called"))
    monkeypatch.setattr(client, "fetch_quarterly_fmp", lambda *args, **kwargs: pytest.fail("FMP called"))
    monkeypatch.setattr(client, "record_provider_event", lambda *args: None)
    monkeypatch.setattr(client, "bulk_status", lambda: {"fetched_at": pd.Timestamp.now(tz="UTC").isoformat()})
    result = client.fetch_fundamental_enrichment("TEST", sec_user_agent="test contact@example.com", fmp_api_key="key")
    assert result.metadata["fallbacks_used"] == []
    assert result.metadata["data_sources"]["eps"] == "sec_bulk_cache"
    assert result.metadata["fmp_requests_used"] == 0


def test_partial_sec_uses_yahoo_then_fmp_only_if_still_missing(monkeypatch):
    monkeypatch.setattr(client, "record_provider_event", lambda *args: None)
    monkeypatch.setattr(client, "bulk_status", lambda: {"fetched_at": pd.Timestamp.now(tz="UTC").isoformat()})
    partial = {"DilutedEPS": _complete_raw()["DilutedEPS"]}
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *args, **kwargs: (partial, "SEC sec_bulk_cache currency=USD"))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *args: ({**_complete_raw(), "_statement_currency": "USD"}, "yfinance statements"))
    monkeypatch.setattr(client, "fetch_quarterly_fmp", lambda *args, **kwargs: pytest.fail("FMP called"))
    result = client.fetch_fundamental_enrichment("TEST", sec_user_agent="test contact@example.com", fmp_api_key="key")
    assert result.metadata["fallbacks_used"] == ["yfinance"]
    assert result.metadata["data_sources"]["eps"] == "sec_bulk_cache"
    assert result.metadata["data_sources"]["revenue"] == "yfinance"
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *args: (None, "Yahoo leer"))
    calls = []
    monkeypatch.setattr(client, "fetch_quarterly_fmp", lambda *args, **kwargs: (calls.append(1) or {**_complete_raw(), "_statement_currency": "USD"}, "FMP stable"))
    result = client.fetch_fundamental_enrichment("TEST", sec_user_agent="test contact@example.com", fmp_api_key="key")
    assert calls == [1]
    assert result.metadata["fallbacks_used"] == ["yfinance", "fmp"]
    result = client.fetch_fundamental_enrichment("TEST", sec_user_agent="test contact@example.com", fmp_api_key="")
    assert result.metadata["fallbacks_used"] == ["yfinance"]


def test_mismatched_statement_currency_is_not_merged(monkeypatch):
    monkeypatch.setattr(client, "record_provider_event", lambda *args: None)
    monkeypatch.setattr(client, "bulk_status", lambda: {"fetched_at": pd.Timestamp.now(tz="UTC").isoformat()})
    partial = {"DilutedEPS": _complete_raw()["DilutedEPS"]}
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *args, **kwargs: (partial, "SEC sec_bulk_cache currency=USD"))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *args: ({**_complete_raw(), "_statement_currency": "EUR"}, "yfinance statements"))
    result = client.fetch_fundamental_enrichment("TEST", sec_user_agent="agent", fmp_api_key="")
    assert result.metadata["data_sources"]["revenue"] is None
    assert result.metadata["reason_code"] == "waiting_yahoo_data"
    assert "TotalRevenue" not in result.metadata["series_lengths"]


def test_previous_snapshot_keeps_history_on_partial_provider(monkeypatch):
    raw = _complete_raw()
    metadata = client.compute_fundamental_enrichment("TEST", raw).metadata
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *args, **kwargs: pytest.fail("SEC live called"))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *args: pytest.fail("Yahoo called"))
    monkeypatch.setattr(client, "record_provider_event", lambda *args: None)
    result = client.fetch_fundamental_enrichment("TEST", sec_user_agent="agent", previous_metadata={"enrichment": metadata})
    assert result.metadata["series_lengths"]["DilutedEPS"] == len(raw["DilutedEPS"])
    old = FundamentalSnapshotWrite("TEST", date.today(), trailing_eps=7.0,
                                   metadata_json={"eps_quarter_history": [{"fiscal_period": "2025 Q4", "eps_current_quarter": 2.0}]})
    new = FundamentalSnapshotWrite("TEST", date.today(), trailing_eps=None,
                                   metadata_json={"eps_quarter_history": [{"fiscal_period": "2026 Q1", "eps_current_quarter": 3.0}]})
    merged = merge_snapshot_write(old, new)
    assert merged.trailing_eps == 7.0
    assert len(merged.metadata_json["eps_quarter_history"]) == 2


def test_filing_rechecks_bulk_even_with_complete_local_history(monkeypatch):
    raw = _complete_raw()
    metadata = client.compute_fundamental_enrichment("TEST", raw).metadata
    calls = []
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *args, **kwargs: (
        calls.append(kwargs) or raw, "SEC sec_bulk_cache currency=USD"
    ))
    monkeypatch.setattr(client, "fetch_yfinance_statement_history", lambda *args: pytest.fail("Yahoo called"))
    monkeypatch.setattr(client, "record_provider_event", lambda *args: None)
    client.fetch_fundamental_enrichment(
        "TEST", sec_user_agent="agent", previous_metadata={"enrichment": metadata},
        refresh_sec=True,
    )
    assert calls == [{"timeout": 15, "force_live": False}]


def test_fresh_filing_keeps_sec_rate_limit_reason_with_old_complete_data(monkeypatch):
    raw = _complete_raw()
    metadata = client.compute_fundamental_enrichment("TEST", raw).metadata
    monkeypatch.setattr(client, "fetch_quarterly_sec_companyfacts", lambda *args, **kwargs: (
        raw, "SEC sec_bulk_cache_live_rate_limited currency=USD"
    ))
    monkeypatch.setattr(client, "record_provider_event", lambda *args: None)
    result = client.fetch_fundamental_enrichment(
        "TEST", sec_user_agent="agent", previous_metadata={"enrichment": metadata},
        force_live_sec=True, refresh_sec=True,
    )
    assert result.metadata["reason_code"] == "rate_limited"


def _zip_bytes(value=1):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("CIK0000000001.json", json.dumps({"facts": {"value": value}}))
    return output.getvalue()


class _StreamResponse:
    status_code = 200
    def __init__(self, data): self.data = data
    def iter_content(self, chunk_size): yield self.data
    def raise_for_status(self): pass
    def close(self): pass


def test_bulk_cache_atomic_refresh_failure_and_reuse(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(cache, "record_provider_event", lambda *args: None)
    monkeypatch.setattr(cache, "sec_get", lambda *args, **kwargs: _StreamResponse(_zip_bytes(1)))
    first = cache.refresh_companyfacts_bulk_cache("agent", min_members=1)
    assert first["available"] and first["downloaded"]
    loaded, source = cache.load_companyfacts("0000000001", "agent")
    assert loaded["facts"]["value"] == 1 and source == "sec_bulk_cache"
    monkeypatch.setattr(cache, "sec_get", lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("offline")))
    failed = cache.refresh_companyfacts_bulk_cache("agent", max_age_hours=0, min_members=1)
    assert failed["available"] and not failed["downloaded"]
    assert cache.load_companyfacts("0000000001", "agent")[0]["facts"]["value"] == 1
    monkeypatch.setattr(cache, "sec_get", lambda *args, **kwargs: _StreamResponse(_zip_bytes(2)))
    updated = cache.refresh_companyfacts_bulk_cache("agent", max_age_hours=0, min_members=1)
    assert updated["downloaded"]
    assert cache.load_companyfacts("0000000001", "agent")[0]["facts"]["value"] == 2


def test_missing_bulk_cache_uses_live_companyfacts(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(cache, "record_provider_event", lambda *args: None)
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"facts":{"us-gaap":{}}}'
    calls = []
    monkeypatch.setattr(cache, "sec_get", lambda url, **kwargs: (calls.append(url) or response))
    payload, source = cache.load_companyfacts("0000000001", "agent")
    assert payload["facts"] == {"us-gaap": {}}
    assert source == "sec_companyfacts_live"
    assert calls == ["https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"]


def test_fmp_429_cooldown_prevents_followup_requests(monkeypatch):
    class RedisStub:
        remaining = 0
        def ttl(self, key): return self.remaining
        def set(self, key, value, ex): self.remaining = ex
        def close(self): pass
    redis = RedisStub()
    monkeypatch.setattr(provider_guard.Redis, "from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr(provider_guard, "record_provider_event", lambda *args: None)
    calls = []
    def fake_get(*args, **kwargs):
        calls.append(1)
        response = requests.Response()
        response.status_code = 429
        response._content = b"limit"
        return response
    monkeypatch.setattr(provider_guard.requests, "get", fake_get)
    first = provider_guard.guarded_fmp_get("https://example.com/income", params={"apikey": "key"}, timeout=5)
    second = provider_guard.guarded_fmp_get("https://example.com/income", params={"apikey": "key"}, timeout=5)
    assert first.status_code == second.status_code == 429
    assert len(calls) == 1
    assert redis.remaining == 86400


def test_sec_guard_shared_redis_cooldown(monkeypatch):
    class RedisStub:
        cooldown = -2
        counts = 0
        def ttl(self, key): return self.cooldown
        def eval(self, script, count, key):
            self.counts += 1
            return self.counts
        def set(self, key, value, ex): self.cooldown = ex
        def close(self): pass
    redis = RedisStub()
    monkeypatch.setattr(sec_request.Redis, "from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr(sec_request, "record_provider_event", lambda *args: None)
    response = requests.Response()
    response.status_code = 429
    response._content = b"limit"
    response._content_consumed = True
    calls = []
    def requester(*args, **kwargs):
        calls.append(1)
        return response
    with pytest.raises(sec_request.SecRequestError) as first:
        sec_request.sec_get("https://data.sec.gov/test", user_agent="test contact@example.com",
                            requester=requester)
    assert first.value.reason_code == "rate_limited"
    with pytest.raises(sec_request.SecRequestError):
        sec_request.sec_get("https://data.sec.gov/test", user_agent="test contact@example.com",
                            requester=requester)
    assert len(calls) == 1
    assert redis.counts == 1
