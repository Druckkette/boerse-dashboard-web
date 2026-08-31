from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.domain.market.ampel import (
    MarketSwingPoint,
    TrendAmpelBar,
    _compute_ampel_frame,
    _swing_structure,
    compute_atr_zigzag_swings,
    compute_trend_ampel,
)


def test_startschuss_is_not_confirmed_before_fifth_session_after_anchor() -> None:
    result = _run_frame(_book_frame())

    assert result.iloc[6]["Ampel_Phase"] == "rot"
    assert result.iloc[7]["Ampel_Phase"] == "gelb_startschuss"


def test_yellow_does_not_turn_green_from_elapsed_time_alone() -> None:
    frame = _book_frame(confirm_green=None)

    assert _run_frame(frame).iloc[12]["Ampel_Phase"] == "gelb_startschuss"


def test_accumulation_day_confirms_green_after_three_full_sessions() -> None:
    frame = _book_frame(confirm_green="accumulation")
    result = _run_frame(frame)

    assert result.iloc[9]["Ampel_Phase"] == "gelb_startschuss"
    assert result.iloc[10]["Ampel_Phase"] == "gruen"


def test_three_closes_above_ema21_confirm_green() -> None:
    frame = _book_frame(confirm_green="ema21")

    assert _run_frame(frame).iloc[10]["Ampel_Phase"] == "gruen"


def test_green_may_remain_below_sma200_and_emits_warning() -> None:
    frame = _book_frame(confirm_green="ema21")
    row = frame.index[11]
    frame.loc[row, "SMA200"] = frame.loc[row, "Close"] + 1.0
    result = _run_frame(frame)

    assert result.iloc[11]["Ampel_Phase"] == "gruen"
    assert bool(result.iloc[11]["Green_Below_SMA200"]) is True


def test_uptrend_cannot_start_below_sma200() -> None:
    frame = _uptrend_ready_frame()
    row = frame.index[13]
    frame.loc[row, "SMA200"] = frame.loc[row, "Close"] + 1.0

    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"


def test_uptrend_cannot_start_with_close_below_ema21() -> None:
    frame = _uptrend_ready_frame()
    row = frame.index[13]
    frame.loc[row, "EMA21"] = frame.loc[row, "Close"] + 0.1

    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"


def test_uptrend_needs_three_complete_sessions_above_ema21() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[13], "Consec_Low_above_21"] = 2

    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"


def test_uptrend_needs_three_complete_sessions_above_sma50() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[13], "Consec_Low_above_50"] = 2

    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"


def test_uptrend_needs_three_sessions_of_correct_ma_order() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[13], "MA_Order_Streak"] = 2

    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"


def test_uptrend_needs_rising_ema21_and_sma50() -> None:
    frame = _uptrend_ready_frame()
    row = frame.index[13]
    frame.loc[row, "EMA21_Rising"] = False
    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"

    frame.loc[row, "EMA21_Rising"] = True
    frame.loc[row, "SMA50_Rising"] = False
    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"


def test_uptrend_needs_confirmed_up_market_structure() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[13], "Market_Structure"] = "mixed"

    assert _run_frame(frame).iloc[13]["Ampel_Phase"] == "gruen"


def test_uptrend_uses_its_own_high_instead_of_old_correction_high() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[0], "High"] = 130.0
    frame.loc[frame.index[14], ["Open", "High", "Low", "Close"]] = [93.0, 94.0, 91.8, 92.0]
    result = _run_frame(frame)

    assert result.iloc[13]["Ampel_Phase"] == "aufwaertstrend"
    assert result.iloc[14]["Ampel_Phase"] == "aufwaertstrend"
    assert result.iloc[14]["Uptrend_High"] < 100.0


def test_uptrend_turns_red_at_ten_percent_from_own_high() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[13], "High"] = 100.0
    frame.loc[frame.index[14], ["Open", "High", "Low", "Close"]] = [92.0, 93.0, 89.5, 90.0]
    result = _run_frame(frame)

    assert result.iloc[13]["Ampel_Phase"] == "aufwaertstrend"
    assert result.iloc[14]["Ampel_Phase"] == "rot"


def test_one_or_two_closes_below_ema21_do_not_change_uptrend() -> None:
    frame = _uptrend_ready_frame()
    rows = frame.index[14:16]
    frame.loc[rows, "Consec_Close_Below_21"] = [1, 2]
    frame.loc[rows, "EMA21"] = frame.loc[rows, "Close"] + 0.2
    result = _run_frame(frame)

    assert result.iloc[14]["Ampel_Phase"] == "aufwaertstrend"
    assert result.iloc[15]["Ampel_Phase"] == "aufwaertstrend"


def test_three_closes_below_ema21_enter_pressure_phase() -> None:
    frame = _uptrend_ready_frame()
    rows = frame.index[14:17]
    frame.loc[rows, "Consec_Close_Below_21"] = [1, 2, 3]
    frame.loc[rows, "EMA21"] = frame.loc[rows, "Close"] + 0.2

    assert _run_frame(frame).iloc[16]["Ampel_Phase"] == "gelb_trend_unter_druck"


def test_volume_confirmed_significant_sma50_break_enters_pressure_phase() -> None:
    frame = _uptrend_ready_frame()
    row = frame.index[14]
    frame.loc[row, "SMA50"] = 94.0
    frame.loc[row, "ATR21"] = 2.0
    frame.loc[row, "Close"] = 92.5
    frame.loc[row, "Low"] = 92.0
    frame.loc[row, "Volume"] = 1_300_000
    frame.loc[frame.index[13], "Volume"] = 1_000_000
    frame.loc[row, "Vol_SMA50"] = 1_100_000

    assert _run_frame(frame).iloc[14]["Ampel_Phase"] == "gelb_trend_unter_druck"


def test_negative_ema21_sma50_cross_enters_pressure_phase() -> None:
    frame = _uptrend_ready_frame()
    row = frame.index[14]
    frame.loc[row, "EMA21"] = 89.0
    frame.loc[row, "SMA50"] = 90.0

    assert _run_frame(frame).iloc[14]["Ampel_Phase"] == "gelb_trend_unter_druck"


def test_break_of_last_higher_swing_low_enters_pressure_phase() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[13:15], "Latest_Swing_Low"] = 93.0
    frame.loc[frame.index[14], "Close"] = 92.5
    frame.loc[frame.index[14], "Low"] = 92.0

    assert _run_frame(frame).iloc[14]["Ampel_Phase"] == "gelb_trend_unter_druck"


def test_four_internal_warnings_need_two_consecutive_sessions_for_pressure() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[14:16], "Phase_Warning_Streak"] = [1, 2]
    result = _run_frame(frame)

    assert result.iloc[14]["Ampel_Phase"] == "aufwaertstrend"
    assert result.iloc[15]["Ampel_Phase"] == "gelb_trend_unter_druck"


def test_two_qualified_closes_above_ema21_allow_recovery() -> None:
    frame = _pressure_frame(recovery_structure="up")
    result = _run_frame(frame)

    assert result.iloc[16]["Ampel_Phase"] == "gelb_trend_unter_druck"
    assert result.iloc[18]["Ampel_Phase"] == "aufwaertstrend"


def test_mixed_structure_recovers_from_pressure_to_green_first() -> None:
    frame = _pressure_frame(recovery_structure="mixed")

    assert _run_frame(frame).iloc[18]["Ampel_Phase"] == "gruen"


def test_down_structure_turns_pressure_phase_red() -> None:
    frame = _pressure_frame(recovery_structure="up")
    frame.loc[frame.index[17], "Market_Structure"] = "down"

    assert _run_frame(frame).iloc[17]["Ampel_Phase"] == "rot"


def test_startschuss_low_break_has_priority_and_allows_only_one_transition() -> None:
    frame = _book_frame(confirm_green="ema21")
    frame.loc[frame.index[11], ["Open", "High", "Low", "Close"]] = [91.0, 92.0, 89.0, 90.0]
    result = _run_frame(frame)

    assert result.iloc[10]["Ampel_Phase"] == "gruen"
    assert result.iloc[11]["Ampel_Phase"] == "rot"
    assert pd.isna(result.iloc[11]["Startschuss_Low"])


def test_equal_weight_or_breadth_mode_cannot_change_ampel_phase() -> None:
    bars = _simple_public_bars()
    strict = compute_trend_ampel(bars, over_50_warning_pct=5.0)
    relaxed = compute_trend_ampel(bars, over_50_warning_pct=7.0)

    assert [point.phase for point in strict] == [point.phase for point in relaxed]


def test_atr_zigzag_recognizes_higher_highs_and_higher_lows() -> None:
    swings = compute_atr_zigzag_swings(_zigzag_bars())
    highs = [swing for swing in swings if swing.pivot_type == "high"]
    lows = [swing for swing in swings if swing.pivot_type == "low"]

    assert len(highs) >= 2
    assert len(lows) >= 2
    assert _swing_structure(highs) == "higher"
    assert _swing_structure(lows) == "higher"


def test_swing_structure_ignores_difference_within_quarter_atr() -> None:
    swings = [
        MarketSwingPoint("high", 100.0, "2026-01-01", "2026-01-02", 4.0),
        MarketSwingPoint("high", 100.9, "2026-01-03", "2026-01-04", 4.0),
    ]

    assert _swing_structure(swings) == "equal"


def _book_frame(*, confirm_green: str | None = "ema21") -> pd.DataFrame:
    index = pd.date_range("2026-01-02", periods=24, freq="B")
    closes = np.array(
        [100.0, 89.0, 90.0, 90.2, 90.4, 90.6, 90.8, 92.0, 93.1, 93.4, 93.7, 94.0,
         94.3, 94.6, 94.8, 95.0, 95.2, 95.4, 95.6, 95.8, 96.0, 96.2, 96.4, 96.6]
    )
    frame = pd.DataFrame(index=index)
    frame["Open"] = closes - 0.2
    frame["High"] = closes + 0.5
    frame["Low"] = closes - 0.5
    frame["Close"] = closes
    frame["Volume"] = 1_000_000.0
    frame["Pct_Change"] = pd.Series(closes, index=index).pct_change().fillna(0.0) * 100
    frame["Closing_Range"] = 0.7
    frame["Dist_Count_25"] = 0
    frame["SMA50"] = 89.0
    frame["SMA200"] = 80.0
    frame["EMA21"] = 100.0
    frame["ATR21"] = 2.0
    frame["Vol_SMA50"] = 1_050_000.0
    frame["Consec_Low_above_21"] = 0
    frame["Consec_Low_above_50"] = 0
    frame["Consec_Close_Below_21"] = 0
    frame["Consec_Close_Above_21"] = 0
    frame["MA_Order_Streak"] = 0
    frame["EMA21_Rising"] = False
    frame["SMA50_Rising"] = False
    frame["Market_Structure"] = "unknown"
    frame["Latest_Swing_Low"] = np.nan
    frame["Phase_Warning_Streak"] = 0
    frame.iloc[1, frame.columns.get_loc("Low")] = 88.0
    frame.iloc[1, frame.columns.get_loc("High")] = 100.0
    frame.iloc[7, frame.columns.get_loc("Pct_Change")] = 1.2
    frame.iloc[7, frame.columns.get_loc("Volume")] = 1_200_000.0
    if confirm_green == "accumulation":
        frame.iloc[8, frame.columns.get_loc("Pct_Change")] = 1.1
        frame.iloc[8, frame.columns.get_loc("Volume")] = 1_300_000.0
    elif confirm_green == "ema21":
        frame.loc[index[8:11], "EMA21"] = 90.0
    return frame


def _uptrend_ready_frame() -> pd.DataFrame:
    frame = _book_frame(confirm_green="ema21")
    row = frame.index[13]
    frame.loc[row, "EMA21"] = 92.0
    frame.loc[row, "SMA50"] = 90.0
    frame.loc[row, "SMA200"] = 80.0
    frame.loc[row, "Consec_Low_above_21"] = 3
    frame.loc[row, "Consec_Low_above_50"] = 3
    frame.loc[row, "MA_Order_Streak"] = 3
    frame.loc[row, "EMA21_Rising"] = True
    frame.loc[row, "SMA50_Rising"] = True
    frame.loc[row, "Market_Structure"] = "up"
    frame.loc[row, "Latest_Swing_Low"] = 91.0
    frame.loc[frame.index[14]:, "EMA21"] = 92.0
    frame.loc[frame.index[14]:, "SMA50"] = 90.0
    frame.loc[frame.index[14]:, "SMA200"] = 80.0
    frame.loc[frame.index[14]:, "Market_Structure"] = "up"
    frame.loc[frame.index[14]:, "Latest_Swing_Low"] = 91.0
    return frame


def _pressure_frame(*, recovery_structure: str) -> pd.DataFrame:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[14:17], "Consec_Close_Below_21"] = [1, 2, 3]
    frame.loc[frame.index[14:17], "EMA21"] = frame.loc[frame.index[14:17], "Close"] + 0.1
    frame.loc[frame.index[17:19], "EMA21"] = 93.0
    frame.loc[frame.index[17:19], "Consec_Close_Above_21"] = [1, 2]
    frame.loc[frame.index[17:19], "SMA50"] = 90.0
    frame.loc[frame.index[17:19], "SMA200"] = 80.0
    frame.loc[frame.index[17:19], "Market_Structure"] = recovery_structure
    return frame


def _run_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return _compute_ampel_frame(frame.copy())


def _simple_public_bars() -> list[TrendAmpelBar]:
    bars: list[TrendAmpelBar] = []
    previous = 100.0
    for index in range(80):
        close = 100.0 + index * 0.1
        bars.append(
            TrendAmpelBar(
                date=date(2026, 1, 2) + timedelta(days=index),
                open=previous,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000 + index * 1_000,
            )
        )
        previous = close
    return bars


def _zigzag_bars() -> list[TrendAmpelBar]:
    closes = [100.0] * 22 + [100, 103, 106, 109, 105, 101, 105, 109, 113, 109, 105, 109, 113, 117, 113, 109, 113, 117, 121]
    bars: list[TrendAmpelBar] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        bars.append(
            TrendAmpelBar(
                date=date(2026, 1, 2) + timedelta(days=index),
                open=previous,
                high=float(close) + 1.0,
                low=float(close) - 1.0,
                close=float(close),
                volume=1_000_000,
            )
        )
        previous = float(close)
    return bars
