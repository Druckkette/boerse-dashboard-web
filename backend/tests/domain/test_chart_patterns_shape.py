"""Independent geometry invariants: wicks, pointed Vs and actual rim prices."""

from dataclasses import replace

import numpy as np
import pytest

from app.domain.chart_patterns import PatternParameters, detect_patterns
from scripts.evaluate_published_chart_examples import bars_for, cases, matching
from tests.domain.test_chart_patterns import series
from tests.helpers.chart_pattern_data import historical_bars, historical_cases


@pytest.mark.parametrize("bottom", [20, 32, 45, 49])
@pytest.mark.parametrize("noise", [0, 0.2, 1])
def test_asymmetric_and_noisy_pointed_vs_are_not_rounded_cups(bottom, noise):
    # Unequal legs and daily noise must not turn the same pointed V into a U.
    for seed in (11, 37, 83):
        v = np.interp(np.arange(1, 66), [0, bottom, 65], [100, 65, 100])
        v += np.random.default_rng(seed).normal(0, noise, len(v))
        bars = series([*np.linspace(60, 100, 60), *v])
        assert not any(p.kind.startswith("cup") for p in detect_patterns("V", bars))


def test_isolated_deep_wick_in_flat_prices_is_not_a_cup():
    bars = series([*np.linspace(60, 100, 60), *np.full(65, 98)])
    bars[90] = replace(bars[90], low=65)
    assert not any(p.kind.startswith("cup") for p in detect_patterns("WICK", bars))


@pytest.mark.parametrize(
    "case",
    [c for c in historical_cases() if c["kind"] == "cup_with_handle"],
    ids=lambda c: c["ticker"],
)
def test_drawn_right_rim_uses_price_observed_on_that_date(case):
    bars = historical_bars(case)
    by_date = {str(b.date): b for b in bars}
    for pattern in detect_patterns(case["ticker"], bars):
        if pattern.kind != "cup_with_handle":
            continue
        rim = pattern.points[2]
        assert rim.value == by_date[rim.date].high
        # A nearby earlier higher peak cannot be removed by starting on a
        # declining candle inside the handle to manufacture a lower pivot.
        i = next(i for i, b in enumerate(bars) if str(b.date) == rim.date)
        assert rim.value == max(b.high for b in bars[max(0, i - 4) : i + 1])


def test_asymmetry_is_adjustable_without_loosening_price_depths():
    source = next(c for c in cases() if c["ticker"] == "ADSK")
    bars = bars_for(source)
    assert matching(source, detect_patterns("ADSK", bars))
    assert not matching(
        source, detect_patterns("ADSK", bars, PatternParameters(cup_max_asymmetry_ratio=1))
    )


@pytest.mark.parametrize("value", [0.9, 5.1, float("nan")])
def test_asymmetry_parameter_rejects_invalid_limits(value):
    with pytest.raises(ValueError):
        PatternParameters(cup_max_asymmetry_ratio=value)
