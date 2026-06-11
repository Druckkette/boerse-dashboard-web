from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.domain.market.ampel import TrendAmpelBar, compute_trend_ampel


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "market" / "ampel"


@pytest.mark.parametrize("fixture_path", sorted(FIXTURE_DIR.glob("*.json")), ids=lambda path: path.stem)
def test_trend_ampel_golden_master(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    points = compute_trend_ampel(_bars_for_scenario(fixture["scenario"]))
    expected = fixture["expected"]

    assert points
    assert points[-1].phase == expected["final_phase"]

    phase_path = [point.phase for point in points]
    for phase in expected["phase_path_contains"]:
        assert phase in phase_path

    assert (points[-1].anchor_date is not None) is expected["anchor_date_present"]
    assert (points[-1].startschuss_low is not None) is expected["startschuss_low_present"]


def test_trend_ampel_survives_empty_input() -> None:
    assert compute_trend_ampel([]) == []


def _bars_for_scenario(scenario: str) -> list[TrendAmpelBar]:
    if scenario == "correction_to_red":
        return _correction_to_red_bars()
    if scenario == "startschuss_to_green":
        return _startschuss_to_green_bars()
    if scenario == "green_to_uptrend":
        return _green_to_uptrend_bars()
    raise AssertionError(f"Unknown scenario fixture: {scenario}")


def _correction_to_red_bars() -> list[TrendAmpelBar]:
    bars = _rising_bars(61, start=100.0, step=0.2)
    bars.append(
        _bar(
            61,
            open_price=112.0,
            close=98.0,
            high=113.0,
            low=97.0,
            volume=1_250_000,
        )
    )
    return bars


def _startschuss_to_green_bars() -> list[TrendAmpelBar]:
    bars = _correction_to_red_bars()
    bars.extend(
        [
            _bar(62, open_price=98.0, close=99.5, high=100.0, low=98.2, volume=1_050_000),
            _bar(63, open_price=99.5, close=99.8, high=100.1, low=98.8, volume=1_020_000),
            _bar(64, open_price=99.8, close=100.0, high=100.4, low=99.0, volume=1_030_000),
            _bar(65, open_price=100.0, close=100.2, high=100.5, low=99.2, volume=1_010_000),
            _bar(66, open_price=100.2, close=100.4, high=100.8, low=99.5, volume=1_000_000),
            _bar(67, open_price=100.4, close=101.8, high=102.0, low=100.0, volume=1_350_000),
            _bar(68, open_price=101.8, close=102.0, high=102.3, low=101.0, volume=1_120_000),
            _bar(69, open_price=102.0, close=102.2, high=102.5, low=101.3, volume=1_110_000),
            _bar(70, open_price=102.2, close=102.4, high=102.7, low=101.5, volume=1_100_000),
        ]
    )
    return bars


def _green_to_uptrend_bars() -> list[TrendAmpelBar]:
    bars = _rising_bars(220, start=100.0, step=0.25)
    bars.extend(
        [
            _bar(220, open_price=154.5, close=136.0, high=156.5, low=134.5, volume=1_350_000),
            _bar(221, open_price=136.5, close=138.0, high=139.0, low=135.8, volume=1_050_000),
            _bar(222, open_price=138.0, close=139.0, high=140.0, low=136.5, volume=1_030_000),
            _bar(223, open_price=139.0, close=140.0, high=141.0, low=137.4, volume=1_020_000),
            _bar(224, open_price=140.0, close=141.0, high=142.0, low=138.3, volume=1_010_000),
            _bar(225, open_price=141.0, close=142.0, high=143.0, low=139.4, volume=1_000_000),
            _bar(226, open_price=142.0, close=145.0, high=146.0, low=143.0, volume=1_400_000),
        ]
    )
    previous_close = 145.0
    for offset, close in enumerate([147, 149, 151, 153, 155, 157, 159, 161, 163, 165, 167, 169, 171], 227):
        bars.append(
            _bar(
                offset,
                open_price=previous_close,
                close=float(close),
                high=float(close) + 1.0,
                low=previous_close - 1.0,
                volume=1_120_000,
            )
        )
        previous_close = float(close)
    return bars


def _rising_bars(count: int, *, start: float, step: float) -> list[TrendAmpelBar]:
    bars: list[TrendAmpelBar] = []
    previous_close = start
    for index in range(count):
        close = start + index * step
        bars.append(
            _bar(
                index,
                open_price=previous_close,
                close=close,
                high=close + 1.0,
                low=close - 1.0,
                volume=1_000_000 + index * 1_000,
            )
        )
        previous_close = close
    return bars


def _bar(
    offset: int,
    *,
    open_price: float,
    close: float,
    high: float,
    low: float,
    volume: int,
) -> TrendAmpelBar:
    return TrendAmpelBar(
        date=date(2025, 1, 2) + timedelta(days=offset),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )
