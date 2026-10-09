from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

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


def test_ibd_logic_allows_startschuss_on_rally_day_four() -> None:
    frame = _book_frame(confirm_green=None)
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = frame["Close"].diff().fillna(0.0) >= 0
    # Correction on row 1, Rally Day 1 / anchor on row 2, eligible FTD on row 5.
    frame.loc[frame.index[5], "Pct_Change"] = 1.2
    frame.loc[frame.index[5], "Volume"] = 1_200_000.0

    result = _compute_ampel_frame(frame.copy(), logic="ibd")

    assert result.iloc[4]["Ampel_Phase"] == "rot"
    assert result.iloc[5]["Ampel_Phase"] == "gelb_startschuss"
    assert result.iloc[5]["Anchor_Date"] == frame.index[2].strftime("%Y-%m-%d")


def test_ibd_logic_detects_smaller_correction_while_current_logic_stays_neutral() -> None:
    frame = _book_frame(confirm_green=None)
    frame.loc[frame.index[1], ["Open", "High", "Low", "Close"]] = [98.0, 98.2, 96.0, 96.5]
    frame.loc[frame.index[1], "Pct_Change"] = -3.5
    frame.loc[frame.index[1], "SMA50"] = 97.0
    frame.loc[frame.index[1], "Dist_Count_25"] = 0
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = frame["Close"].diff().fillna(0.0) >= 0

    current = _compute_ampel_frame(frame.copy(), logic="current")
    ibd = _compute_ampel_frame(frame.copy(), logic="ibd")

    assert current.iloc[1]["Ampel_Phase"] == "neutral"
    assert ibd.iloc[1]["Ampel_Phase"] == "rot"


def test_ibd_startschuss_low_can_be_negated_while_rally_day_one_low_holds() -> None:
    frame = _book_frame(confirm_green=None)
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = frame["Close"].diff().fillna(0.0) >= 0
    frame.loc[frame.index[5], "Pct_Change"] = 1.2
    frame.loc[frame.index[5], "Volume"] = 1_200_000.0
    # FTD low is 90.1, Rally-Day-1 low is 89.5.
    frame.loc[frame.index[6], ["Open", "High", "Low", "Close"]] = [90.2, 90.3, 89.7, 89.9]

    result = _compute_ampel_frame(frame.copy(), logic="ibd")

    assert result.iloc[5]["Ampel_Phase"] == "gelb_startschuss"
    assert result.iloc[6]["Ampel_Phase"] == "gelb_rally_unter_druck"
    assert bool(result.iloc[6]["FTD_Negated"]) is True
    assert result.iloc[6]["Anchor_Date"] == frame.index[2].strftime("%Y-%m-%d")
    assert result.iloc[6]["Floor_Mark"] == pytest.approx(89.5)
    assert result.iloc[6]["Startschuss_Low"] == pytest.approx(90.1)


def test_ibd_rally_day_one_low_break_ends_rally_attempt() -> None:
    frame = _book_frame(confirm_green=None)
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = frame["Close"].diff().fillna(0.0) >= 0
    frame.loc[frame.index[5], "Pct_Change"] = 1.2
    frame.loc[frame.index[5], "Volume"] = 1_200_000.0
    frame.loc[frame.index[6], ["Open", "High", "Low", "Close"]] = [90.0, 90.1, 89.0, 89.4]

    result = _compute_ampel_frame(frame.copy(), logic="ibd")

    assert result.iloc[6]["Ampel_Phase"] == "rot"
    assert pd.isna(result.iloc[6]["Anchor_Date"])
    assert pd.isna(result.iloc[6]["Floor_Mark"])
    assert bool(result.iloc[6]["FTD_Negated"]) is False


def test_ibd_powertrend_activates_on_10_5_rule_and_ends_on_negative_cross() -> None:
    frame = _book_frame(confirm_green=None)
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = False
    activation = frame.index[13]
    frame.loc[activation, "Consec_Low_above_21"] = 10
    frame.loc[activation, "Consec_EMA21_Above_SMA50"] = 5
    frame.loc[activation, "SMA50_Rising_1D"] = True
    frame.loc[activation, "Positive_Or_Flat_Day"] = True
    frame.loc[activation, "EMA21"] = 92.0
    frame.loc[activation, "SMA50"] = 90.0

    end = frame.index[14]
    frame.loc[end, "EMA21"] = 89.0
    frame.loc[end, "SMA50"] = 90.0

    result = _compute_ampel_frame(frame.copy(), logic="ibd")

    assert result.loc[activation, "PowerTrend_State"] == "on"
    assert bool(result.loc[activation, "PowerTrend_Formally_Active"]) is True
    assert result.loc[end, "PowerTrend_State"] == "off"
    assert bool(result.loc[end, "PowerTrend_Formally_Active"]) is False


def test_ibd_powertrend_needs_positive_or_flat_activation_day() -> None:
    frame = _book_frame(confirm_green=None)
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = False
    row = frame.index[13]
    frame.loc[row, "Consec_Low_above_21"] = 10
    frame.loc[row, "Consec_EMA21_Above_SMA50"] = 5
    frame.loc[row, "SMA50_Rising_1D"] = True
    frame.loc[row, "Positive_Or_Flat_Day"] = False
    frame.loc[row, "EMA21"] = 92.0
    frame.loc[row, "SMA50"] = 90.0

    result = _compute_ampel_frame(frame.copy(), logic="ibd")

    assert result.loc[row, "PowerTrend_State"] == "off"


@pytest.mark.parametrize("confirm", [None, "ema21", "uptrend"])
def test_ibd_ftd_intraday_undercut_warns_without_negation(confirm) -> None:
    frame = _uptrend_ready_frame() if confirm == "uptrend" else _book_frame(confirm_green=confirm)
    break_index = 14 if confirm == "uptrend" else 11 if confirm else 8
    ftd_low = float(frame.iloc[7]["Low"])
    frame.loc[frame.index[break_index], "Low"] = ftd_low - 0.1
    result = _compute_ampel_frame(frame.copy(), logic="ibd")
    row = result.iloc[break_index]
    assert row["Close"] > ftd_low
    assert not bool(row["FTD_Negated"])
    assert bool(row["FTD_Intraday_Undercut"])
    assert row["Anchor_Date"] == frame.index[2].strftime("%Y-%m-%d")
    assert row["Ampel_Phase"] == ("aufwaertstrend" if confirm == "uptrend" else "gruen" if confirm else "gelb_startschuss")
    # The existing variant deliberately still uses the close.
    assert not bool(_compute_ampel_frame(frame.copy()).iloc[break_index]["FTD_Negated"])


def test_ibd_negated_ftd_does_not_repeat_after_pressure_recovery_to_green() -> None:
    frame = _uptrend_ready_frame()
    frame.loc[frame.index[14], ["Low", "Close"]] = [float(frame.iloc[7]["Low"]) - 0.2, float(frame.iloc[7]["Low"]) - 0.1]
    frame.loc[frame.index[15:19], "MA_Order"] = True
    frame.loc[frame.index[15:19], "Market_Structure"] = "mixed"
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[14]["Ampel_Phase"] == "gelb_trend_unter_druck"
    assert result.iloc[16]["Ampel_Phase"] == "gruen"
    assert bool(result.iloc[16]["FTD_Negated"])
    frame.loc[frame.index[17], ["Low", "Close"]] = [89.9, 90.0]
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[17]["Ampel_Phase"] == "gruen"
    assert bool(result.iloc[17]["FTD_Negated"])


@pytest.mark.parametrize("under_pressure", [False, True])
@pytest.mark.parametrize("risk_exit", ["sma200", "drawdown", "distribution", "structure"])
def test_ibd_new_correction_ends_completed_cycle_and_restarts_rally_clock(under_pressure, risk_exit) -> None:
    frame = _uptrend_ready_frame()
    exit_index = 15 if under_pressure else 14
    if under_pressure:
        frame.loc[frame.index[14], "Consec_Close_Below_21"] = 3
    exit_row = frame.index[exit_index]
    if risk_exit == "sma200":
        frame.loc[exit_row, "SMA200"] = 100.0
    elif risk_exit == "drawdown":
        frame.loc[exit_row, "High"] = 110.0
    elif risk_exit == "distribution":
        frame.loc[exit_row, ["SMA50", "Dist_Count_25"]] = [100.0, 4]
    else:
        frame.loc[exit_row, "Market_Structure"] = "down"
    # Neither the old Rally-Day-1 low nor the FTD low was broken.
    frame.loc[frame.index[exit_index + 2], ["Pct_Change", "Volume"]] = [1.2, 1_300_000]
    frame.loc[frame.index[exit_index + 4], ["Pct_Change", "Volume"]] = [1.2, 1_400_000]
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[exit_index - 1]["Ampel_Phase"] == (
        "gelb_trend_unter_druck" if under_pressure else "aufwaertstrend"
    )
    assert result.iloc[exit_index]["Ampel_Phase"] == "rot"
    assert pd.isna(result.iloc[exit_index]["Anchor_Date"])
    assert pd.isna(result.iloc[exit_index]["Floor_Mark"])
    assert pd.isna(result.iloc[exit_index]["Startschuss_Low"])
    assert not bool(result.iloc[exit_index]["FTD_Negated"])
    assert result.iloc[exit_index + 1]["Anchor_Date"] == frame.index[exit_index + 1].strftime("%Y-%m-%d")
    assert result.iloc[exit_index + 2]["Ampel_Phase"] == "rot"
    assert result.iloc[exit_index + 4]["Ampel_Phase"] == "gelb_startschuss"


def test_ibd_display_does_not_mix_markers_from_completed_and_new_cycles() -> None:
    from app.domain.market.ampel import _trend_ampel_point
    from app.services.market import _last_cycle_markers

    frame = _uptrend_ready_frame()
    frame.loc[frame.index[14], "SMA200"] = 100.0
    result = _compute_ampel_frame(frame, logic="ibd")
    points = [_trend_ampel_point(index, row) for index, row in result.iterrows()]
    assert points[13].startschuss_low is not None
    assert _last_cycle_markers(points[:15], points[14]) == (None, None, None)
    assert _last_cycle_markers(points[:16], points[15]) == (
        points[15].anchor_date, points[15].floor_mark, None,
    )


def test_ibd_display_keeps_negated_ftd_reference_within_same_rally_attempt() -> None:
    from app.domain.market.ampel import _trend_ampel_point
    from app.services.market import _last_cycle_markers

    frame = _book_frame(confirm_green=None)
    frame.loc[frame.index[8], ["Low", "Close"]] = [float(frame.iloc[7]["Low"]) - 0.2, float(frame.iloc[7]["Low"]) - 0.1]
    result = _compute_ampel_frame(frame, logic="ibd")
    points = [_trend_ampel_point(index, row) for index, row in result.iloc[:9].iterrows()]
    assert points[-1].ftd_negated
    assert _last_cycle_markers(points, points[-1]) == (
        points[-1].anchor_date, points[-1].floor_mark, points[7].startschuss_low,
    )


def test_ibd_new_ftd_reuses_rally_and_clears_negation() -> None:
    frame = _book_frame(confirm_green=None)
    frame.loc[frame.index[8], ["Low", "Close"]] = [float(frame.iloc[7]["Low"]) - 0.2, float(frame.iloc[7]["Low"]) - 0.1]
    frame.loc[frame.index[9], ["Pct_Change", "Volume"]] = [1.2, 1_300_000]
    result = _compute_ampel_frame(frame, logic="ibd")
    assert bool(result.iloc[8]["FTD_Negated"])
    assert result.iloc[9]["Ampel_Phase"] == "gelb_startschuss"
    assert not bool(result.iloc[9]["FTD_Negated"])
    assert result.iloc[9]["Anchor_Date"] == frame.index[2].strftime("%Y-%m-%d")


def test_powertrend_stays_active_with_lost_start_conditions_and_equal_averages() -> None:
    frame = _book_frame(confirm_green=None)
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = False
    frame.loc[frame.index[13], ["Consec_Low_above_21", "Consec_EMA21_Above_SMA50"]] = [10, 5]
    frame.loc[frame.index[13], ["SMA50_Rising_1D", "Positive_Or_Flat_Day"]] = True
    frame.loc[frame.index[13:], ["EMA21", "SMA50"]] = [92.0, 90.0]
    frame.loc[frame.index[14], "SMA50"] = 92.0
    frame.loc[frame.index[15], ["Close", "Consec_Close_Below_21"]] = [90.0, 3]
    result = _compute_ampel_frame(frame, logic="ibd")
    start = frame.index[13].strftime("%Y-%m-%d")
    assert result.iloc[14]["PowerTrend_State"] == "on"
    assert result.iloc[15]["PowerTrend_State"] == "under_pressure"
    assert result.iloc[16]["PowerTrend_State"] == "under_pressure"
    assert result.iloc[16]["PowerTrend_Start_Date"] == start
    assert all(result.iloc[13:17]["PowerTrend_Formally_Active"])


def test_powertrend_real_bars_use_low_and_consecutive_trading_sessions() -> None:
    from dataclasses import replace
    bars = _simple_public_bars()
    bars = [replace(bar, open=bar.close - 0.025, low=bar.close - 0.05) for bar in bars]
    points = compute_trend_ampel(bars, logic="ibd")
    assert points[-1].powertrend_formally_active
    # Touching EMA breaks the low streak although the close remains above it.
    bars[-1] = replace(bars[-1], low=points[-1].ema21)
    touched = compute_trend_ampel(bars, logic="ibd")[-1]
    assert touched.powertrend_low_above_21_streak == 0
    assert touched.powertrend_formally_active


@pytest.mark.parametrize("missing_field", ["open", "high", "low"])
def test_ibd_missing_ohlc_cannot_activate_powertrend(missing_field) -> None:
    from dataclasses import asdict

    bars = [asdict(bar) for bar in _simple_public_bars()]
    for bar in bars:
        bar[missing_field] = None
    points = compute_trend_ampel(bars, logic="ibd")
    assert not any(point.powertrend_formally_active for point in points)
    assert points[-1].powertrend_low_above_21_streak == 0
    assert not points[-1].price_data_complete


def test_ibd_incomplete_repository_candle_breaks_low_streak() -> None:
    from dataclasses import replace

    bars = [replace(bar, open=bar.close, low=bar.close - 0.05) for bar in _simple_public_bars()]
    baseline = compute_trend_ampel(bars, logic="ibd")
    assert baseline[-1].powertrend_formally_active
    bars[-1] = replace(bars[-1], ohlc_complete=False)
    point = compute_trend_ampel(bars, logic="ibd")[-1]
    assert point.powertrend_low_above_21_streak == 0
    assert not point.price_data_complete
    assert point.low is None
    # A data gap does not invent a formal exit from an already known Powertrend.
    assert point.powertrend_formally_active


def test_ibd_invalid_low_is_not_a_confirmed_candle() -> None:
    from dataclasses import replace

    bars = [replace(bar, low=bar.close + 0.5) for bar in _simple_public_bars()]
    points = compute_trend_ampel(bars, logic="ibd")
    assert not any(point.powertrend_formally_active for point in points)
    assert not points[-1].price_data_complete


def test_negated_ftd_stays_negated_in_green_hero_and_cycle() -> None:
    from app.domain.market.ampel import _trend_ampel_point
    from app.services.market import _ampel_cycle, _ampel_reason_line, _last_cycle_markers

    frame = _uptrend_ready_frame()
    frame.loc[frame.index[14], ["Low", "Close"]] = [float(frame.iloc[7]["Low"]) - 0.2, float(frame.iloc[7]["Low"]) - 0.1]
    frame.loc[frame.index[15:19], "Market_Structure"] = "mixed"
    result = _compute_ampel_frame(frame, logic="ibd")
    points = [_trend_ampel_point(index, row) for index, row in result.iloc[:17].iterrows()]
    latest = points[-1]
    assert latest.phase == "gruen" and latest.ftd_negated
    anchor, floor, ftd = _last_cycle_markers(points, latest)
    cycle = _ampel_cycle(latest, anchor_date=anchor, floor_mark=floor, startschuss_low=ftd)
    hero = _ampel_reason_line(latest, anchor_date=anchor, floor_mark=floor, startschuss_low=ftd)
    assert not cycle.startschuss_current
    assert "negiert" in hero
    assert "Startschuss bestätigt" not in hero
    assert "Absicherung" not in hero


@pytest.mark.parametrize("expected_phase,activation", [("rot", 6), ("gelb_startschuss", 7), ("gruen", 11)])
def test_powertrend_activation_is_independent_of_market_phase(expected_phase, activation):
    frame = _book_frame(confirm_green="ema21" if expected_phase == "gruen" else None)
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = False
    row = frame.index[activation]
    frame.loc[row, ["Consec_Low_above_21", "Consec_EMA21_Above_SMA50"]] = [10, 5]
    frame.loc[row, ["SMA50_Rising_1D", "Positive_Or_Flat_Day"]] = True
    if expected_phase != "gruen":
        # Keep this unit frame's precomputed MA series consistent with activation.
        frame.loc[row, ["EMA21", "SMA50"]] = [92, 90]
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.loc[row, "Ampel_Phase"] == expected_phase
    assert result.loc[row, "PowerTrend_State"] == "on"
    assert result.loc[row, "PowerTrend_Start_Date"] == row.strftime("%Y-%m-%d")


def test_market_pressure_and_red_do_not_pressure_an_active_powertrend():
    frame = _uptrend_ready_frame()
    frame["Consec_EMA21_Above_SMA50"] = 0
    frame["SMA50_Rising_1D"] = False
    frame["Positive_Or_Flat_Day"] = False
    frame.loc[frame.index[13], ["Consec_Low_above_21", "Consec_EMA21_Above_SMA50"]] = [10, 5]
    frame.loc[frame.index[13], ["SMA50_Rising_1D", "Positive_Or_Flat_Day"]] = True
    frame.loc[frame.index[14], "Phase_Warning_Streak"] = 2
    frame.loc[frame.index[15], "Market_Structure"] = "down"
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[14]["Ampel_Phase"] == "gelb_trend_unter_druck"
    assert result.iloc[15]["Ampel_Phase"] == "rot"
    assert all(result.iloc[13:16]["PowerTrend_State"] == "on")


def _powertrend_recovery_frame(pressure_signal):
    frame = _book_frame(confirm_green=None)
    # Extend a complete confirmed daily frame for the recovery sequence.
    extension = pd.concat([frame.iloc[[-1]]] * 12, ignore_index=True)
    extension.index = pd.bdate_range(frame.index[-1] + pd.Timedelta(days=1), periods=12)
    frame = pd.concat([frame, extension])
    frame["Consec_Low_above_21"] = 0
    frame["Consec_EMA21_Above_SMA50"] = 5
    frame["SMA50_Rising_1D"] = True
    frame["Positive_Or_Flat_Day"] = True
    frame.loc[frame.index[13]:, ["EMA21", "SMA50", "ATR21"]] = [92, 90, 2]
    frame.loc[frame.index[13], "Consec_Low_above_21"] = 10
    if pressure_signal == "three_below":
        frame.loc[frame.index[14], ["Close", "Consec_Close_Below_21"]] = [91, 3]
    else:
        frame.loc[frame.index[14], "Close"] = 88.9
    for progress in range(1, 11):
        frame.loc[frame.index[14 + progress], ["Close", "Consec_Low_above_21", "Consec_Close_Below_21"]] = [96, progress, 0]
    frame.loc[frame.index[25], "EMA21"] = 89
    frame.loc[frame.index[25], "Consec_Low_above_21"] = 0
    return frame


@pytest.mark.parametrize("pressure_signal", ["three_below", "strong_50_break"])
def test_powertrend_pressure_persists_until_full_requalification(pressure_signal):
    frame = _powertrend_recovery_frame(pressure_signal)
    result = _compute_ampel_frame(frame, logic="ibd")
    start = frame.index[13].strftime("%Y-%m-%d")
    pressure = frame.index[14].strftime("%Y-%m-%d")
    assert all(result.iloc[14:24]["PowerTrend_State"] == "under_pressure")
    assert all(result.iloc[14:24]["PowerTrend_Pressure_Since"] == pressure)
    assert all(result.iloc[13:25]["PowerTrend_Start_Date"] == start)
    assert all(result.iloc[13:25]["PowerTrend_Formally_Active"])
    assert result.iloc[24]["PowerTrend_State"] == "on"
    assert pd.isna(result.iloc[24]["PowerTrend_Pressure_Since"])
    assert result.iloc[25]["PowerTrend_State"] == "off"
    assert not result.iloc[25]["PowerTrend_Formally_Active"]
    assert pd.isna(result.iloc[25]["PowerTrend_Start_Date"])
    assert pd.isna(result.iloc[25]["PowerTrend_Pressure_Since"])
    # After a formal end, a fresh activation needs all four criteria and a new date.
    frame.loc[frame.index[26]:, "EMA21"] = 92
    frame.loc[frame.index[26], "Consec_Low_above_21"] = 1
    frame.loc[frame.index[27], "Consec_Low_above_21"] = 10
    restarted = _compute_ampel_frame(frame, logic="ibd")
    assert restarted.iloc[26]["PowerTrend_State"] == "off"
    assert restarted.iloc[27]["PowerTrend_State"] == "on"
    assert restarted.iloc[27]["PowerTrend_Start_Date"] == frame.index[27].strftime("%Y-%m-%d")



def test_sp500_august_2026_powertrend_survives_pressure_and_replay():
    import json
    from pathlib import Path
    from app.services.market import _powertrend_response, _trend_ampel_metrics
    from app.schemas import MarketTrendAmpel

    fixture = json.loads((Path(__file__).parents[2] / "fixtures/market/powertrend/sp500_2026.json").read_text())
    points = compute_trend_ampel(fixture["bars"], logic="ibd")
    by_date = {point.date: point for point in points}
    assert by_date["2026-08-18"].powertrend_state == "off"
    assert by_date["2026-08-19"].powertrend_state == "on"
    assert by_date["2026-08-20"].phase == "gelb_trend_unter_druck"
    assert by_date["2026-08-20"].powertrend_state == "on"
    assert by_date["2026-09-10"].powertrend_state == "under_pressure"
    assert by_date["2026-09-21"].powertrend_low_above_21_streak == 1
    assert by_date["2026-09-21"].powertrend_state == "under_pressure"
    assert all(point.powertrend_start_date == "2026-08-19" for point in points if point.date >= "2026-08-19")
    latest = points[-1]
    assert latest.powertrend_pressure_since == "2026-09-10"
    # API and JSON persisted metrics retain both dates; rebuilding after a restart does too.
    api = _powertrend_response(latest, enabled=True)
    assert api.start_date == "2026-08-19"
    assert api.pressure_since == "2026-09-10"
    stored = MarketTrendAmpel.model_validate(_trend_ampel_metrics(latest, ticker="^GSPC"))
    restored = MarketTrendAmpel.model_validate_json(stored.model_dump_json())
    assert restored.powertrend_pressure_since == "2026-09-10"
    assert restored.powertrend_start_date == "2026-08-19"
    assert compute_trend_ampel(fixture["bars"], logic="ibd")[-1] == latest


@pytest.mark.parametrize("column,value", [
    ("Consec_Low_above_21", 9), ("Consec_EMA21_Above_SMA50", 4),
    ("SMA50_Rising_1D", False), ("Positive_Or_Flat_Day", False),
])
def test_powertrend_recovery_requires_all_four_conditions(column, value):
    frame = _powertrend_recovery_frame("three_below")
    frame.loc[frame.index[24], column] = value
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[24]["PowerTrend_State"] == "under_pressure"
    assert result.iloc[24]["PowerTrend_Start_Date"] == frame.index[13].strftime("%Y-%m-%d")


def test_powertrend_does_not_transition_on_incomplete_daily_prices():
    frame = _powertrend_recovery_frame("three_below")
    frame["OHLC_Complete"] = True
    frame.loc[frame.index[14], "OHLC_Complete"] = False
    frame.loc[frame.index[14], "EMA21"] = 89
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[14]["PowerTrend_State"] == "on"
    assert result.iloc[14]["PowerTrend_Start_Date"] == frame.index[13].strftime("%Y-%m-%d")


@pytest.mark.parametrize("confirm,break_index", [(None, 8), ("ema21", 11), ("uptrend", 14)])
def test_ibd_close_negation_preserves_rally_and_ftd_history(confirm, break_index):
    frame = _uptrend_ready_frame() if confirm == "uptrend" else _book_frame(confirm_green=confirm)
    ftd_low = float(frame.iloc[7]["Low"])
    frame.loc[frame.index[break_index], ["Low", "Close"]] = [ftd_low - .2, ftd_low - .1]
    result = _compute_ampel_frame(frame, logic="ibd")
    row = result.iloc[break_index]
    assert row["Ampel_Phase"] == ("gelb_trend_unter_druck" if confirm == "uptrend" else "gelb_rally_unter_druck")
    assert row["FTD_Negated"]
    assert row["Startschuss_Date"] == frame.index[7].strftime("%Y-%m-%d")
    assert row["Startschuss_Low"] == ftd_low
    assert row["Anchor_Date"] == result.iloc[7]["Anchor_Date"]
    assert row["Floor_Mark"] == result.iloc[7]["Floor_Mark"]


@pytest.mark.parametrize("exit_signal", ["floor", "distribution", "structure", "sma200", "drawdown"])
def test_ibd_rally_pressure_independent_red_priority(exit_signal):
    frame = _book_frame(confirm_green=None)
    ftd_low = float(frame.iloc[7]["Low"])
    frame.loc[frame.index[8], ["Low", "Close"]] = [ftd_low - .2, ftd_low - .1]
    row = frame.index[9]
    if exit_signal == "floor":
        frame.loc[row, "Low"] = 89.0
    elif exit_signal == "distribution":
        frame.loc[row, ["SMA50", "Dist_Count_25"]] = [100, 4]
    elif exit_signal == "structure":
        frame.loc[row, "Market_Structure"] = "down"
    elif exit_signal == "sma200":
        frame.loc[row, "SMA200"] = 100
    else:
        frame.loc[row, "High"] = 110
    # Even a qualifying FTD must not override a hard red signal.
    frame.loc[row, ["Pct_Change", "Volume"]] = [1.2, 1_400_000]
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[8]["Ampel_Phase"] == "gelb_rally_unter_druck"
    assert result.iloc[9]["Ampel_Phase"] == "rot"
    assert pd.isna(result.iloc[9]["Anchor_Date"])


def test_ibd_early_negation_cannot_recover_without_new_ftd():
    frame = _book_frame(confirm_green="ema21")
    frame.loc[frame.index[11], ["Low", "Close"]] = [90, 90.1]
    frame.loc[frame.index[12:], "Pct_Change"] = .5
    result = _compute_ampel_frame(frame, logic="ibd")
    assert set(result.iloc[11:]["Ampel_Phase"]) == {"gelb_rally_unter_druck"}
    assert result.iloc[11:]["FTD_Negated"].all()
    assert result.iloc[-1]["Startschuss_Date"] == frame.index[7].strftime("%Y-%m-%d")


def test_ibd_missing_candle_cannot_negate_or_confirm_replacement():
    frame = _book_frame(confirm_green=None)
    frame["OHLC_Complete"] = True
    frame.loc[frame.index[8], ["Low", "Close", "OHLC_Complete"]] = [89.7, 89.9, False]
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[8]["Ampel_Phase"] == "gelb_startschuss"
    assert not result.iloc[8]["FTD_Negated"]
    frame.loc[frame.index[8], "OHLC_Complete"] = True
    frame.loc[frame.index[9], ["Pct_Change", "Volume", "OHLC_Complete"]] = [1.2, 1_400_000, False]
    result = _compute_ampel_frame(frame, logic="ibd")
    assert result.iloc[9]["Ampel_Phase"] == "gelb_rally_unter_druck"
    assert result.iloc[9]["FTD_Negated"]
