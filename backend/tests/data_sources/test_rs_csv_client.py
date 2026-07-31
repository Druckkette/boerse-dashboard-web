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
