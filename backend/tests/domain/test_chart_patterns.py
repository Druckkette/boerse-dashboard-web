"""Independent labelled shapes, adversarial shapes, and causal replay checks."""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from app.domain.chart_patterns import Bar, PatternParameters, detect_patterns, validate_bars


def series(prices, volumes=None):
    result = []
    day = date(2024, 1, 1)
    for i, price in enumerate(prices):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        result.append(
            Bar(
                day,
                float(price),
                float(price) * 1.002,
                float(price) * 0.998,
                float(price),
                float(volumes[i]) if volumes is not None else 1000,
            )
        )
        day += timedelta(days=1)
    return result


def fixture(kind="cup_with_handle", *, depth=30, missing_volume=False):
    prior = list(np.linspace(60, 100, 60))  # ends Friday, then first red week
    if kind.startswith("cup"):
        x = np.linspace(-1, 1, 66)[1:]
        cup = list(100 - depth + depth * x * x)
        vol = list(450 + 550 * np.abs(x))
        after = [98, 96, 94, 92, 91, 92, 94, 96, 97] if kind == "cup_with_handle" else []
        prices = prior + cup + after
        volumes = [1400] * 60 + vol + [400] * len(after)
    elif kind == "double_bottom":
        prices = prior + list(
            np.interp(np.arange(1, 62), [0, 15, 30, 45, 61], [100, 75, 93, 70, 92])
        )
        volumes = [1400] * 60 + [
            550 if 10 <= i <= 20 or 40 <= i <= 50 else 900 for i in range(1, 62)
        ]
    elif kind == "high_tight_flag":
        prices = (
            list(np.linspace(30, 50, 40))
            + list(np.linspace(51, 100, 40))
            + [
                94,
                92,
                90,
                89,
                91,
                93,
                95,
                96,
                94,
                92,
                90,
                91,
                93,
                94,
                95,
                93,
                91,
                92,
                94,
                95,
                96,
                95,
                94,
                95,
                96,
            ]
        )
        volumes = [1400] * 80 + [400] * 25
    else:
        prices = prior + list(97 + 2 * np.cos(np.arange(1, 27) * np.pi / 5))
        volumes = [1400] * 60 + list(np.linspace(900, 400, 26))
    bars = series(prices, volumes)
    if missing_volume:
        bars = [replace(b, volume=None) for b in bars]
    return bars


@pytest.mark.parametrize(
    "kind", ["cup_with_handle", "cup_without_handle", "double_bottom", "high_tight_flag", "box"]
)
def test_five_labelled_patterns(kind):
    found = detect_patterns("TEST", fixture(kind))
    assert kind in [p.kind for p in found], [(p.kind, p.detected_on) for p in found]
    p = next(p for p in found if p.kind == kind)
    assert p.start_date > p.points[0].date or kind == "high_tight_flag"
    assert p.detected_on >= p.end_date
    assert p.pivot == pytest.approx(100.2 if kind != "double_bottom" else 93 * 1.002)


def test_v_recovery_is_not_a_cup():
    bars = series(
        list(np.linspace(60, 100, 60))
        + list(np.interp(np.arange(1, 66), [0, 32, 65], [100, 65, 100])),
        [1400] * 60 + [500] * 65,
    )
    assert not any(p.kind.startswith("cup") for p in detect_patterns("TEST", bars))


def test_cup_maximum_depth_changes_recognition():
    bars = fixture("cup_without_handle", depth=44)
    assert any(p.kind == "cup_without_handle" for p in detect_patterns("TEST", bars))
    assert not any(
        p.kind.startswith("cup")
        for p in detect_patterns("TEST", bars, PatternParameters(cup_max_depth_pct=40))
    )


def test_strict_volume_mode_excludes_missing_volume():
    bars = fixture("cup_with_handle", missing_volume=True)
    assert detect_patterns("TEST", bars, PatternParameters(require_volume=True)) == []
    found = detect_patterns("TEST", bars)
    assert found
    assert any("Volumen" in warning for warning in found[0].warnings)


def test_duplicate_gap_nan_and_impossible_ohlc():
    bars = fixture()
    for bad in [
        [bars[0], *bars],
        [bars[0], *bars[20:]],
        [replace(bars[0], high=float("nan")), *bars[1:]],
        [replace(bars[0], low=10000), *bars[1:]],
    ]:
        assert validate_bars(bad)
        assert detect_patterns("TEST", bad) == []


def test_volume_breakout_excludes_own_volume_from_average():
    bars = fixture()
    pattern = next(p for p in detect_patterns("TEST", bars) if p.kind == "cup_with_handle")
    breakout = replace(
        bars[-1],
        date=bars[-1].date + timedelta(days=3),
        open=pattern.pivot,
        low=pattern.pivot * 0.999,
        high=pattern.pivot * 1.03,
        close=pattern.pivot * 1.02,
        volume=2000,
    )
    found = next(p for p in detect_patterns("TEST", bars + [breakout]) if p.kind == pattern.kind)
    assert found.status == "breakout"
    assert found.breakout_volume_ratio == pytest.approx(
        2000 / np.mean([b.volume for b in bars[-50:]]), abs=0.001
    )
    assert found.detected_on == pattern.detected_on
    assert found.points == pattern.points
    low_volume = next(
        p
        for p in detect_patterns("TEST", bars + [replace(breakout, volume=100)])
        if p.kind == pattern.kind
    )
    assert low_volume.status == "unconfirmed_breakout"


@pytest.mark.parametrize(
    "kind", ["cup_with_handle", "cup_without_handle", "double_bottom", "high_tight_flag", "box"]
)
def test_geometry_exists_at_its_claimed_detection_date(kind):
    bars = fixture(kind)
    found = next(p for p in detect_patterns("TEST", bars) if p.kind == kind)
    prefix = [b for b in bars if b.date.isoformat() <= found.detected_on]
    replay = next(p for p in detect_patterns("TEST", prefix) if p.id == found.id)
    assert replay.points == found.points
    assert replay.detected_on == found.detected_on
    assert replay.pivot == found.pivot


@pytest.mark.parametrize(
    "parameters",
    [
        {"cup_max_depth_pct": 51},
        {"handle_max_depth_pct": 16},
        {"cup_min_depth_pct": 30, "cup_max_depth_pct": 20},
        {"handle_min_days": 10, "handle_max_days": 5},
        {"volume_dry_up_ratio": float("nan")},
        {"unknown": 1},
    ],
)
def test_parameter_validation(parameters):
    with pytest.raises(ValidationError):
        PatternParameters(**parameters)


def test_parameter_hash_is_reproducible_and_changes():
    assert PatternParameters().fingerprint == PatternParameters().fingerprint
    assert PatternParameters().fingerprint != PatternParameters(cup_max_depth_pct=40).fingerprint
    assert (
        PatternParameters().fingerprint
        == PatternParameters.model_validate(PatternParameters().model_dump()).fingerprint
    )


@pytest.mark.parametrize(
    "prices", [np.linspace(100, 200, 200), np.linspace(200, 100, 200), np.full(200, 100)]
)
def test_featureless_trends_and_flat_series_are_not_bases(prices):
    assert detect_patterns("TEST", series(prices)) == []


def test_noisy_pointed_v_stays_rejected():
    rng = np.random.default_rng(41)
    prices = list(np.linspace(60, 100, 60)) + list(
        np.interp(np.arange(1, 66), [0, 32, 65], [100, 65, 100]) + rng.normal(0, 0.2, 65)
    )
    assert not any(p.kind.startswith("cup") for p in detect_patterns("TEST", series(prices)))


def test_upper_half_and_depth_rules_reject_a_bad_handle():
    bars = fixture("cup_with_handle")
    bad = [
        replace(b, open=b.close * 0.8, high=b.high * 0.8, low=b.low * 0.8, close=b.close * 0.8)
        if i >= 125
        else b
        for i, b in enumerate(bars)
    ]
    assert not any(p.kind == "cup_with_handle" for p in detect_patterns("TEST", bad))


def test_higher_second_bottom_does_not_pass_double_bottom_rule():
    prices = list(np.linspace(60, 100, 60)) + list(
        np.interp(np.arange(1, 62), [0, 15, 30, 45, 61], [100, 70, 93, 75, 92])
    )
    assert not any(p.kind == "double_bottom" for p in detect_patterns("TEST", series(prices)))


def test_weak_mast_does_not_become_high_tight_flag():
    bars = fixture("high_tight_flag")
    prices = [b.close for b in bars]
    prices[:80] = np.linspace(65, 100, 80)
    assert not any(p.kind == "high_tight_flag" for p in detect_patterns("TEST", series(prices)))


def test_first_breakout_gap_can_also_be_the_first_observation():
    bars = fixture("double_bottom")
    found = next(p for p in detect_patterns("TEST", bars) if p.kind == "double_bottom")
    prefix = [b for b in bars if str(b.date) < found.detected_on]
    last = bars[len(prefix)]
    gap = replace(last, open=94, high=96, low=93.5, close=95, volume=2000)
    matches = [p for p in detect_patterns("TEST", prefix + [gap]) if p.kind == "double_bottom"]
    assert matches
    assert matches[0].detected_on == str(gap.date)
    assert matches[0].breakout_on == str(gap.date)


def test_new_low_before_recovery_invalidates_the_second_bottom():
    bars = fixture("double_bottom")
    original = next(p for p in detect_patterns("TEST", bars) if p.kind == "double_bottom")
    changed = list(bars)
    index = 60 + 54
    changed[index] = replace(changed[index], open=60, high=60.12, low=59.88, close=60)
    result = detect_patterns("TEST", changed)
    for p in result:
        if p.kind != "double_bottom":
            continue
        second = p.points[3]
        observed = [b for b in changed if second.date <= str(b.date) <= p.detected_on]
        assert min(b.low for b in observed) >= second.value
    assert not any(
        p.kind == "double_bottom"
        and p.points[3].date == original.points[3].date
        and p.detected_on >= str(changed[index].date)
        for p in result
    )
