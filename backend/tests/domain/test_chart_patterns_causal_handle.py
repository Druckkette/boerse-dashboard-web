"""Recognition keeps its first observation when competing rims dry up differently."""

from datetime import date, timedelta

import numpy as np
import pytest

from app.domain.chart_patterns import Bar, PatternParameters, detect_patterns


def _cup_with_competing_rims() -> list[Bar]:
    x = np.linspace(-1, 1, 66)[1:]
    prices = [
        *np.linspace(60, 100, 60),
        *(70 + 30 * x**2),
        98,
        99,
        100,
        98,
        96,
        94,
        92,
        91,
        93,
        96,
        *([95] * 15),
    ]
    volumes = [1400] * 60 + list(450 + 550 * np.abs(x))
    volumes[-10:] = [400] * 10
    # The first rim's low baseline needs longer to prove dry-up. The second
    # rim includes the high-volume retest and has enough evidence sooner.
    volumes += [800] * 3 + [400] * 7 + [100] * 15
    day = date(2024, 1, 1)
    bars = []
    for price, volume in zip(prices, volumes):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        bars.append(Bar(day, price, price * 1.002, price * 0.998, price, volume))
        day += timedelta(days=1)
    return bars


@pytest.mark.parametrize("require_volume", [False, True])
def test_later_volume_evidence_cannot_replace_first_observable_handle(require_volume):
    bars = _cup_with_competing_rims()
    parameters = PatternParameters(require_volume=require_volume)
    prefix = [b for b in bars if str(b.date) <= "2024-07-05"]
    first = next(
        p for p in detect_patterns("TEST", prefix, parameters) if p.kind == "cup_with_handle"
    )
    assert first.detected_on == "2024-07-05"
    assert first.points[2].date == ("2024-06-26" if require_volume else "2024-06-21")
    same = next(p for p in detect_patterns("TEST", bars, parameters) if p.id == first.id)
    assert same.detected_on == first.detected_on
    assert same.points == first.points
    assert same.pivot == first.pivot
    assert same.volume_ratio == first.volume_ratio
