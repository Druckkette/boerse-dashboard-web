from __future__ import annotations

import pandas as pd

from app.data_sources.sec13f_client import (
    SymbolRecord,
    aggregate_by_ticker,
    build_cusip_mapping,
    build_outputs,
    sec_headers,
)


def test_sec13f_cusip_mapping_uses_sec_company_names() -> None:
    meta = pd.DataFrame(
        [
            {
                "CUSIP": "67066G104",
                "issuer": "NVIDIA CORP",
                "title": "COM",
            }
        ]
    )

    mapping, unmatched = build_cusip_mapping(
        meta,
        universe={"NVDA"},
        records=[SymbolRecord(ticker="NVDA", name="NVIDIA CORP", exchange="Nasdaq")],
        overrides={},
    )

    assert unmatched.empty
    assert mapping.to_dict(orient="records") == [
        {
            "cusip": "67066G104",
            "ticker": "NVDA",
            "issuer": "NVIDIA CORP",
            "title": "COM",
            "method": "name_unique",
        }
    ]


def test_sec13f_headers_accept_explicit_runtime_user_agent(monkeypatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    headers = sec_headers("boerse-dashboard-web tests@example.com")

    assert headers["User-Agent"] == "boerse-dashboard-web tests@example.com"


def test_sec13f_aggregate_outputs_stable_trend_payload() -> None:
    holdings = pd.DataFrame(
        [
            {
                "period": "2025-12-31",
                "CUSIP": "67066G104",
                "CIK": "0000000001",
                "value_usd": 12_000_000.0,
                "shares": 100_000.0,
                "is_large_holder": True,
            },
            {
                "period": "2025-12-31",
                "CUSIP": "67066G104",
                "CIK": "0000000002",
                "value_usd": 3_000_000.0,
                "shares": 25_000.0,
                "is_large_holder": False,
            },
            {
                "period": "2025-09-30",
                "CUSIP": "67066G104",
                "CIK": "0000000001",
                "value_usd": 10_000_000.0,
                "shares": 90_000.0,
                "is_large_holder": True,
            },
        ]
    )
    mapping = pd.DataFrame([{"cusip": "67066G104", "ticker": "NVDA"}])

    ticker_agg = aggregate_by_ticker(holdings, mapping, large_holder_min_value_usd=10_000_000)
    payload, rows = build_outputs(
        ticker_agg,
        mapping,
        holdings,
        current_period="2025-12-31",
        previous_period="2025-09-30",
        metadata={"source": "test"},
    )

    nvda = payload["tickers"]["NVDA"]
    assert rows[0]["ticker"] == "NVDA"
    assert nvda["holder_count"] == 2
    assert nvda["previous_holder_count"] == 1
    assert nvda["holder_count_delta"] == 1
    assert nvda["large_holder_count"] == 1
    assert nvda["large_holder_delta"] == 0
    assert nvda["total_value_usd"] == 15_000_000.0
    assert nvda["total_value_delta_pct"] == 50.0
    assert nvda["trend"] == "neutral"
