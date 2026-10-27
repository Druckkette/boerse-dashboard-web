from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.data_sources import nasdaq_trader
from app.db.models import Instrument, UniverseMember
from app.repositories import universes as universe_repository
from app.services import universes as universe_service


NASDAQ_HEADER = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
OTHER_HEADER = "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"
LISTED_NAMES = {
    "CASH": "Pathward Financial, Inc. - Common Stock",
    "NA": "Nano Labs Ltd - Class A Ordinary Shares",
    "OBAI": "Our Bond, Inc. - Common Stock",
}


def _nasdaq_text(names: dict[str, str]) -> str:
    return "\n".join([
        NASDAQ_HEADER,
        *(f"{symbol}|{name}|Q|N|N|100|N|N" for symbol, name in names.items()),
        "File Creation Time: 10272026|||||||",
    ])


def test_nasdaq_preserves_real_symbols_and_listing_metadata() -> None:
    text = _nasdaq_text(LISTED_NAMES)

    assert nasdaq_trader.parse_nasdaq_listed_text(text) == ["CASH", "NA", "OBAI"]
    details = nasdaq_trader._listing_details(text, "symbol", default_exchange="NASDAQ")
    assert set(details) == set(LISTED_NAMES)
    assert {ticker: row["name"] for ticker, row in details.items()} == LISTED_NAMES
    assert all(row["instrument_type"] == "operating_company" for row in details.values())


def test_otherlisted_preserves_symbols_and_falls_back_from_empty_cqs() -> None:
    text = "\n".join([
        OTHER_HEADER,
        "CASH|Pathward Financial, Inc. Common Stock|N|CASH|N|100|N|CASH",
        "NA|Nano Labs Ltd Class A Ordinary Shares|N||N|100|N|NA",
        "BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK.B",
        "File Creation Time: 10272026|||||||",
    ])

    assert nasdaq_trader.parse_otherlisted_text(text) == ["CASH", "NA", "BRK-B"]
    assert set(nasdaq_trader._listing_details(text, "cqs symbol", "nasdaq symbol", "act symbol")) == {
        "CASH", "NA", "BRK-B",
    }


def test_manual_ticker_normalization_keeps_cash_and_missing_value_guards() -> None:
    assert nasdaq_trader.normalize_tickers(["CASH", "cash", "USD", "NULL", "NAN", "", "NA", "BRK.B"]) == [
        "NA", "BRK-B",
    ]


@pytest.mark.parametrize("name", [
    "Example Corporation - 6.5% Bonds due 2030",
    "Example Corporation 6.5% Bonds due 2030",
    "Example Corporation - Common Stock and Bonds",
    "Example Bond Fund, Inc. - Common Stock",
    "Example Corporation - Senior Notes due 2030",
    "Example Corporation - Debentures due 2030",
    "Example Corporation - Preferred Stock",
    "Example Corporation - Warrants",
    "Example Corporation - Rights",
    "Example Acquisition Corporation - Units",
    "Example Corporation - American Depositary Shares",
])
def test_real_debt_and_existing_noncommon_policies_remain_excluded(name: str) -> None:
    assert nasdaq_trader.parse_nasdaq_listed_text(_nasdaq_text({"EXAMPLE": name})) == []


@pytest.mark.parametrize("flags", ["Q|Y|N|100|N|N", "Q|N|N|100|Y|N", "Q|N|N|100|N|Y"])
def test_listed_cash_still_respects_test_issue_etf_and_nextshares(flags: str) -> None:
    text = f"{NASDAQ_HEADER}\nCASH|{LISTED_NAMES['CASH']}|{flags}"
    assert nasdaq_trader.parse_nasdaq_listed_text(text) == []


def test_cash_reaches_universe_membership_without_second_reserved_word_filter(monkeypatch) -> None:
    # Exercise the real fetch, service, and repository normalization against an
    # isolated in-memory session double; neither HTTP nor a database is used.
    names = {**LISTED_NAMES, **{f"ZZZ{i}": f"Example {i} Inc. - Common Stock" for i in range(500)}}
    nasdaq_text = _nasdaq_text(names)
    other_text = f"{OTHER_HEADER}\nBRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK.B"

    def fake_get(url: str, **kwargs):
        assert url in nasdaq_trader.NASDAQ_LISTED_URLS + nasdaq_trader.OTHER_LISTED_URLS
        text = nasdaq_text if url in nasdaq_trader.NASDAQ_LISTED_URLS else other_text
        return SimpleNamespace(text=text, raise_for_status=lambda: None)

    class Session:
        def __init__(self):
            self.added = []
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def scalars(self, statement):
            return SimpleNamespace(first=lambda: None, all=lambda: [])

        def add(self, row):
            self.added.append(row)

        def flush(self):
            pass

        def commit(self):
            self.committed = True

    session = Session()
    monkeypatch.setattr(nasdaq_trader.requests, "get", fake_get)
    monkeypatch.setattr(universe_repository, "SessionLocal", lambda: session)
    monkeypatch.setattr(universe_repository, "get_universe_status", lambda key: None)

    result = universe_service.refresh_us_common_stock_universe()

    instruments = {row.ticker: row for row in session.added if isinstance(row, Instrument)}
    members = {row.ticker for row in session.added if isinstance(row, UniverseMember)}
    assert set(LISTED_NAMES) <= members
    assert instruments["CASH"].name == LISTED_NAMES["CASH"]
    assert instruments["CASH"].metadata_json["nasdaq_listing"]["classification_source"] == "nasdaq_trader"
    assert result["member_count"] == 504
    assert session.committed is True
