from dataclasses import asdict
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd

from app.domain.stocks import assessment


def test_typed_dates_skip_parser_without_changing_complete_assessment():
    bars = [assessment.StockAssessmentBar(
        date=date(2020, 1, 1) + timedelta(days=i),
        open=100 + i / 10, high=102 + i / 10, low=99 + i / 10,
        close=101 + i / 10, volume=1_000_000 + i * 100,
    ) for i in range(2600)]
    strings = [{**asdict(bar), "date": bar.date.isoformat()} for bar in bars]
    expected = assessment.compute_stock_assessment("TEST", strings)
    with patch.object(pd, "to_datetime", wraps=pd.to_datetime) as parse:
        actual = assessment.compute_stock_assessment("TEST", bars)
    assert actual == expected
    assert parse.call_count == 0


def test_mixed_dates_preserve_invalid_filtering_sorting_and_last_duplicate():
    base = {"open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}
    bars = [{**base, "date": value} for value in [date(2026, 9, 11), "invalid", None, "2026-09-10"]]
    bars.append({**base, "date": pd.Timestamp("2026-09-11 14:30"), "close": 12})
    frame = assessment._coerce_bars_to_frame(bars)
    assert frame.index.tolist() == [pd.Timestamp("2026-09-10"), pd.Timestamp("2026-09-11")]
    assert frame["Close"].tolist() == [11, 12]
