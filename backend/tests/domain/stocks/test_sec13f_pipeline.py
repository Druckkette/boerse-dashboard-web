from __future__ import annotations

import pandas as pd

from app.data_sources.sec13f_client import (
    SymbolRecord,
    aggregate_by_ticker,
    append_override_meta_rows,
    build_cusip_mapping,
    build_outputs,
    load_default_overrides,
    sec_headers,
)
from app.services.sec13f import _ticker_breakdown


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


def test_sec13f_default_overrides_include_current_sandisk_cusip() -> None:
    overrides = load_default_overrides({"SNDK"})

    assert overrides["80004C200"] == "SNDK"


def test_sec13f_override_meta_rows_allow_mapping_when_sec_meta_is_missing() -> None:
    holdings = pd.DataFrame(
        [
            {
                "period": "2025-12-31",
                "CUSIP": "80004C200",
                "CIK": "0000000001",
                "value_usd": 15_000_000.0,
                "shares": 250_000.0,
                "is_large_holder": True,
            },
            {
                "period": "2025-09-30",
                "CUSIP": "80004C200",
                "CIK": "0000000001",
                "value_usd": 10_000_000.0,
                "shares": 200_000.0,
                "is_large_holder": True,
            },
        ]
    )
    overrides = load_default_overrides({"SNDK"})
    meta = append_override_meta_rows(
        pd.DataFrame(columns=["CUSIP", "issuer", "title"]),
        holdings,
        overrides,
        {"SNDK"},
    )

    mapping, unmatched = build_cusip_mapping(meta, {"SNDK"}, records=[], overrides=overrides)
    ticker_agg = aggregate_by_ticker(holdings, mapping, large_holder_min_value_usd=10_000_000)
    payload, _ = build_outputs(
        ticker_agg,
        mapping,
        holdings,
        current_period="2025-12-31",
        previous_period="2025-09-30",
        metadata={"source": "test"},
    )

    assert unmatched.empty
    assert mapping.to_dict(orient="records") == [
        {
            "cusip": "80004C200",
            "ticker": "SNDK",
            "issuer": "SNDK",
            "title": "COM",
            "method": "override",
        }
    ]
    assert payload["tickers"]["SNDK"]["holder_count"] == 1
    assert payload["tickers"]["SNDK"]["cusip"] == "80004C200"


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


def test_sec13f_aggregate_counts_manager_once_across_multiple_cusips() -> None:
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
                "CUSIP": "67066G203",
                "CIK": "0000000001",
                "value_usd": 2_000_000.0,
                "shares": 10_000.0,
                "is_large_holder": False,
            },
            {
                "period": "2025-12-31",
                "CUSIP": "67066G104",
                "CIK": "0000000002",
                "value_usd": 9_000_000.0,
                "shares": 80_000.0,
                "is_large_holder": False,
            },
            {
                "period": "2025-09-30",
                "CUSIP": "67066G104",
                "CIK": "0000000001",
                "value_usd": 8_000_000.0,
                "shares": 70_000.0,
                "is_large_holder": False,
            },
        ]
    )
    mapping = pd.DataFrame(
        [
            {"cusip": "67066G104", "ticker": "NVDA"},
            {"cusip": "67066G203", "ticker": "NVDA"},
        ]
    )

    ticker_agg = aggregate_by_ticker(holdings, mapping, large_holder_min_value_usd=10_000_000)
    current = ticker_agg[(ticker_agg["period"] == "2025-12-31") & (ticker_agg["ticker"] == "NVDA")].iloc[0]

    assert int(current["holder_count"]) == 2
    assert int(current["large_holder_count"]) == 1
    assert float(current["total_value_usd"]) == 23_000_000.0


def test_sec13f_ticker_breakdown_explains_matched_and_unmapped_tickers() -> None:
    payload = {
        "metadata": {"current_period": "2025-12-31", "previous_period": "2025-09-30"},
        "tickers": {
            "NVDA": {
                "period": "2025-12-31",
                "previous_period": "2025-09-30",
                "cusip": "67066G104",
                "holder_count": 2,
                "previous_holder_count": 1,
                "holder_count_delta": 1,
                "large_holder_count": 1,
                "previous_large_holder_count": 1,
                "large_holder_delta": 0,
                "total_value_usd": 15_000_000.0,
                "total_shares": 125_000.0,
            }
        },
    }

    breakdown = _ticker_breakdown(
        universe=["NVDA", "SNDK"],
        payload=payload,
        mapping_rows=[{"cusip": "67066G104", "ticker": "NVDA"}],
        unmatched_rows=[
            {
                "cusip": "80004C101",
                "issuer": "SANDISK CORP",
                "title": "COM",
                "reason": "no_name_match",
                "candidate_tickers": "",
            }
        ],
        known_overrides={},
    )

    assert breakdown[0]["ticker"] == "NVDA"
    assert breakdown[0]["status"] == "matched"
    assert breakdown[0]["holder_count_delta"] == 1
    assert breakdown[1]["ticker"] == "SNDK"
    assert breakdown[1]["status"] == "no_cusip_mapping"


def test_sec13f_ticker_breakdown_reports_known_cusip_missing_from_loaded_dataset() -> None:
    breakdown = _ticker_breakdown(
        universe=["SNDK"],
        payload={"metadata": {"current_period": "2025-12-31", "previous_period": "2025-09-30"}, "tickers": {}},
        mapping_rows=[],
        unmatched_rows=[],
        known_overrides=load_default_overrides({"SNDK"}),
    )

    assert breakdown == [
        {
            "ticker": "SNDK",
            "status": "known_cusip_not_in_dataset",
            "report_period": "2025-12-31",
            "previous_period": "2025-09-30",
            "cusip": "80004C200",
            "reason": "Bekannte CUSIP(s) waren im geladenen 13F-Holdingsatz nicht enthalten.",
        }
    ]
