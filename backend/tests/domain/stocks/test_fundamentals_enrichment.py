from __future__ import annotations

from datetime import date

import pandas as pd

from app.data_sources.fundamentals_client import (
    FundamentalEnrichment,
    compute_fundamental_enrichment,
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
                pd.Timestamp("2024-03-31"): 1.00,
                pd.Timestamp("2023-03-31"): 0.80,
            }
        ),
        "TotalRevenue": pd.Series(
            {
                pd.Timestamp("2026-03-31"): 240.0,
                pd.Timestamp("2025-12-31"): 225.0,
                pd.Timestamp("2025-09-30"): 210.0,
                pd.Timestamp("2025-06-30"): 205.0,
                pd.Timestamp("2025-03-31"): 200.0,
                pd.Timestamp("2024-03-31"): 190.0,
                pd.Timestamp("2023-03-31"): 185.0,
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
    assert enrichment.quarterly_revenue_growth_pct == 20.0
    assert enrichment.quarterly_revenue_accelerating is True
    assert enrichment.trailing_eps == 8.1
    assert enrichment.profit_margin_pct == 19.3
    assert enrichment.roe_pct == 53.1
    assert enrichment.metadata["series_lengths"]["DilutedEPS"] == 7


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
        institutional_holders=120,
        institutional_ownership_pct=62.0,
        next_earnings_date=None,
        beta=1.3,
    )
    enrichment = FundamentalEnrichment(
        source="fmp+sec",
        fiscal_period="2026 Q1",
        quarterly_eps_growth_pct=60.0,
        quarterly_revenue_growth_pct=42.0,
        quarterly_eps_accelerating=True,
        quarterly_revenue_accelerating=True,
        trailing_eps=8.1,
        roe_pct=53.1,
        profit_margin_pct=18.2,
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
        assert payload.quarterly_revenue_growth_pct == 42.0
        assert payload.quarterly_eps_accelerating is True
        assert payload.quarterly_revenue_accelerating is True
        assert payload.trailing_eps == 8.1
        assert payload.roe_pct == 53.1
        assert payload.profit_margin_pct == 18.2
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
            institutional_holders=payload.institutional_holders,
            institutional_ownership_pct=payload.institutional_ownership_pct,
            next_earnings_date=payload.next_earnings_date,
            beta=payload.beta,
            metadata_json=payload.metadata_json or {},
        )

    monkeypatch.setattr(fundamentals_service, "upsert_fundamentals", fake_upsert)

    result = fundamentals_service.refresh_fundamentals_for_ticker("NVDA")

    assert result["source"] == "yfinance+fmp+sec"
    assert result["quarterly_eps_growth_pct"] == 60.0
    assert result["quarterly_revenue_growth_pct"] == 42.0
    assert result["quarterly_eps_accelerating"] is True
    assert result["enrichment_source"] == "fmp+sec"
