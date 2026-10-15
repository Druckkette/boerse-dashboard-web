from __future__ import annotations

import pandas as pd

from app.data_sources import sec13f_client
from app.data_sources.sec13f_client import (
    DatasetLink,
    SymbolRecord,
    aggregate_by_ticker,
    append_override_meta_rows,
    build_cusip_mapping,
    build_outputs,
    load_default_overrides,
    list_sec_13f_datasets,
    sec_headers,
)
from app.services.sec13f import _resolve_universe, _ticker_breakdown


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


def test_sec13f_dataset_sorting_prefers_current_month_range_files() -> None:
    current = DatasetLink(
        label="2026 March April May 13F",
        url="https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip",
    )
    prior = DatasetLink(
        label="2025 December 2026 January February 13F",
        url="https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01dec2025-28feb2026_form13f.zip",
    )
    old_quarter = DatasetLink(
        label="2023 Q4 13F",
        url="https://www.sec.gov/files/structureddata/data/form-13f-data-sets/2023q4_form13f.zip",
    )

    assert current.sort_key > prior.sort_key > old_quarter.sort_key


def test_sec13f_dataset_listing_sorts_mixed_sec_formats(monkeypatch) -> None:
    html = """
    <a href="/files/structureddata/data/form-13f-data-sets/2023q4_form13f.zip">2023 Q4 13F</a>
    <a href="/files/structureddata/data/form-13f-data-sets/01dec2025-28feb2026_form13f.zip">
      2025 December 2026 January February 13F
    </a>
    <a href="/files/structureddata/data/form-13f-data-sets/2023q3_form13f.zip">2023 Q3 13F</a>
    <a href="/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip">
      2026 March April May 13F
    </a>
    """
    monkeypatch.setattr(sec13f_client, "fetch_text", lambda *args, **kwargs: html)

    links = list_sec_13f_datasets(sec_user_agent="boerse-dashboard-web tests@example.com")

    assert [link.label for link in links] == [
        "2026 March April May 13F",
        "2025 December 2026 January February 13F",
        "2023 Q4 13F",
        "2023 Q3 13F",
    ]


def test_sec13f_default_overrides_include_current_sandisk_cusip() -> None:
    overrides = load_default_overrides({"SNDK"})

    assert overrides["80004C200"] == "SNDK"


def test_sec13f_universe_can_resolve_stored_us_common_stocks(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.sec13f.resolve_universe_tickers",
        lambda **kwargs: ["AAPL", "INTC", "NVDA"][: int(kwargs["limit"])],
    )

    assert _resolve_universe({"universe": "us_common_stocks", "limit_universe": 5000}) == ["AAPL", "INTC", "NVDA"]


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


def test_sec13f_abbreviated_issuer_matches_veeva_without_fuzzy_matching():
    meta = pd.DataFrame([{"CUSIP": "922475108", "issuer": "VEEVA SYS INC CL A COM", "title": "Stock"}])
    mapping, unmatched = build_cusip_mapping(meta, {"VEEV"},
        [SymbolRecord(ticker="VEEV", name="VEEVA SYSTEMS INC")], {})
    assert mapping.iloc[0]["ticker"] == "VEEV"
    assert unmatched.empty


def test_sec13f_abbreviation_collision_is_not_assigned_arbitrarily():
    meta = pd.DataFrame([{"CUSIP": "123456789", "issuer": "EXAMPLE SYS INC", "title": "COM"}])
    mapping, unmatched = build_cusip_mapping(meta, {"ONE", "TWO"},
        [SymbolRecord(ticker="ONE", name="EXAMPLE SYSTEMS INC"),
         SymbolRecord(ticker="TWO", name="EXAMPLE SYS INC")], {})
    assert mapping.empty
    assert unmatched.iloc[0]["reason"] == "ambiguous_name"


def test_sec13f_legal_state_suffix_and_reordered_names():
    meta = pd.DataFrame([
        {"CUSIP": "038222105", "issuer": "APPLIED MATLS INC COM", "title": "Stock"},
        {"CUSIP": "254687106", "issuer": "DISNEY WALT CO COM", "title": "Stock"}])
    records = [SymbolRecord(ticker="AMAT", name="APPLIED MATERIALS INC /DE"),
               SymbolRecord(ticker="DIS", name="Walt Disney Co")]
    mapping, unmatched = build_cusip_mapping(meta, {"AMAT", "DIS"}, records, {})
    assert set(mapping["ticker"]) == {"AMAT", "DIS"}
    assert unmatched.empty


def test_sec13f_unmatched_float_columns_are_strict_json_safe():
    import json
    frame = pd.DataFrame({"current_holder_count": [1., float("nan")]})
    rows = sec13f_client._dataframe_records(frame)
    assert rows[1]["current_holder_count"] is None
    json.dumps(rows, allow_nan=False)


def test_sec13f_duplicate_alias_does_not_create_false_ambiguity():
    meta = pd.DataFrame([{"CUSIP": "922475108", "issuer": "VEEVA SYS INC", "title": "COM"}])
    mapping, unmatched = build_cusip_mapping(meta, {"VEEV"},
        [SymbolRecord(ticker="VEEV", name="VEEVA SYSTEMS INC"),
         SymbolRecord(ticker="VEEV", name="Veeva Systems Inc. Class A Common Stock")], {})
    assert list(mapping["ticker"]) == ["VEEV"]
    assert unmatched.empty


def test_sec13f_main_cusips_with_abbreviated_names_are_not_silently_omitted():
    meta = pd.DataFrame([
        {"CUSIP": "874039100", "issuer": "TAIWAN SEMICONDUCTOR MANUFACT", "title": "SPONSORED ADS"},
        {"CUSIP": "882508104", "issuer": "TEXAS INSTRS INC COM", "title": "Stock"},
        {"CUSIP": "127387108", "issuer": "CADENCE DESIGN SYSTEM INC COM", "title": "Stock"},
        {"CUSIP": "30231G102", "issuer": "EXXON MOBIL CORP COM", "title": "Stock"}])
    records = [SymbolRecord(ticker="TSM", name="TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD"),
               SymbolRecord(ticker="TXN", name="TEXAS INSTRUMENTS INC"),
               SymbolRecord(ticker="CDNS", name="CADENCE DESIGN SYSTEMS INC"),
               SymbolRecord(ticker="XOM", name="ExxonMobil Holdings Corp")]
    mapping, unmatched = build_cusip_mapping(meta, {r.ticker for r in records}, records, {})
    assert set(mapping["cusip"]) == set(meta["CUSIP"])
    assert unmatched.empty


def test_sec13f_established_cusip_repairs_changed_name_but_keeps_current_name_match():
    meta = pd.DataFrame([{"CUSIP": "123456789", "issuer": "OLD ISSUER NAME", "title": "COM"}])
    records = [SymbolRecord(ticker="NEW", name="CURRENT ISSUER NAME")]
    mapping, unmatched = build_cusip_mapping(meta, {"NEW"}, records, {}, known_mappings={"123456789": "NEW"})
    assert mapping.iloc[0]["ticker"] == "NEW"
    assert mapping.iloc[0]["method"] == "known_cusip"
    assert unmatched.empty
    current = pd.DataFrame([{"CUSIP": "123456789", "issuer": "CURRENT ISSUER NAME", "title": "COM"}])
    mapping, _ = build_cusip_mapping(current, {"NEW", "OLD"}, records, {}, known_mappings={"123456789": "OLD"})
    assert mapping.iloc[0]["ticker"] == "NEW"


def test_sec13f_fixed_width_truncation_requires_long_exact_unique_prefix():
    meta = pd.DataFrame([{"CUSIP": "123456789", "issuer": "ARTISAN PARTNERS ASSET MGMT I CL A", "title": "Stock"}])
    record = SymbolRecord(ticker="APAM", name="Artisan Partners Asset Management Inc.")
    mapping, unmatched = build_cusip_mapping(meta, {"APAM"}, [record], {})
    assert mapping.iloc[0]["ticker"] == "APAM"
    assert mapping.iloc[0]["method"] == "issuer_prefix_unique"
    assert unmatched.empty
    other = SymbolRecord(ticker="OTHER", name="Artisan Partners Asset Management International Inc.")
    mapping, unmatched = build_cusip_mapping(meta, {"APAM", "OTHER"}, [record, other], {})
    assert mapping.empty
    assert len(unmatched) == 1


def test_verified_security_ids_handle_registered_share_names_and_abbreviated_issuer():
    meta = pd.DataFrame([
        {"CUSIP": "H5919C104", "issuer": "ON HLDG AG NAMEN AKT A", "title": "Stock"},
        {"CUSIP": "78467J100", "issuer": "SS&C TECH HLDGS COM", "title": "Stock"}])
    universe = {"ONON", "SSNC"}
    mapping, unmatched = build_cusip_mapping(meta, universe,
        [SymbolRecord(ticker="ONON", name="On Holding AG"),
         SymbolRecord(ticker="SSNC", name="SS&C Technologies Holdings Inc.")], load_default_overrides(universe))
    assert set(mapping["ticker"]) == universe
    assert unmatched.empty
