from __future__ import annotations

from datetime import date

import pandas as pd

from app.data_sources.fundamentals_client import (
    FundamentalEnrichment,
    compute_fundamental_enrichment,
    fetch_fmp_next_earnings_date,
    fetch_fmp_profile,
    fetch_quarterly_fmp,
)
from app.data_sources.fmp_client import (
    FMP_BALANCE_SHEET_URL,
    FMP_EARNINGS_URL,
    FMP_INCOME_STATEMENT_URL,
    FMP_PROFILE_URL,
    FMP_RATIOS_TTM_URL,
)
from app.data_sources.yfinance_client import FetchedFundamentals
from app.repositories.fundamentals import FundamentalSnapshotRow
from app.services import fundamentals as fundamentals_service


def test_compute_fundamental_enrichment_detects_growth_and_acceleration() -> None:
    raw = {
        "DilutedEPS": pd.Series(
            {
                pd.Timestamp("2026-03-31"): 2.40,
                pd.Timestamp("2025-12-31"): 2.10,
                pd.Timestamp("2025-09-30"): 1.90,
                pd.Timestamp("2025-06-30"): 1.70,
                pd.Timestamp("2025-03-31"): 1.50,
                pd.Timestamp("2024-12-31"): 1.40,
                pd.Timestamp("2024-09-30"): 1.45,
                pd.Timestamp("2024-06-30"): 1.35,
                pd.Timestamp("2024-03-31"): 1.00,
                pd.Timestamp("2023-12-31"): 0.90,
                pd.Timestamp("2023-09-30"): 0.85,
                pd.Timestamp("2023-06-30"): 0.82,
                pd.Timestamp("2023-03-31"): 0.80,
                pd.Timestamp("2022-12-31"): 0.70,
                pd.Timestamp("2022-09-30"): 0.65,
                pd.Timestamp("2022-06-30"): 0.60,
                pd.Timestamp("2022-03-31"): 0.55,
            }
        ),
        "TotalRevenue": pd.Series(
            {
                pd.Timestamp("2026-03-31"): 240.0,
                pd.Timestamp("2025-12-31"): 225.0,
                pd.Timestamp("2025-09-30"): 210.0,
                pd.Timestamp("2025-06-30"): 205.0,
                pd.Timestamp("2025-03-31"): 200.0,
                pd.Timestamp("2024-12-31"): 190.0,
                pd.Timestamp("2024-09-30"): 185.0,
                pd.Timestamp("2024-06-30"): 150.0,
                pd.Timestamp("2024-03-31"): 145.0,
                pd.Timestamp("2023-12-31"): 140.0,
                pd.Timestamp("2023-09-30"): 135.0,
                pd.Timestamp("2023-06-30"): 135.0,
                pd.Timestamp("2023-03-31"): 130.0,
                pd.Timestamp("2022-12-31"): 110.0,
                pd.Timestamp("2022-09-30"): 110.0,
                pd.Timestamp("2022-06-30"): 105.0,
                pd.Timestamp("2022-03-31"): 105.0,
            }
        ),
        "NetIncome": pd.Series(
            {
                pd.Timestamp("2026-03-31"): 48.0,
                pd.Timestamp("2025-12-31"): 44.0,
                pd.Timestamp("2025-09-30"): 40.0,
                pd.Timestamp("2025-06-30"): 38.0,
            }
        ),
        "StockholdersEquity": pd.Series({pd.Timestamp("2026-03-31"): 320.0}),
    }

    enrichment = compute_fundamental_enrichment("LEAD", raw, notes=["FMP stable", "SEC ergaenzt"])

    assert enrichment.source == "fmp+sec"
    assert enrichment.fiscal_period == "2026 Q1"
    assert enrichment.quarterly_eps_growth_pct == 60.0
    assert enrichment.quarterly_eps_accelerating is True
    assert [item["fiscal_period"] for item in enrichment.eps_quarter_history] == ["2026 Q1", "2025 Q4", "2025 Q3"]
    assert [item["eps_growth_yoy_pct"] for item in enrichment.eps_quarter_history] == [60.0, 50.0, 31.0]
    assert enrichment.annual_eps_growth_pct == 38.5
    assert [item["fiscal_year"] for item in enrichment.annual_eps_history] == ["2025", "2024", "2023"]
    assert [item["eps_growth_yoy_pct"] for item in enrichment.annual_eps_history] == [38.5, 54.3, 34.8]
    assert enrichment.quarterly_revenue_growth_pct == 20.0
    assert enrichment.quarterly_revenue_accelerating is True
    assert [item["fiscal_period"] for item in enrichment.revenue_quarter_history] == ["2026 Q1", "2025 Q4", "2025 Q3"]
    assert [item["revenue_growth_yoy_pct"] for item in enrichment.revenue_quarter_history] == [20.0, 18.4, 13.5]
    assert enrichment.annual_revenue_growth_pct == 25.4
    assert [item["fiscal_year"] for item in enrichment.annual_revenue_history] == ["2025", "2024", "2023"]
    assert [item["revenue_growth_yoy_pct"] for item in enrichment.annual_revenue_history] == [25.4, 24.1, 25.6]
    assert enrichment.trailing_eps == 8.1
    assert enrichment.profit_margin_pct == 19.3
    assert enrichment.roe_pct == 53.1
    assert enrichment.metadata["series_lengths"]["DilutedEPS"] == 17


def test_fetch_quarterly_fmp_uses_stable_endpoints(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload
            self.text = "[]"

        def json(self):
            return self._payload

    def fake_get(url, *, params, timeout):
        calls.append({"url": url, "params": params, "timeout": timeout})
        if url == FMP_INCOME_STATEMENT_URL and params.get("period") == "quarter":
            return FakeResponse(
                [
                    {
                        "date": "2026-03-31",
                        "epsDiluted": 2.4,
                        "revenue": 240.0,
                        "netIncome": 48.0,
                    }
                ]
            )
        if url == FMP_INCOME_STATEMENT_URL and params.get("period") == "annual":
            return FakeResponse(
                [
                    {"date": "2025-12-31", "epsDiluted": 7.2, "revenue": 1350.0, "netIncome": 255.0},
                    {"date": "2024-12-31", "epsDiluted": 5.0, "revenue": 1000.0, "netIncome": 160.0},
                ]
            )
        if url == FMP_BALANCE_SHEET_URL:
            return FakeResponse(
                [
                    {"date": "2025-12-31", "totalStockholdersEquity": 900.0},
                    {"date": "2024-12-31", "totalStockholdersEquity": 700.0},
                ]
            )
        return FakeResponse([{"returnOnEquityTTM": 0.34, "netProfitMarginTTM": 0.18}])

    import app.data_sources.fundamentals_client as fundamentals_client

    monkeypatch.setattr(fundamentals_client.requests, "get", fake_get)

    raw, note = fetch_quarterly_fmp("aapl", "test-key")

    assert raw is not None
    assert note == "FMP stable"
    assert [call["url"] for call in calls] == [
        FMP_INCOME_STATEMENT_URL,
        FMP_INCOME_STATEMENT_URL,
        FMP_BALANCE_SHEET_URL,
        FMP_RATIOS_TTM_URL,
    ]
    assert calls[0]["params"] == {"symbol": "AAPL", "period": "quarter", "limit": 40, "apikey": "test-key"}
    assert calls[1]["params"] == {"symbol": "AAPL", "period": "annual", "limit": 8, "apikey": "test-key"}
    assert calls[2]["params"] == {"symbol": "AAPL", "period": "annual", "limit": 8, "apikey": "test-key"}
    assert calls[3]["params"] == {"symbol": "AAPL", "apikey": "test-key"}
    assert "AnnualDilutedEPS" in raw
    assert "AnnualStockholdersEquity" in raw


def test_fetch_quarterly_fmp_returns_response_body_on_403(monkeypatch) -> None:
    class FakeResponse:
        status_code = 403
        text = "Legacy Endpoint"

        def json(self):
            return {"error": "Legacy Endpoint"}

    import app.data_sources.fundamentals_client as fundamentals_client

    monkeypatch.setattr(fundamentals_client.requests, "get", lambda *args, **kwargs: FakeResponse())

    raw, note = fetch_quarterly_fmp("aapl", "test-key")

    assert raw is None
    assert "Zugriff verweigert" in note
    assert "Legacy Endpoint" in note


def test_fetch_fmp_profile_uses_stable_profile_endpoint(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = "[]"

        def json(self):
            return [{"symbol": "SNDK", "companyName": "SanDisk Corporation", "beta": 1.42}]

    import app.data_sources.fundamentals_client as fundamentals_client

    def fake_get(url, *, params, timeout):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(fundamentals_client.requests, "get", fake_get)

    profile, note = fetch_fmp_profile("sndk", "test-key")

    assert note == "FMP Profile"
    assert profile["beta"] == 1.42
    assert calls == [{"url": FMP_PROFILE_URL, "params": {"symbol": "SNDK", "apikey": "test-key"}, "timeout": 10}]


def test_fetch_fmp_next_earnings_date_uses_stable_earnings_endpoint(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = "[]"

        def json(self):
            return [{"symbol": "SNDK", "date": "2099-08-05"}]

    import app.data_sources.fundamentals_client as fundamentals_client

    def fake_get(url, *, params, timeout):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(fundamentals_client.requests, "get", fake_get)

    earnings_date, note = fetch_fmp_next_earnings_date("sndk", "test-key")

    assert note == "FMP Earnings"
    assert earnings_date == date(2099, 8, 5)
    assert calls == [{"url": FMP_EARNINGS_URL, "params": {"symbol": "SNDK", "apikey": "test-key"}, "timeout": 10}]


def test_refresh_fundamentals_prefers_enriched_quarterly_values(monkeypatch) -> None:
    fetched = FetchedFundamentals(
        ticker="NVDA",
        as_of=date(2026, 6, 12),
        source="yfinance",
        fiscal_period="",
        quarterly_eps_growth_pct=12.0,
        annual_eps_growth_pct=25.0,
        quarterly_revenue_growth_pct=8.0,
        annual_revenue_growth_pct=20.0,
        roe_pct=30.0,
        profit_margin_pct=15.0,
        trailing_eps=1.2,
        institutional_holders=None,
        institutional_ownership_pct=None,
        next_earnings_date=None,
        beta=None,
    )
    enrichment = FundamentalEnrichment(
        source="fmp+sec",
        fiscal_period="2026 Q1",
        quarterly_eps_growth_pct=60.0,
        annual_eps_growth_pct=44.0,
        quarterly_revenue_growth_pct=42.0,
        annual_revenue_growth_pct=35.0,
        quarterly_eps_accelerating=True,
        quarterly_revenue_accelerating=True,
        trailing_eps=8.1,
        roe_pct=53.1,
        profit_margin_pct=18.2,
        eps_quarter_history=[
            {
                "fiscal_period": "2026 Q1",
                "eps_current_quarter": 2.4,
                "eps_same_quarter_last_year": 1.5,
                "eps_growth_yoy_pct": 60.0,
            }
        ],
        annual_eps_history=[
            {
                "fiscal_year": "2025",
                "eps_current_year": 7.2,
                "eps_previous_year": 5.0,
                "eps_growth_yoy_pct": 44.0,
            }
        ],
        revenue_quarter_history=[
            {
                "fiscal_period": "2026 Q1",
                "revenue_current_quarter": 142.0,
                "revenue_same_quarter_last_year": 100.0,
                "revenue_growth_yoy_pct": 42.0,
            }
        ],
        annual_revenue_history=[
            {
                "fiscal_year": "2025",
                "revenue_current_year": 1350.0,
                "revenue_previous_year": 1000.0,
                "revenue_growth_yoy_pct": 35.0,
            }
        ],
        roe_history=[
            {
                "fiscal_year": "2025",
                "roe_pct": 28.3,
                "net_income": 255.0,
                "shareholders_equity": 900.0,
            }
        ],
        beta=1.42,
        next_earnings_date=date(2026, 8, 5),
        metadata={"notes": ["FMP stable"]},
    )

    monkeypatch.setattr(fundamentals_service, "fetch_fundamentals", lambda ticker, include_holders: fetched)
    monkeypatch.setattr(
        fundamentals_service,
        "fetch_fundamental_enrichment",
        lambda ticker, fmp_api_key, sec_user_agent: enrichment,
    )

    def fake_upsert(payload):
        assert payload.source == "yfinance+fmp+sec"
        assert payload.fiscal_period == "2026 Q1"
        assert payload.quarterly_eps_growth_pct == 60.0
        assert payload.annual_eps_growth_pct == 44.0
        assert payload.quarterly_revenue_growth_pct == 42.0
        assert payload.annual_revenue_growth_pct == 35.0
        assert payload.quarterly_eps_accelerating is True
        assert payload.quarterly_revenue_accelerating is True
        assert payload.trailing_eps == 8.1
        assert payload.roe_pct == 53.1
        assert payload.profit_margin_pct == 18.2
        assert payload.beta == 1.42
        assert payload.next_earnings_date == date(2026, 8, 5)
        assert payload.metadata_json["eps_quarter_history"][0]["eps_growth_yoy_pct"] == 60.0
        assert payload.metadata_json["annual_eps_history"][0]["eps_growth_yoy_pct"] == 44.0
        assert payload.metadata_json["revenue_quarter_history"][0]["revenue_growth_yoy_pct"] == 42.0
        assert payload.metadata_json["annual_revenue_history"][0]["revenue_growth_yoy_pct"] == 35.0
        assert payload.metadata_json["roe_history"][0]["roe_pct"] == 28.3
        return FundamentalSnapshotRow(
            ticker="NVDA",
            as_of=payload.as_of,
            source=payload.source,
            fiscal_period=payload.fiscal_period,
            quarterly_eps_growth_pct=payload.quarterly_eps_growth_pct,
            annual_eps_growth_pct=payload.annual_eps_growth_pct,
            quarterly_revenue_growth_pct=payload.quarterly_revenue_growth_pct,
            annual_revenue_growth_pct=payload.annual_revenue_growth_pct,
            roe_pct=payload.roe_pct,
            profit_margin_pct=payload.profit_margin_pct,
            trailing_eps=payload.trailing_eps,
            quarterly_eps_accelerating=payload.quarterly_eps_accelerating,
            quarterly_revenue_accelerating=payload.quarterly_revenue_accelerating,
            institutional_holders=None,
            institutional_ownership_pct=None,
            next_earnings_date=payload.next_earnings_date,
            beta=payload.beta,
            metadata_json=payload.metadata_json or {},
        )

    monkeypatch.setattr(fundamentals_service, "upsert_fundamentals", fake_upsert)

    result = fundamentals_service.refresh_fundamentals_for_ticker("NVDA")

    assert result["source"] == "yfinance+fmp+sec"
    assert result["quarterly_eps_growth_pct"] == 60.0
    assert result["quarterly_revenue_growth_pct"] == 42.0
    assert result["annual_revenue_growth_pct"] == 35.0
    assert result["quarterly_eps_accelerating"] is True
    assert result["beta"] == 1.42
    assert result["next_earnings_date"] == "2026-08-05"
    assert result["enrichment_source"] == "fmp+sec"
