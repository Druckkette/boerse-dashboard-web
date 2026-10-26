"""A later W recovery cannot replace an already observable W at the same rim."""

from datetime import date, timedelta

import numpy as np
import pytest

from app.domain.chart_patterns import Bar, detect_patterns


def _seeded_bars(offset: int) -> list[Bar]:
    # Fixed independent walks also exercise competing trough pairs in one base.
    returns = np.random.default_rng(123).normal(0, 0.018, (offset + 1, 300))[-1]
    prices = 100 * np.exp(np.cumsum(returns))
    day = date(2024, 1, 1)
    bars = []
    for price in prices:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        bars.append(Bar(day, price, price * 1.002, price * 0.998, price, 1000))
        day += timedelta(days=1)
    return bars


def test_later_recovery_does_not_replace_an_earlier_observable_double_bottom():
    bars = _seeded_bars(15)
    found = detect_patterns("TEST", bars)
    earlier = next(
        p
        for p in found
        if p.kind == "double_bottom"
        and p.points[0].date == "2024-07-23"
        and p.detected_on == "2024-10-14"
    )
    prefix = [b for b in bars if str(b.date) <= earlier.detected_on]
    replay = next(p for p in detect_patterns("TEST", prefix) if p.id == earlier.id)
    assert replay.points == earlier.points
    assert replay.pivot == earlier.pivot


@pytest.mark.parametrize("offset", [0, 7, 15, 19])
def test_seeded_double_bottoms_exist_at_their_claimed_detection_date(offset):
    bars = _seeded_bars(offset)
    for pattern in detect_patterns("TEST", bars):
        if pattern.kind != "double_bottom":
            continue
        prefix = [b for b in bars if str(b.date) <= pattern.detected_on]
        replay = next(p for p in detect_patterns("TEST", prefix) if p.id == pattern.id)
        assert replay.points == pattern.points
        assert replay.pivot == pattern.pivot
