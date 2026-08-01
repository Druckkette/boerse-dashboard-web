from __future__ import annotations

import json
from pathlib import Path

from app.data_sources.nasdaq_trader import parse_nasdaq_listed_text, parse_otherlisted_text
from app.repositories import universes as universe_repository
from app.services.universes import get_universe_symbol_mappings, resolve_universe_price_symbols


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "market" / "universe"


def test_parse_nasdaq_listed_filters_non_common_rows() -> None:
    text = "\n".join(
        [
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
            "TQQQ|ProShares UltraPro QQQ|G|N|N|100|Y|N",
            "BADW|Bad Co Warrant|S|N|N|100|N|N",
            "File Creation Time: 06122026|||||||",
        ]
    )

    assert parse_nasdaq_listed_text(text) == ["AAPL"]


def test_parse_otherlisted_filters_etfs_and_normalizes_symbols() -> None:
    text = "\n".join(
        [
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
            "BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK.B",
            "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY",
            "XYZ.W|XYZ Warrants|N|XYZ.W|N|100|N|XYZ.W",
            "File Creation Time: 06122026|||||||",
        ]
    )

    assert parse_otherlisted_text(text) == ["BRK-B"]


def test_universe_mapping_review_counts_manual_overrides(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_repository,
        "list_universe_tickers",
        lambda key, limit: ["AAPL", "BRK-B", "BF-B", "XYZ-W"],
    )
    monkeypatch.setattr(
        universe_repository,
        "list_symbol_mappings",
        lambda key, limit: [
            universe_repository.UniverseSymbolMappingRow(
                universe_key=key,
                source_ticker="BRK-B",
                yahoo_symbol="BRK-B",
                status="active",
                source="manual",
                note="class b",
                confidence=1.0,
                updated_at=None,
            ),
            universe_repository.UniverseSymbolMappingRow(
                universe_key=key,
                source_ticker="XYZ-W",
                yahoo_symbol="",
                status="ignored",
                source="manual",
                note="warrant",
                confidence=1.0,
                updated_at=None,
            ),
        ],
    )

    review = get_universe_symbol_mappings()

    assert review.source == "database"
    assert review.member_count == 4
    assert review.mapped_count == 1
    assert review.ignored_count == 1
    assert review.unmapped_count == 2
    assert review.unmapped_sample == ["AAPL", "BF-B"]


def test_universe_mapping_review_ignores_stale_delisted_and_renamed_overrides(monkeypatch) -> None:
    fixture = json.loads((FIXTURE_DIR / "symbol_edge_cases.json").read_text())

    monkeypatch.setattr(
        universe_repository,
        "list_universe_tickers",
        lambda key, limit: fixture["members"],
    )
    monkeypatch.setattr(
        universe_repository,
        "list_symbol_mappings",
        lambda key, limit: [
            universe_repository.UniverseSymbolMappingRow(
                universe_key=key,
                source_ticker=row["source_ticker"],
                yahoo_symbol=row["yahoo_symbol"],
                status=row["status"],
                source=row["source"],
                note=row["note"],
                confidence=1.0,
                updated_at=None,
            )
            for row in fixture["mappings"]
        ],
    )

    review = get_universe_symbol_mappings()

    assert review.member_count == 5
    assert review.mapped_count == 2
    assert review.ignored_count == 0
    assert review.unmapped_count == 3
    assert [item.source_ticker for item in review.mappings] == ["BRK-B", "BF-B"]
    assert review.unmapped_sample == ["AAPL", "META", "GOOG"]


def test_resolve_universe_price_symbols_uses_yahoo_aliases(monkeypatch) -> None:
    monkeypatch.setattr(
        universe_repository,
        "list_resolved_universe_symbols",
        lambda key, limit: [
            universe_repository.ResolvedUniverseSymbolRow(
                source_ticker="BRK-B",
                yahoo_symbol="BRK-B",
                status="active",
                source="manual",
            ),
            universe_repository.ResolvedUniverseSymbolRow(
                source_ticker="AAPL",
                yahoo_symbol="AAPL",
                status="unmapped",
                source="universe",
            ),
        ],
    )

    resolved = resolve_universe_price_symbols(
        explicit_tickers=None,
        universe_key="us_common_stocks",
        fallback=["SPY"],
        limit=500,
    )

    assert [item.source_ticker for item in resolved] == ["BRK-B", "AAPL"]
    assert [item.yahoo_symbol for item in resolved] == ["BRK-B", "AAPL"]


def test_resolve_universe_price_symbols_prefers_explicit_payload() -> None:
    resolved = resolve_universe_price_symbols(
        explicit_tickers=["MSFT", "NVDA"],
        universe_key="us_common_stocks",
        fallback=["SPY"],
        limit=500,
    )

    assert [item.source_ticker for item in resolved] == ["MSFT", "NVDA"]
    assert all(item.source == "payload" for item in resolved)


def test_resolve_universe_price_symbols_preserves_exchange_suffixes() -> None:
    resolved = resolve_universe_price_symbols(
        explicit_tickers=["2318.HK", "ARKK.L"],
        universe_key=None,
        fallback=[],
        limit=10,
    )

    assert [(item.source_ticker, item.yahoo_symbol) for item in resolved] == [
        ("2318.HK", "2318.HK"),
        ("ARKK.L", "ARKK.L"),
    ]
