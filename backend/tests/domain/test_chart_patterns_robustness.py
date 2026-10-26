"""Structural lifecycle regressions independent of the fitting implementation."""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from app.domain.chart_patterns import Bar, PatternParameters, detect_patterns


def _rounded_cup_with_handle(depth: float) -> list[Bar]:
    """A rounded base, then a 9 % upper-half pullback and initial recovery."""
    curve = np.linspace(-1, 1, 66)[1:]
    prices = [
        *np.linspace(60, 100, 60),
        *(100 - depth + depth * curve**2),
        98,
        96,
        94,
        92,
        91,
        92,
        94,
        96,
        97,
    ]
    day = date(2024, 1, 1)
    bars = []
    for i, price in enumerate(prices):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        bars.append(
            Bar(
                day,
                float(price),
                float(price * 1.002),
                float(price * 0.998),
                float(price),
                1400 if i < 60 else 400,
            )
        )
        day += timedelta(days=1)
    return bars


def _append(bars: list[Bar], price: float, *, low: float | None = None) -> None:
    day = bars[-1].date + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    bars.append(
        replace(
            bars[-1],
            date=day,
            open=price,
            high=price * 1.002,
            low=price * 0.998 if low is None else low,
            close=price,
            volume=2000,
        )
    )


@pytest.mark.parametrize(
    ("depth", "bad_low"),
    [
        # The pullback is only 11.2 % deep, but crosses this shallow cup's midpoint.
        (20, 89),
        # This deeper cup's midpoint is preserved, but the handle exceeds 15 %.
        (40, 82),
    ],
)
def test_handle_that_loses_its_structure_cannot_later_be_a_valid_breakout(depth, bad_low):
    bars = _rounded_cup_with_handle(depth)
    initial = next(p for p in detect_patterns("TEST", bars) if p.kind == "cup_with_handle")
    assert initial.status == "ready"
    _append(bars, bad_low)
    _append(bars, 95)
    _append(bars, 101)
    same = next(p for p in detect_patterns("TEST", bars) if p.id == initial.id)
    assert same.status == "invalidated"
    assert same.breakout_on is None
    assert same.points == initial.points


def test_handle_violation_is_detected_even_if_the_session_recovers_its_close():
    bars = _rounded_cup_with_handle(40)
    initial = next(p for p in detect_patterns("TEST", bars) if p.kind == "cup_with_handle")
    # OHLC geometry defines handle depth, so a deep wick cannot disappear merely
    # because the same session closes in the original handle's price range.
    _append(bars, 95, low=82)
    _append(bars, 101)
    same = next(p for p in detect_patterns("TEST", bars) if p.id == initial.id)
    assert same.status == "invalidated"
    assert same.breakout_on is None


def test_second_bottom_cannot_break_undercut_limit_and_then_keep_old_breakout():
    prices = [
        *np.linspace(60, 100, 60),
        *np.interp(np.arange(1, 62), [0, 15, 30, 45, 61], [100, 75, 93, 70, 92]),
    ]
    dates = _rounded_cup_with_handle(30)
    bars = [
        replace(
            b,
            open=float(price),
            high=float(price * 1.002),
            low=float(price * 0.998),
            close=float(price),
        )
        for b, price in zip(dates, prices)
    ]
    initial = next(p for p in detect_patterns("TEST", bars) if p.kind == "double_bottom")
    assert initial.status == "ready"
    _append(bars, 90, low=60)
    _append(bars, 95)
    same = next(p for p in detect_patterns("TEST", bars) if p.id == initial.id)
    assert same.status == "invalidated"
    assert same.breakout_on is None


def test_old_handle_cannot_wait_beyond_configured_maximum_and_then_break_out():
    bars = _rounded_cup_with_handle(30)
    parameters = PatternParameters(handle_max_days=12)
    initial = next(
        p for p in detect_patterns("TEST", bars, parameters) if p.kind == "cup_with_handle"
    )
    for _ in range(15):
        _append(bars, 96)
    _append(bars, 101)
    same = next(p for p in detect_patterns("TEST", bars, parameters) if p.id == initial.id)
    assert same.status == "expired"
    assert same.breakout_on is None
