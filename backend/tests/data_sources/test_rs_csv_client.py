from __future__ import annotations

from datetime import date

import pytest

from app.data_sources.rs_csv_client import parse_external_rs_csv


def test_parse_external_rs_csv_keeps_source_date() -> None:
    rows = parse_external_rs_csv(
        "ticker,rating,score,as_of_date,generated_at_utc,universe,source\n"
        "NVDA,99,12.5,2026-07-30,2026-07-31 04:00:00,us_common_stocks,github_actions_yahoo\n"
    )

    assert rows[0].ticker == "NVDA"
    assert rows[0].rating == 99
    assert rows[0].as_of == date(2026, 7, 30)
    assert rows[0].source == "github_actions_yahoo"


def test_parse_external_rs_csv_rejects_rows_without_as_of() -> None:
    with pytest.raises(RuntimeError, match="as_of_date"):
        parse_external_rs_csv("ticker,rating,score\nNVDA,99,12.5\n")


def test_parse_fred_rs_csv_uses_commit_derived_market_date() -> None:
    rows = parse_external_rs_csv(
        "Rank,Ticker,Relative Strength,Percentile\n1,NVDA,506.39,99\n",
        default_as_of=date(2026, 7, 30),
        default_generated_at="2026-07-31T01:18:54+00:00",
    )

    assert rows[0].ticker == "NVDA"
    assert rows[0].rating == 99
    assert rows[0].score == 506.39
    assert rows[0].as_of == date(2026, 7, 30)
    assert rows[0].source == "github_fred_rs_log"
