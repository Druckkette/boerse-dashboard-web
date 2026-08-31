from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.domain.market.ampel import TrendAmpelBar, compute_trend_ampel
from app.services.market import (
    _ampel_cycle,
    _build_ampel_warning_checks,
    _detect_failing_rally,
    _last_cycle_markers,
    _legacy_market_action_and_tone,
)


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


def test_negative_upper_half_close_counts_as_anchor_day() -> None:
    bars = _correction_to_red_bars()
    bars.append(
        _bar(
            62,
            open_price=98.2,
            close=97.5,
            high=99.0,
            low=95.0,
            volume=1_100_000,
        )
    )

    latest = compute_trend_ampel(bars)[-1]

    assert latest.phase == "rot"
    assert latest.anchor_date == "2025-03-05"
    assert latest.floor_mark == 95.0


def test_active_cycle_values_are_marked_current() -> None:
    points = compute_trend_ampel(_startschuss_to_green_bars())
    latest = points[-1]
    anchor_date, floor_mark, startschuss_low = _last_cycle_markers(points, latest)

    cycle = _ampel_cycle(
        latest,
        anchor_date=anchor_date,
        floor_mark=floor_mark,
        startschuss_low=startschuss_low,
    )

    assert cycle.anchor_date is not None
    assert cycle.floor_mark is not None
    assert cycle.startschuss_low is not None
    assert cycle.anchor_current is True
    assert cycle.floor_current is True
    assert cycle.startschuss_current is True


def test_green_resets_to_red_when_close_breaks_startschuss_low() -> None:
    bars = _startschuss_to_green_bars()
    points = compute_trend_ampel(bars)
    startschuss_low = points[-1].startschuss_low

    assert points[-1].phase == "gruen"
    assert startschuss_low is not None

    bars.append(
        _bar(
            71,
            open_price=startschuss_low + 1.0,
            close=startschuss_low - 0.5,
            high=startschuss_low + 1.4,
            low=startschuss_low - 1.0,
            volume=1_300_000,
        )
    )

    latest = compute_trend_ampel(bars)[-1]

    assert latest.phase == "rot"
    assert latest.startschuss_low is None


def test_historical_cycle_values_are_marked_old_after_red_reset() -> None:
    bars = _startschuss_to_green_bars()
    points = compute_trend_ampel(bars)
    startschuss_low = points[-1].startschuss_low
    assert startschuss_low is not None
    bars.append(
        _bar(
            71,
            open_price=startschuss_low + 1.0,
            close=startschuss_low - 0.5,
            high=startschuss_low + 1.4,
            low=startschuss_low - 1.0,
            volume=1_300_000,
        )
    )
    points = compute_trend_ampel(bars)
    latest = points[-1]
    anchor_date, floor_mark, fallback_startschuss_low = _last_cycle_markers(points, latest)

    cycle = _ampel_cycle(
        latest,
        anchor_date=anchor_date,
        floor_mark=floor_mark,
        startschuss_low=fallback_startschuss_low,
    )

    assert latest.phase == "rot"
    assert latest.anchor_date is None
    assert latest.floor_mark is None
    assert latest.startschuss_low is None
    assert cycle.anchor_date is not None
    assert cycle.floor_mark is not None
    assert cycle.startschuss_low is not None
    assert cycle.anchor_current is False
    assert cycle.floor_current is False
    assert cycle.startschuss_current is False


def test_uptrend_resets_to_red_when_close_breaks_startschuss_low() -> None:
    bars = _green_to_uptrend_bars()
    points = compute_trend_ampel(bars)
    startschuss_low = points[-1].startschuss_low

    assert points[-1].phase == "aufwaertstrend"
    assert startschuss_low is not None

    bars.append(
        _bar(
            240,
            open_price=startschuss_low + 1.0,
            close=startschuss_low - 0.5,
            high=startschuss_low + 1.4,
            low=startschuss_low - 1.0,
            volume=1_500_000,
        )
    )

    latest = compute_trend_ampel(bars)[-1]

    assert latest.phase == "rot"
    assert latest.startschuss_low is None


def test_uptrend_enters_pressure_after_three_closes_below_ema21() -> None:
    points = compute_trend_ampel(_uptrend_loses_ema21_sma50_order_bars())
    latest = next(point for point in points if point.phase == "gelb_trend_unter_druck")

    assert "aufwaertstrend" in [point.phase for point in points]
    assert latest.phase == "gelb_trend_unter_druck"
    assert latest.startschuss_low is not None
    assert latest.close is not None
    assert latest.sma200 is not None
    assert latest.ema21 is not None
    assert latest.sma50 is not None
    assert latest.close > latest.startschuss_low
    assert latest.close > latest.sma200


def test_uptrend_turns_red_on_ten_percent_drawdown_from_own_high() -> None:
    bars = _green_to_uptrend_bars()
    bars.append(
        _bar(
            len(bars),
            open_price=171.0,
            close=153.0,
            high=171.0,
            low=152.0,
            volume=1_500_000,
        )
    )

    latest = compute_trend_ampel(bars)[-1]
    previous = compute_trend_ampel(bars[:-1])[-1]

    assert latest.high_52w is not None
    assert latest.close is not None
    assert previous.startschuss_low is not None
    assert latest.sma200 is not None
    assert (latest.close / latest.high_52w - 1) * 100 < -10
    assert latest.close > previous.startschuss_low
    assert latest.close > latest.sma200
    assert latest.phase == "rot"
    assert latest.anchor_date is None


def test_ampel_turns_red_when_close_breaks_sma200() -> None:
    points = compute_trend_ampel(_green_breaks_sma200_without_breaking_startschuss_low_bars())
    previous = points[-2]
    latest = points[-1]

    assert previous.phase in {"gruen", "aufwaertstrend", "gelb_trend_unter_druck"}
    assert previous.startschuss_low is not None
    assert previous.sma200 is not None
    assert latest.close is not None
    assert latest.close > previous.startschuss_low
    assert latest.close < previous.sma200
    assert latest.phase == "rot"
    assert latest.startschuss_low is None


def test_startschuss_can_turn_yellow_below_sma200() -> None:
    points = compute_trend_ampel(_green_without_full_ma_order_bars())
    first_yellow_index = next(index for index, point in enumerate(points) if point.phase == "gelb_startschuss")
    first_yellow = points[first_yellow_index]
    next_yellow = points[first_yellow_index + 1]

    assert first_yellow.close is not None
    assert first_yellow.sma200 is not None
    assert first_yellow.close < first_yellow.sma200
    assert first_yellow.phase == "gelb_startschuss"
    assert next_yellow.phase == "gelb_startschuss"


def test_loss_gain_ratio_uses_last_ten_sessions() -> None:
    closes = [100, 99, 98, 99, 98, 97, 96, 97, 96, 95, 94]
    bars = [
        _bar(
            index,
            open_price=closes[index - 1] if index else closes[index],
            close=float(close),
            high=float(close) + 1.0,
            low=float(close) - 1.0,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    ]

    latest = compute_trend_ampel(bars)[-1]

    assert latest.loss_days_10d == 8
    assert latest.gain_days_10d == 2
    assert latest.loss_gain_ratio_10d == pytest.approx(4.0)


def test_loss_gain_warning_activates_when_loss_days_outnumber_gain_days() -> None:
    closes = [100, 101, 100, 99, 100, 99, 98, 99, 98, 97, 98]
    bars = [
        _bar(
            index,
            open_price=closes[index - 1] if index else closes[index],
            close=float(close),
            high=float(close) + 1.0,
            low=float(close) - 1.0,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    ]
    points = compute_trend_ampel(bars)
    latest = points[-1]

    assert latest.loss_days_10d == 6
    assert latest.gain_days_10d == 4

    checks = _build_ampel_warning_checks(
        points=points,
        latest=latest,
        intermarket=[],
        defensive_lead=None,
        defensive_spread_pct=None,
        index_name="S&P 500",
    )
    check = next(item for item in checks if item.label == "Verlusttage/Gewinntage (10T)")

    assert check.active_warning is True
    assert check.passed is False
    assert check.tone == "warning"


def test_under_50sma_is_counted_once_as_trend_break() -> None:
    points = compute_trend_ampel(_rising_bars(220, start=100.0, step=0.2))
    latest = replace(
        points[-1],
        close=139.0,
        sma50=140.0,
        dist_50sma_pct=-0.7,
        neg_reversals_10d=0,
        low_cr_5d=0,
        dist_count_25=0,
        loss_days_10d=4,
        gain_days_10d=6,
        loss_gain_ratio_10d=0.7,
        dist_21ema=0.2,
        sma200=120.0,
        up_vol_declining=False,
    )

    checks = _build_ampel_warning_checks(
        points=[*points[:-1], latest],
        latest=latest,
        intermarket=[],
        defensive_lead=None,
        defensive_spread_pct=None,
        index_name="Russell 2000",
    )
    active = [check.label for check in checks if check.active_warning]

    assert "Kurs über 50-SMA" in active
    assert "Überdehnt über 50-SMA" not in active
    assert active.count("Kurs über 50-SMA") == 1


@pytest.mark.parametrize(
    ("phase", "warning_count", "breadth_mode", "vix_regime", "expected_mode", "expected_tone"),
    [
        ("aufwaertstrend", 1, "rueckenwind", "Ruhig", "Offensiv", "good"),
        ("aufwaertstrend", 2, "rueckenwind", "Ruhig", "Neutral", "warning"),
        ("aufwaertstrend", 3, "rueckenwind", "Ruhig", "Neutral", "warning"),
        ("aufwaertstrend", 4, "rueckenwind", "Ruhig", "Defensiv", "bad"),
        ("aufwaertstrend", 0, "schutz", "Ruhig", "Defensiv", "bad"),
        ("aufwaertstrend", 0, "rueckenwind", "Stress", "Defensiv", "bad"),
        ("rot", 0, "rueckenwind", "Ruhig", "Defensiv", "bad"),
    ],
)
def test_market_mode_uses_four_warning_threshold(
    phase: str,
    warning_count: int,
    breadth_mode: str,
    vix_regime: str,
    expected_mode: str,
    expected_tone: str,
) -> None:
    mode, tone, _ = _legacy_market_action_and_tone(
        phase,
        warning_count,
        breadth_mode,
        vix_regime,
    )

    assert mode == expected_mode
    assert tone == expected_tone


def test_failing_rally_detail_uses_recovered_drop_share_not_price_gain() -> None:
    closes = [80 + index * (20 / 30) for index in range(31)]
    closes.extend([98.0, 95.0, 92.9, 93.2, 93.61])
    bars = [
        _bar(
            index,
            open_price=closes[index - 1] if index else closes[index],
            close=float(close),
            high=float(close) + 1.0,
            low=float(close) - 1.0,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    ]
    points = compute_trend_ampel(bars)

    rally = _detect_failing_rally(points)

    assert rally is not None
    assert rally.drop_from_high_pct == pytest.approx(7.1)
    assert rally.recovered_drop_pct == pytest.approx(10.0, abs=0.2)
    assert rally.current_below_high_pct == pytest.approx(-6.4, abs=0.2)

    checks = _build_ampel_warning_checks(
        points=points,
        latest=points[-1],
        intermarket=[],
        defensive_lead=None,
        defensive_spread_pct=None,
        index_name="Nasdaq",
    )
    check = next(item for item in checks if item.label == "Erholungsquote >=50%")

    assert check.active_warning is True
    assert "Rückeroberung 10% des Rückgangs" in check.detail
    assert "aktueller Abstand zum Hoch -6.4%" in check.detail


def test_recovery_ratio_check_is_present_without_relevant_correction() -> None:
    points = compute_trend_ampel(_rising_bars(70, start=100.0, step=0.2))

    checks = _build_ampel_warning_checks(
        points=points,
        latest=points[-1],
        intermarket=[],
        defensive_lead=None,
        defensive_spread_pct=None,
        index_name="S&P 500",
    )
    check = next(item for item in checks if item.label == "Erholungsquote >=50%")

    assert check.active_warning is False
    assert check.passed is True
    assert check.tone == "neutral"
    assert "nicht anwendbar" in check.detail


def test_recovery_ratio_check_is_present_below_correction_threshold() -> None:
    closes = [80 + index * (20 / 30) for index in range(31)]
    closes.extend([99.0, 98.0, 96.0, 97.0, 98.0])
    bars = [
        _bar(
            index,
            open_price=closes[index - 1] if index else closes[index],
            close=float(close),
            high=float(close) + 1.0,
            low=float(close) - 1.0,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    ]
    points = compute_trend_ampel(bars)

    checks = _build_ampel_warning_checks(
        points=points,
        latest=points[-1],
        intermarket=[],
        defensive_lead=None,
        defensive_spread_pct=None,
        index_name="Nasdaq",
    )
    check = next(item for item in checks if item.label == "Erholungsquote >=50%")

    assert check.active_warning is False
    assert check.passed is True
    assert check.tone == "neutral"
    assert "unter der Prüfschwelle von 5%" in check.detail


def test_green_waits_for_full_ma_order_before_uptrend() -> None:
    points = compute_trend_ampel(_green_without_full_ma_order_bars())
    latest = points[-1]

    assert latest.phase == "gruen"
    assert latest.close is not None
    assert latest.ema21 is not None
    assert latest.sma50 is not None
    assert latest.sma200 is not None
    assert latest.close > latest.ema21
    assert latest.close > latest.sma200
    assert latest.ema21 > latest.sma50
    assert latest.sma50 < latest.sma200
    assert latest.ma_order is False


def test_green_cannot_upgrade_to_uptrend_with_close_below_ema21() -> None:
    all_bars = _green_to_uptrend_bars()
    all_points = compute_trend_ampel(all_bars)
    first_uptrend = next(index for index, point in enumerate(all_points) if point.phase == "aufwaertstrend")
    bars = all_bars[:first_uptrend]
    previous = compute_trend_ampel(bars)[-1]
    assert previous.phase == "gruen"
    assert previous.ema21 is not None
    assert previous.sma200 is not None
    close = max(previous.sma200 + 1.0, previous.ema21 - 0.2)
    bars.append(
        _bar(
            len(bars),
            open_price=close + 0.5,
            close=close,
            high=close + 1.0,
            low=close - 1.0,
            volume=1_120_000,
        )
    )

    latest = compute_trend_ampel(bars)[-1]

    assert latest.phase == "gruen"
    assert latest.close is not None
    assert latest.ema21 is not None
    assert latest.sma200 is not None
    assert latest.ma_order is True
    assert latest.close < latest.ema21
    assert latest.close > latest.sma200


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
            _bar(70, open_price=102.2, close=103.5, high=103.8, low=101.5, volume=1_300_000),
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
    for open_price, close, high, low, volume in [
        (171.0, 175.0, 176.0, 170.0, 1_120_000),
        (175.0, 179.0, 180.0, 174.0, 1_130_000),
        (179.0, 171.0, 180.0, 170.0, 1_200_000),
        (171.0, 176.0, 177.0, 170.0, 1_150_000),
        (176.0, 181.0, 182.0, 175.0, 1_160_000),
        (181.0, 183.0, 184.0, 180.0, 1_150_000),
        (183.0, 185.0, 186.0, 182.0, 1_150_000),
        (185.0, 187.0, 188.0, 184.0, 1_150_000),
    ]:
        bars.append(
            _bar(
                len(bars),
                open_price=open_price,
                close=close,
                high=high,
                low=low,
                volume=volume,
            )
        )
    return bars


def _uptrend_loses_ema21_sma50_order_bars() -> list[TrendAmpelBar]:
    bars = _green_to_uptrend_bars()
    previous_close = bars[-1].close
    for close in (169.5, 169.4, 169.3):
        bars.append(
            _bar(
                len(bars),
                open_price=previous_close,
                close=float(close),
                high=max(previous_close, float(close)) + 0.8,
                low=min(previous_close, float(close)) - 0.8,
                volume=1_050_000,
            )
        )
        previous_close = float(close)
    return bars


def _green_breaks_sma200_without_breaking_startschuss_low_bars() -> list[TrendAmpelBar]:
    bars = _green_to_uptrend_bars()
    previous_close = bars[-1].close
    for offset in range(len(bars), len(bars) + 120):
        bars.append(
            _bar(
                offset,
                open_price=previous_close,
                close=175.0,
                high=max(previous_close, 175.0) + 1.0,
                low=min(previous_close, 175.0) - 1.0,
                volume=1_100_000,
            )
        )
        previous_close = 175.0

    bars.append(
        _bar(
            len(bars),
            open_price=previous_close,
            close=160.0,
            high=previous_close + 1.0,
            low=159.0,
            volume=1_200_000,
        )
    )
    return bars


def _green_without_full_ma_order_bars() -> list[TrendAmpelBar]:
    bars: list[TrendAmpelBar] = []
    previous_close = 180.0
    for index in range(220):
        close = 180.0 - index * 0.2
        bars.append(
            _bar(
                index,
                open_price=previous_close,
                close=close,
                high=close + 1.0,
                low=close - 1.0,
                volume=1_000_000 + index * 500,
            )
        )
        previous_close = close

    for offset, close in enumerate(
        [136, 138, 139, 140, 141, 142, 145, 147, 149, 151, 153, 155, 157, 159, 161, 163, 165, 167, 169, 171],
        220,
    ):
        bars.append(
            _bar(
                offset,
                open_price=previous_close,
                close=float(close),
                high=max(previous_close, float(close)) + 1.0,
                low=min(previous_close, float(close)) - 1.0,
                volume=1_200_000 + offset * 1_000,
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
