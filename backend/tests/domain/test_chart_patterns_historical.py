"""Frozen calibration examples establish reproducibility, not population precision."""

import pytest
import json

from app.domain.chart_patterns import detect_patterns
from tests.helpers.chart_pattern_data import FIXTURES, historical_bars, historical_cases


@pytest.mark.parametrize("case", historical_cases(), ids=lambda v: v["file"])
def test_real_historical_examples_and_causal_replay(case):
    bars = historical_bars(case)
    matches = [
        p
        for p in detect_patterns(case["ticker"], bars)
        if p.kind == case["kind"] and case["detected_from"] <= p.detected_on <= case["detected_to"]
    ]
    assert matches, case
    for found in matches:
        assert found.breakout_on is not None
        prefix = [b for b in bars if str(b.date) <= found.detected_on]
        replay = next(p for p in detect_patterns(case["ticker"], prefix) if p.id == found.id)
        assert replay.points == found.points
        assert replay.pivot == found.pivot
        assert replay.detected_on == found.detected_on


@pytest.mark.parametrize(
    "case", json.loads((FIXTURES / "rejections.json").read_text()), ids=lambda v: v["ticker"]
)
def test_invalidated_real_second_trough_is_not_used(case):
    bars = historical_bars(case)
    for pattern in detect_patterns(case["ticker"], bars):
        if pattern.kind != "double_bottom":
            continue
        second = pattern.points[3]
        assert not (
            second.date == case["invalid_second_low"]
            and pattern.detected_on == case["old_detected_on"]
        )
        assert (
            min(b.low for b in bars if second.date <= str(b.date) <= pattern.detected_on)
            >= second.value
        )
