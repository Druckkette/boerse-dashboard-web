from __future__ import annotations

from app.data_sources.nasdaq_trader import parse_nasdaq_listed_text, parse_otherlisted_text


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
