from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.domain.market.regime import MarketPhase


GREEN_CONFIRMATION_DAYS = 3
ATR_PERIOD = 21
REVERSAL_ATR_MULTIPLIER = 1.5
PIVOT_TOLERANCE_ATR = 0.25

MarketStructure = Literal["up", "down", "mixed", "unknown"]


@dataclass(frozen=True)
class MarketSwingPoint:
    pivot_type: Literal["high", "low"]
    pivot_price: float
    pivot_date: str
    confirmation_date: str
    atr_at_pivot: float


@dataclass(frozen=True)
class TrendAmpelBar:
    date: date | str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class TrendAmpelPoint:
    date: str
    phase: MarketPhase
    close: float | None
    ema21: float | None
    sma50: float | None
    sma200: float | None
    pct_change: float | None
    closing_range: float | None
    dist_count_25: int
    anchor_date: str | None
    floor_mark: float | None
    startschuss_low: float | None
    startschuss_bonus: bool | None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    sma10: float | None = None
    atr21: float | None = None
    atr_pct: float | None = None
    vol_sma50: float | None = None
    dist_21ema: float | None = None
    dist_10sma_pct: float | None = None
    dist_50sma_pct: float | None = None
    dist_200sma_pct: float | None = None
    high_52w: float | None = None
    dist_52w_pct: float | None = None
    ma_order: bool | None = None
    low_above_21: bool | None = None
    low_above_50: bool | None = None
    low_above_200: bool | None = None
    consec_low_above_21: int = 0
    consec_low_above_50: int = 0
    consec_low_above_200: int = 0
    ema21_held: bool | None = None
    sma50_held: bool | None = None
    sma200_held: bool | None = None
    intraday_reversal_down: bool | None = None
    intraday_reversal_up: bool | None = None
    neg_reversals_10d: int = 0
    pos_reversals_10d: int = 0
    low_cr_5d: int = 0
    up_vol_declining: bool | None = None
    is_distribution: bool | None = None
    is_stall: bool | None = None
    loss_days_10d: int = 0
    gain_days_10d: int = 0
    loss_gain_ratio_10d: float | None = None
    startschuss_date: str | None = None
    uptrend_high: float | None = None
    market_structure: MarketStructure = "unknown"
    high_structure: Literal["higher", "lower", "equal", "unknown"] = "unknown"
    low_structure: Literal["higher", "lower", "equal", "unknown"] = "unknown"
    latest_swing_high: float | None = None
    latest_swing_high_date: str | None = None
    latest_swing_low: float | None = None
    latest_swing_low_date: str | None = None
    consecutive_closes_below_ema21: int = 0
    consecutive_closes_above_ema21: int = 0
    ma_order_streak: int = 0
    ema21_rising: bool | None = None
    sma50_rising: bool | None = None
    phase_warning_count: int = 0
    phase_warning_streak: int = 0
    green_below_sma200: bool = False
    phase_reason: str | None = None


def compute_trend_ampel(
    bars: Sequence[TrendAmpelBar | Mapping[str, Any]],
    *,
    over_50_warning_pct: float = 5.0,
) -> list[TrendAmpelPoint]:
    frame = _frame_from_bars(bars)
    if frame.empty:
        return []

    indicator_frame = add_trend_indicators(frame)
    distribution_frame = detect_distribution_days(indicator_frame)
    structure_frame, _swings = add_market_structure(distribution_frame)
    warning_frame = add_phase_warning_counts(
        structure_frame,
        over_50_warning_pct=over_50_warning_pct,
    )
    ampel_frame = _compute_ampel_frame(warning_frame)
    return [_trend_ampel_point(index, row) for index, row in ampel_frame.iterrows()]


def compute_atr_zigzag_swings(
    bars: Sequence[TrendAmpelBar | Mapping[str, Any]],
) -> list[MarketSwingPoint]:
    frame = _frame_from_bars(bars)
    if frame.empty:
        return []
    indicator_frame = add_trend_indicators(frame)
    _structure_frame, swings = add_market_structure(indicator_frame)
    return swings


def add_trend_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["EMA21"] = _ema(df["Close"], 21)
    df["SMA50"] = _sma(df["Close"], 50)
    df["SMA200"] = _sma(df["Close"], 200)
    df["SMA10"] = _sma(df["Close"], 10)
    df["ATR21"] = _atr(df, ATR_PERIOD)
    df["ATR_pct"] = df["ATR21"] / df["Close"] * 100
    df["Vol_SMA50"] = _sma(df["Volume"], 50)
    df["Pct_Change"] = pd.to_numeric(df["Close"], errors="coerce").ffill().pct_change(fill_method=None) * 100

    daily_range = df["High"] - df["Low"]
    df["Closing_Range"] = np.where(
        daily_range > 0,
        (df["Close"] - df["Low"]) / daily_range,
        0.5,
    )
    df["Dist_21EMA"] = (df["Close"] - df["EMA21"]) / df["ATR21"]
    df["Dist_50SMA_pct"] = (df["Close"] - df["SMA50"]) / df["SMA50"] * 100
    df["Dist_200SMA_pct"] = (df["Close"] - df["SMA200"]) / df["SMA200"] * 100
    df["Dist_10SMA_pct"] = (df["Close"] - df["SMA10"]) / df["SMA10"] * 100
    df["High_52w"] = df["High"].rolling(252, min_periods=1).max()
    df["Dist_52w_pct"] = (df["Close"] - df["High_52w"]) / df["High_52w"] * 100
    df["MA_Order"] = (df["EMA21"] > df["SMA50"]) & (df["SMA50"] > df["SMA200"])
    df["MA_Order_Streak"] = _consecutive_true(df["MA_Order"])
    df["Low_above_21"] = df["Low"] > df["EMA21"]
    df["Low_above_50"] = df["Low"] > df["SMA50"]
    df["Low_above_200"] = df["Low"] > df["SMA200"]
    df["Consec_Low_above_21"] = _consecutive_true(df["Low_above_21"])
    df["Consec_Low_above_50"] = _consecutive_true(df["Low_above_50"])
    df["Consec_Low_above_200"] = _consecutive_true(df["Low_above_200"])
    df["EMA21_held"] = df["Close"] > df["EMA21"]
    df["SMA50_held"] = df["Close"] > df["SMA50"]
    df["SMA200_held"] = df["Close"] > df["SMA200"]
    previous_close = df["Close"].shift(1)
    df["Intraday_Reversal_Down"] = (df["Open"] > previous_close) & (df["Close"] < df["Open"])
    df["Intraday_Reversal_Up"] = (df["Open"] < previous_close) & (df["Close"] > df["Open"])
    df["Neg_Reversals_10d"] = (
        df["Intraday_Reversal_Down"].rolling(10, min_periods=1).sum().fillna(0).astype(int)
    )
    df["Pos_Reversals_10d"] = (
        df["Intraday_Reversal_Up"].rolling(10, min_periods=1).sum().fillna(0).astype(int)
    )
    df["Low_CR"] = df["Closing_Range"] < 0.25
    df["Low_CR_5d"] = df["Low_CR"].rolling(5, min_periods=1).sum().fillna(0).astype(int)
    # Streamlit parity: warning is active when the 5-day average volume
    # difference is negative while price is higher than five sessions ago.
    df["Up_Vol_Declining"] = (df["Close"] > df["Close"].shift(5)) & (
        df["Volume"].diff().rolling(5, min_periods=5).mean() < 0
    )
    gain_day = df["Close"] > previous_close
    loss_day = df["Close"] < previous_close
    df["Gain_Days_10d"] = gain_day.rolling(10, min_periods=1).sum().fillna(0).astype(int)
    df["Loss_Days_10d"] = loss_day.rolling(10, min_periods=1).sum().fillna(0).astype(int)
    df["Loss_Gain_Ratio_10d"] = df["Loss_Days_10d"] / df["Gain_Days_10d"].clip(lower=1)
    df["Consec_Close_Above_21"] = _consecutive_true(df["Close"] > df["EMA21"])
    df["Consec_Close_Below_21"] = _consecutive_true(df["Close"] < df["EMA21"])
    df["EMA21_Rising"] = df["EMA21"] > df["EMA21"].shift(5)
    df["SMA50_Rising"] = df["SMA50"] > df["SMA50"].shift(10)
    return df


def detect_distribution_days(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    previous_close = df["Close"].shift(1)
    previous_volume = df["Volume"].shift(1)
    is_down = df["Close"] < previous_close
    high_volume = (df["Volume"] > previous_volume) | (df["Volume"] > df["Vol_SMA50"])
    df["Is_Distribution"] = (is_down & high_volume).fillna(False)
    df["Is_Stall"] = (
        (~is_down)
        & (df["Pct_Change"] < 0.5)
        & (df["Volume"] >= previous_volume * 0.95)
        & (df["Closing_Range"] < 0.5)
    ).fillna(False)
    df["Dist_Count_25"] = _count_active_distribution_days(df["Is_Distribution"], df["Close"], 25, 6.0)
    df["Stall_Count_10"] = df["Is_Stall"].rolling(10, min_periods=1).sum().fillna(0).astype(int)
    return df


def add_market_structure(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[MarketSwingPoint]]:
    df = frame.copy()
    row_count = len(df)
    structures: list[MarketStructure] = ["unknown"] * row_count
    high_structures = ["unknown"] * row_count
    low_structures = ["unknown"] * row_count
    latest_highs: list[float | None] = [None] * row_count
    latest_high_dates: list[str | None] = [None] * row_count
    latest_lows: list[float | None] = [None] * row_count
    latest_low_dates: list[str | None] = [None] * row_count

    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    close = df["Close"].to_numpy(dtype=float)
    atr = df["ATR21"].to_numpy(dtype=float)
    dates = [pd.Timestamp(value).strftime("%Y-%m-%d") for value in df.index]

    direction: Literal["unknown", "up", "down"] = "unknown"
    candidate_high: float | None = None
    candidate_high_index: int | None = None
    candidate_high_atr: float | None = None
    candidate_low: float | None = None
    candidate_low_index: int | None = None
    candidate_low_atr: float | None = None
    swings: list[MarketSwingPoint] = []
    confirmed_highs: list[MarketSwingPoint] = []
    confirmed_lows: list[MarketSwingPoint] = []

    def confirm(pivot_type: Literal["high", "low"], price: float, pivot_index: int, pivot_atr: float, index: int) -> None:
        point = MarketSwingPoint(
            pivot_type=pivot_type,
            pivot_price=float(price),
            pivot_date=dates[pivot_index],
            confirmation_date=dates[index],
            atr_at_pivot=float(pivot_atr),
        )
        swings.append(point)
        if pivot_type == "high":
            confirmed_highs.append(point)
        else:
            confirmed_lows.append(point)

    for index in range(row_count):
        if not _is_finite(atr[index]) or atr[index] <= 0:
            continue

        if candidate_high is None:
            candidate_high = float(high[index])
            candidate_high_index = index
            candidate_high_atr = float(atr[index])
            candidate_low = float(low[index])
            candidate_low_index = index
            candidate_low_atr = float(atr[index])
        elif direction == "unknown":
            if high[index] > candidate_high:
                candidate_high = float(high[index])
                candidate_high_index = index
                candidate_high_atr = float(atr[index])
            if candidate_low is None or low[index] < candidate_low:
                candidate_low = float(low[index])
                candidate_low_index = index
                candidate_low_atr = float(atr[index])

            up_confirmed = bool(
                candidate_low is not None
                and close[index] >= candidate_low + REVERSAL_ATR_MULTIPLIER * atr[index]
            )
            down_confirmed = bool(
                candidate_high is not None
                and close[index] <= candidate_high - REVERSAL_ATR_MULTIPLIER * atr[index]
            )
            if up_confirmed and down_confirmed:
                if candidate_low_index is not None and candidate_high_index is not None:
                    up_confirmed = candidate_low_index < candidate_high_index
                    down_confirmed = candidate_high_index < candidate_low_index

            if up_confirmed and candidate_low_index is not None and candidate_low_atr is not None:
                confirm("low", candidate_low, candidate_low_index, candidate_low_atr, index)
                direction = "up"
                candidate_high = float(high[index])
                candidate_high_index = index
                candidate_high_atr = float(atr[index])
            elif down_confirmed and candidate_high_index is not None and candidate_high_atr is not None:
                confirm("high", candidate_high, candidate_high_index, candidate_high_atr, index)
                direction = "down"
                candidate_low = float(low[index])
                candidate_low_index = index
                candidate_low_atr = float(atr[index])
        elif direction == "up":
            if candidate_high is None or high[index] > candidate_high:
                candidate_high = float(high[index])
                candidate_high_index = index
                candidate_high_atr = float(atr[index])
            if (
                candidate_high is not None
                and candidate_high_index is not None
                and candidate_high_atr is not None
                and close[index] <= candidate_high - REVERSAL_ATR_MULTIPLIER * atr[index]
            ):
                confirm("high", candidate_high, candidate_high_index, candidate_high_atr, index)
                direction = "down"
                candidate_low = float(low[index])
                candidate_low_index = index
                candidate_low_atr = float(atr[index])
        else:
            if candidate_low is None or low[index] < candidate_low:
                candidate_low = float(low[index])
                candidate_low_index = index
                candidate_low_atr = float(atr[index])
            if (
                candidate_low is not None
                and candidate_low_index is not None
                and candidate_low_atr is not None
                and close[index] >= candidate_low + REVERSAL_ATR_MULTIPLIER * atr[index]
            ):
                confirm("low", candidate_low, candidate_low_index, candidate_low_atr, index)
                direction = "up"
                candidate_high = float(high[index])
                candidate_high_index = index
                candidate_high_atr = float(atr[index])

        high_structure = _swing_structure(confirmed_highs)
        low_structure = _swing_structure(confirmed_lows)
        structure: MarketStructure = "unknown"
        if high_structure != "unknown" and low_structure != "unknown":
            if high_structure == "higher" and low_structure == "higher":
                structure = "up"
            elif high_structure == "lower" and low_structure == "lower":
                structure = "down"
            else:
                structure = "mixed"
        structures[index] = structure
        high_structures[index] = high_structure
        low_structures[index] = low_structure
        if confirmed_highs:
            latest_highs[index] = confirmed_highs[-1].pivot_price
            latest_high_dates[index] = confirmed_highs[-1].pivot_date
        if confirmed_lows:
            latest_lows[index] = confirmed_lows[-1].pivot_price
            latest_low_dates[index] = confirmed_lows[-1].pivot_date

    df["Market_Structure"] = structures
    df["High_Structure"] = high_structures
    df["Low_Structure"] = low_structures
    df["Latest_Swing_High"] = latest_highs
    df["Latest_Swing_High_Date"] = latest_high_dates
    df["Latest_Swing_Low"] = latest_lows
    df["Latest_Swing_Low_Date"] = latest_low_dates
    return df, swings


def _swing_structure(
    swings: Sequence[MarketSwingPoint],
) -> Literal["higher", "lower", "equal", "unknown"]:
    if len(swings) < 2:
        return "unknown"
    previous, latest = swings[-2], swings[-1]
    tolerance = PIVOT_TOLERANCE_ATR * latest.atr_at_pivot
    if latest.pivot_price > previous.pivot_price + tolerance:
        return "higher"
    if latest.pivot_price < previous.pivot_price - tolerance:
        return "lower"
    return "equal"


def add_phase_warning_counts(
    frame: pd.DataFrame,
    *,
    over_50_warning_pct: float,
) -> pd.DataFrame:
    df = frame.copy()
    warning_columns = pd.DataFrame(
        {
            "negative_reversals": df["Neg_Reversals_10d"] >= 3,
            "weak_closes": df["Low_CR_5d"] >= 3,
            "stall_days": df["Stall_Count_10"] >= 3,
            "distribution": df["Dist_Count_25"] >= 4,
            "loss_days": df["Loss_Days_10d"] > df["Gain_Days_10d"],
            "overextended_50": df["Dist_50SMA_pct"] > float(over_50_warning_pct),
            "below_21": df["Close"] < df["EMA21"],
            "overextended_21": df["Dist_21EMA"] > 3.0,
            "below_50": df["Close"] < df["SMA50"],
            "below_200": df["Close"] < df["SMA200"],
            "declining_up_volume": df["Up_Vol_Declining"],
        },
        index=df.index,
    ).fillna(False)
    df["Phase_Warning_Count"] = warning_columns.astype(int).sum(axis=1)
    df["Phase_Warning_Streak"] = _consecutive_true(df["Phase_Warning_Count"] >= 4)
    return df


def _compute_ampel_frame(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    row_count = len(df)
    phase: MarketPhase = "neutral"
    anchor_idx: int | None = None
    floor_mark: float | None = None
    startschuss_idx: int | None = None
    startschuss_low: float | None = None
    startschuss_date: str | None = None
    startschuss_bonus: bool | None = None
    demand_confirmed = False
    closes_above_21_since_start = 0
    pressure_closes_above_21 = 0
    uptrend_high: float | None = None
    uptrend_structure_low: float | None = None

    phases: list[MarketPhase] = ["neutral"] * row_count
    anchor_dates: list[str | None] = [None] * row_count
    floor_marks: list[float | None] = [None] * row_count
    startschuss_lows: list[float | None] = [None] * row_count
    startschuss_dates: list[str | None] = [None] * row_count
    startschuss_bonuses: list[bool | None] = [None] * row_count
    uptrend_highs: list[float | None] = [None] * row_count
    green_below_sma200: list[bool] = [False] * row_count
    phase_reasons: list[str | None] = [None] * row_count

    close = df["Close"].to_numpy(dtype=float)
    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    volume = df["Volume"].to_numpy(dtype=float)
    pct_change = df["Pct_Change"].to_numpy(dtype=float)
    closing_range = df["Closing_Range"].to_numpy(dtype=float)
    dist_count_25 = df["Dist_Count_25"].to_numpy(dtype=float)
    sma50 = df["SMA50"].to_numpy(dtype=float)
    sma200 = df["SMA200"].to_numpy(dtype=float)
    ema21 = df["EMA21"].to_numpy(dtype=float)
    atr21 = df["ATR21"].to_numpy(dtype=float)
    vol_sma50 = df["Vol_SMA50"].to_numpy(dtype=float)
    consec_low_above_21 = df["Consec_Low_above_21"].to_numpy(dtype=int)
    consec_low_above_50 = df["Consec_Low_above_50"].to_numpy(dtype=int)
    consec_close_below_21 = df["Consec_Close_Below_21"].to_numpy(dtype=int)
    ma_order_streak = df["MA_Order_Streak"].to_numpy(dtype=int)
    ema21_rising = df["EMA21_Rising"].fillna(False).to_numpy(dtype=bool)
    sma50_rising = df["SMA50_Rising"].fillna(False).to_numpy(dtype=bool)
    market_structure = df["Market_Structure"].astype(str).to_numpy()
    latest_swing_low = df["Latest_Swing_Low"].to_numpy(dtype=float)
    phase_warning_streak = df["Phase_Warning_Streak"].to_numpy(dtype=int)
    dates = [pd.Timestamp(value).strftime("%Y-%m-%d") for value in df.index]

    def clear_state() -> None:
        nonlocal anchor_idx, floor_mark, startschuss_idx, startschuss_low, startschuss_date
        nonlocal startschuss_bonus, demand_confirmed, closes_above_21_since_start
        nonlocal pressure_closes_above_21, uptrend_high, uptrend_structure_low
        anchor_idx = None
        floor_mark = None
        startschuss_idx = None
        startschuss_low = None
        startschuss_date = None
        startschuss_bonus = None
        demand_confirmed = False
        closes_above_21_since_start = 0
        pressure_closes_above_21 = 0
        uptrend_high = None
        uptrend_structure_low = None

    def correction_detected(index: int) -> bool:
        lookback = max(0, index - 60)
        recent_high = np.nanmax(high[lookback : index + 1])
        if not np.isfinite(recent_high) or recent_high <= 0:
            return False
        drawdown_pct = (close[index] - recent_high) / recent_high * 100
        below_sma50_with_distribution = (
            _is_finite(sma50[index]) and close[index] < sma50[index] and dist_count_25[index] >= 4
        )
        return drawdown_pct <= -10 or below_sma50_with_distribution

    def uptrend_confirmed(index: int) -> bool:
        return bool(
            _is_finite(close[index])
            and _is_finite(ema21[index])
            and _is_finite(sma50[index])
            and _is_finite(sma200[index])
            and close[index] > ema21[index]
            and close[index] > sma200[index]
            and consec_low_above_21[index] >= 3
            and consec_low_above_50[index] >= 3
            and ma_order_streak[index] >= 3
            and ema21_rising[index]
            and sma50_rising[index]
            and market_structure[index] == "up"
        )

    def startschuss_low_broken(index: int) -> bool:
        return startschuss_low is not None and close[index] < startschuss_low

    def update_uptrend_reference(index: int) -> None:
        nonlocal uptrend_high, uptrend_structure_low
        if uptrend_high is None or high[index] > uptrend_high:
            uptrend_high = float(high[index])
        if market_structure[index] == "up" and _is_finite(latest_swing_low[index]):
            uptrend_structure_low = float(latest_swing_low[index])

    def uptrend_hard_red(index: int) -> str | None:
        if startschuss_low_broken(index):
            return "Schlusskurs unter Startschuss-Tief"
        if _is_finite(sma200[index]) and close[index] < sma200[index]:
            return "Schlusskurs unter 200-SMA"
        if uptrend_high is not None and close[index] <= uptrend_high * 0.90:
            return "Mindestens 10% Drawdown seit Aufwärtstrend-Hoch"
        if _is_finite(sma50[index]) and close[index] < sma50[index] and dist_count_25[index] >= 4:
            return "50-SMA-Bruch bei mindestens vier Distributionstagen"
        if market_structure[index] == "down":
            return "Bestätigtes tieferes Swing-Hoch und tieferes Swing-Tief"
        return None

    def uptrend_pressure_reason(index: int) -> str | None:
        if consec_close_below_21[index] >= 3:
            return "Drei Schlusskurse in Folge unter der 21-EMA"
        strong_50_break = bool(
            _is_finite(sma50[index])
            and _is_finite(atr21[index])
            and close[index] < sma50[index] - 0.5 * atr21[index]
            and (
                volume[index] > volume[index - 1]
                or (_is_finite(vol_sma50[index]) and volume[index] > vol_sma50[index])
            )
        )
        if strong_50_break:
            return "Deutlicher volumenbestätigter Bruch der 50-SMA"
        if _is_finite(ema21[index]) and _is_finite(sma50[index]) and ema21[index] < sma50[index]:
            return "21-EMA unter 50-SMA"
        if uptrend_structure_low is not None and close[index] < uptrend_structure_low:
            return "Schlusskurs unter letztem bestätigten höheren Swing-Tief"
        if phase_warning_streak[index] >= 2:
            return "Mindestens vier indexinterne Warnzeichen an zwei Handelstagen"
        return None

    def pressure_recovered(index: int) -> bool:
        return bool(
            pressure_closes_above_21 >= 2
            and _is_finite(ema21[index])
            and _is_finite(atr21[index])
            and close[index] >= ema21[index] + 0.1 * atr21[index]
            and _is_finite(sma50[index])
            and close[index] > sma50[index]
            and _is_finite(sma200[index])
            and close[index] > sma200[index]
            and ema21[index] > sma50[index] > sma200[index]
            and market_structure[index] != "down"
        )

    for index in range(1, row_count):
        daily_pct = pct_change[index] if _is_finite(pct_change[index]) else 0.0
        range_position = closing_range[index] if _is_finite(closing_range[index]) else 0.5
        transition_reason: str | None = None

        if phase == "neutral":
            if correction_detected(index):
                phase = "rot"
                transition_reason = "Substanzielle Korrektur erkannt"
                clear_state()
        elif phase == "rot":
            if (
                anchor_idx is not None
                and floor_mark is not None
                and index > anchor_idx
                and low[index] < floor_mark
            ):
                anchor_idx = None
                floor_mark = None

            if anchor_idx is None and (daily_pct > 0.0 or range_position >= 0.5):
                anchor_idx = index
                floor_mark = float(np.nanmin([low[index], low[index - 1]]))

            if (
                anchor_idx is not None
                and floor_mark is not None
                and index >= anchor_idx + 5
                and daily_pct >= 1.0
                and volume[index] > volume[index - 1]
                and low[index] >= floor_mark
            ):
                phase = "gelb_startschuss"
                startschuss_idx = index
                startschuss_low = float(low[index])
                startschuss_date = dates[index]
                startschuss_bonus = _is_finite(ema21[index]) and close[index] > ema21[index]
                demand_confirmed = False
                closes_above_21_since_start = 0
                transition_reason = "Startschuss erkannt"
        elif phase == "gelb_startschuss":
            if startschuss_low_broken(index):
                phase = "rot"
                transition_reason = "Schlusskurs unter Startschuss-Tief"
                clear_state()
            else:
                closes_above_21_since_start = (
                    closes_above_21_since_start + 1
                    if _is_finite(ema21[index]) and close[index] > ema21[index]
                    else 0
                )
                if (
                    daily_pct >= 1.0
                    and volume[index] > volume[index - 1]
                    and startschuss_low is not None
                    and close[index] >= startschuss_low
                ):
                    demand_confirmed = True
                if (
                    startschuss_idx is not None
                    and index >= startschuss_idx + GREEN_CONFIRMATION_DAYS
                    and (demand_confirmed or closes_above_21_since_start >= 3)
                ):
                    phase = "gruen"
                    transition_reason = (
                        "Zusätzlicher Akkumulationstag bestätigt Grün"
                        if demand_confirmed
                        else "Drei Schlusskurse über der 21-EMA bestätigen Grün"
                    )
        elif phase == "gruen":
            if startschuss_low_broken(index):
                phase = "rot"
                transition_reason = "Schlusskurs unter Startschuss-Tief"
                clear_state()
            elif uptrend_confirmed(index):
                phase = "aufwaertstrend"
                uptrend_high = float(high[index])
                uptrend_structure_low = (
                    float(latest_swing_low[index]) if _is_finite(latest_swing_low[index]) else None
                )
                transition_reason = "Aufwärtstrend vollständig bestätigt"
        elif phase == "aufwaertstrend":
            update_uptrend_reference(index)
            hard_red_reason = uptrend_hard_red(index)
            if hard_red_reason:
                phase = "rot"
                transition_reason = hard_red_reason
                clear_state()
            else:
                pressure_reason = uptrend_pressure_reason(index)
                if pressure_reason:
                    phase = "gelb_trend_unter_druck"
                    pressure_closes_above_21 = 0
                    transition_reason = pressure_reason
        elif phase == "gelb_trend_unter_druck":
            update_uptrend_reference(index)
            pressure_closes_above_21 = (
                pressure_closes_above_21 + 1
                if _is_finite(ema21[index]) and close[index] > ema21[index]
                else 0
            )
            hard_red_reason = uptrend_hard_red(index)
            if hard_red_reason:
                phase = "rot"
                transition_reason = hard_red_reason
                clear_state()
            elif pressure_recovered(index):
                if market_structure[index] == "up":
                    phase = "aufwaertstrend"
                    transition_reason = "21-EMA qualifiziert zurückerobert; Aufwärtsstruktur intakt"
                else:
                    phase = "gruen"
                    uptrend_high = None
                    uptrend_structure_low = None
                    transition_reason = "21-EMA zurückerobert; Marktstruktur noch nicht eindeutig aufwärts"

        phases[index] = phase
        phase_reasons[index] = transition_reason or (phase_reasons[index - 1] if index > 0 else None)
        if anchor_idx is not None:
            anchor_dates[index] = pd.Timestamp(df.index[anchor_idx]).strftime("%Y-%m-%d")
        if floor_mark is not None:
            floor_marks[index] = round(floor_mark, 2)
        if startschuss_low is not None:
            startschuss_lows[index] = round(startschuss_low, 2)
        if startschuss_date is not None:
            startschuss_dates[index] = startschuss_date
        if startschuss_bonus is not None:
            startschuss_bonuses[index] = bool(startschuss_bonus)
        if uptrend_high is not None:
            uptrend_highs[index] = round(uptrend_high, 2)
        green_below_sma200[index] = bool(
            phase == "gruen" and _is_finite(sma200[index]) and close[index] < sma200[index]
        )

    df["Ampel_Phase"] = phases
    df["Anchor_Date"] = anchor_dates
    df["Floor_Mark"] = floor_marks
    df["Startschuss_Low"] = startschuss_lows
    df["Startschuss_Date"] = startschuss_dates
    df["Startschuss_Bonus"] = startschuss_bonuses
    df["Uptrend_High"] = uptrend_highs
    df["Green_Below_SMA200"] = green_below_sma200
    df["Phase_Reason"] = phase_reasons
    return df


def _count_active_distribution_days(
    distribution_mask: pd.Series,
    close: pd.Series,
    window_days: int = 25,
    recovery_gain_pct: float = 6.0,
) -> pd.Series:
    mask = distribution_mask.fillna(False).astype(bool).to_numpy()
    close_values = pd.to_numeric(close, errors="coerce").to_numpy(dtype=float)
    recovery_factor = 1.0 + max(float(recovery_gain_pct), 0.0) / 100.0
    counts: list[int] = []

    for index in range(len(mask)):
        start = max(0, index - int(window_days) + 1)
        count = 0
        for distribution_index in range(start, index + 1):
            if not mask[distribution_index]:
                continue
            ref_close = close_values[distribution_index]
            recovered = False
            if (
                np.isfinite(ref_close)
                and ref_close > 0
                and recovery_factor > 1.0
                and index > distribution_index
            ):
                later = close_values[distribution_index + 1 : index + 1]
                later = later[np.isfinite(later)]
                recovered = bool(len(later) and later.max() >= ref_close * recovery_factor)
            if not recovered:
                count += 1
        counts.append(count)

    return pd.Series(counts, index=distribution_mask.index, dtype="int64")


def _trend_ampel_point(index: Any, row: pd.Series) -> TrendAmpelPoint:
    return TrendAmpelPoint(
        date=pd.Timestamp(index).strftime("%Y-%m-%d"),
        phase=str(row.get("Ampel_Phase") or "neutral"),  # type: ignore[arg-type]
        close=_safe_float(row.get("Close")),
        ema21=_safe_float(row.get("EMA21")),
        sma50=_safe_float(row.get("SMA50")),
        sma200=_safe_float(row.get("SMA200")),
        pct_change=_safe_float(row.get("Pct_Change")),
        closing_range=_safe_float(row.get("Closing_Range")),
        dist_count_25=int(row.get("Dist_Count_25") or 0),
        anchor_date=_safe_str(row.get("Anchor_Date")),
        floor_mark=_safe_float(row.get("Floor_Mark")),
        startschuss_low=_safe_float(row.get("Startschuss_Low")),
        startschuss_bonus=_safe_bool(row.get("Startschuss_Bonus")),
        open=_safe_float(row.get("Open")),
        high=_safe_float(row.get("High")),
        low=_safe_float(row.get("Low")),
        volume=_safe_float(row.get("Volume")),
        sma10=_safe_float(row.get("SMA10")),
        atr21=_safe_float(row.get("ATR21")),
        atr_pct=_safe_float(row.get("ATR_pct")),
        vol_sma50=_safe_float(row.get("Vol_SMA50")),
        dist_21ema=_safe_float(row.get("Dist_21EMA")),
        dist_10sma_pct=_safe_float(row.get("Dist_10SMA_pct")),
        dist_50sma_pct=_safe_float(row.get("Dist_50SMA_pct")),
        dist_200sma_pct=_safe_float(row.get("Dist_200SMA_pct")),
        high_52w=_safe_float(row.get("High_52w")),
        dist_52w_pct=_safe_float(row.get("Dist_52w_pct")),
        ma_order=_safe_bool(row.get("MA_Order")),
        low_above_21=_safe_bool(row.get("Low_above_21")),
        low_above_50=_safe_bool(row.get("Low_above_50")),
        low_above_200=_safe_bool(row.get("Low_above_200")),
        consec_low_above_21=_safe_int(row.get("Consec_Low_above_21")),
        consec_low_above_50=_safe_int(row.get("Consec_Low_above_50")),
        consec_low_above_200=_safe_int(row.get("Consec_Low_above_200")),
        ema21_held=_safe_bool(row.get("EMA21_held")),
        sma50_held=_safe_bool(row.get("SMA50_held")),
        sma200_held=_safe_bool(row.get("SMA200_held")),
        intraday_reversal_down=_safe_bool(row.get("Intraday_Reversal_Down")),
        intraday_reversal_up=_safe_bool(row.get("Intraday_Reversal_Up")),
        neg_reversals_10d=_safe_int(row.get("Neg_Reversals_10d")),
        pos_reversals_10d=_safe_int(row.get("Pos_Reversals_10d")),
        low_cr_5d=_safe_int(row.get("Low_CR_5d")),
        up_vol_declining=_safe_bool(row.get("Up_Vol_Declining")),
        is_distribution=_safe_bool(row.get("Is_Distribution")),
        is_stall=_safe_bool(row.get("Is_Stall")),
        loss_days_10d=_safe_int(row.get("Loss_Days_10d")),
        gain_days_10d=_safe_int(row.get("Gain_Days_10d")),
        loss_gain_ratio_10d=_safe_float(row.get("Loss_Gain_Ratio_10d")),
        startschuss_date=_safe_str(row.get("Startschuss_Date")),
        uptrend_high=_safe_float(row.get("Uptrend_High")),
        market_structure=str(row.get("Market_Structure") or "unknown"),  # type: ignore[arg-type]
        high_structure=str(row.get("High_Structure") or "unknown"),  # type: ignore[arg-type]
        low_structure=str(row.get("Low_Structure") or "unknown"),  # type: ignore[arg-type]
        latest_swing_high=_safe_float(row.get("Latest_Swing_High")),
        latest_swing_high_date=_safe_str(row.get("Latest_Swing_High_Date")),
        latest_swing_low=_safe_float(row.get("Latest_Swing_Low")),
        latest_swing_low_date=_safe_str(row.get("Latest_Swing_Low_Date")),
        consecutive_closes_below_ema21=_safe_int(row.get("Consec_Close_Below_21")),
        consecutive_closes_above_ema21=_safe_int(row.get("Consec_Close_Above_21")),
        ma_order_streak=_safe_int(row.get("MA_Order_Streak")),
        ema21_rising=_safe_bool(row.get("EMA21_Rising")),
        sma50_rising=_safe_bool(row.get("SMA50_Rising")),
        phase_warning_count=_safe_int(row.get("Phase_Warning_Count")),
        phase_warning_streak=_safe_int(row.get("Phase_Warning_Streak")),
        green_below_sma200=bool(_safe_bool(row.get("Green_Below_SMA200"))),
        phase_reason=_safe_str(row.get("Phase_Reason")),
    )


def _frame_from_bars(bars: Sequence[TrendAmpelBar | Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        close = _safe_float(_get(bar, "close"))
        if close is None:
            continue
        bar_date = pd.Timestamp(_get(bar, "date"))
        rows.append(
            {
                "Date": bar_date,
                "Open": _safe_float(_get(bar, "open")) or close,
                "High": _safe_float(_get(bar, "high")) or close,
                "Low": _safe_float(_get(bar, "low")) or close,
                "Close": close,
                "Volume": _safe_float(_get(bar, "volume")) or 0.0,
            }
        )

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["Date"], keep="last")
        .set_index("Date")
        .sort_index()
    )


def _get(source: TrendAmpelBar | Mapping[str, Any], key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key) or source.get(key.capitalize())
    return getattr(source, key)


def _sma(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window, min_periods=window).mean()


def _ema(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").ewm(span=window, adjust=False).mean()


def _consecutive_true(series: pd.Series) -> pd.Series:
    values = series.fillna(False).astype(bool).to_numpy()
    output = np.zeros(len(values), dtype=int)
    for index, value in enumerate(values):
        if value:
            output[index] = output[index - 1] + 1 if index > 0 else 1
    return pd.Series(output, index=series.index, dtype="int64")


def _atr(frame: pd.DataFrame, window: int = 21) -> pd.Series:
    high = pd.to_numeric(frame["High"], errors="coerce")
    low = pd.to_numeric(frame["Low"], errors="coerce")
    previous_close = pd.to_numeric(frame["Close"], errors="coerce").shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=window).mean()


def _is_finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(value))
    except TypeError:
        return False


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


def _safe_bool(value: Any) -> bool | None:
    if value is None or pd.isna(value):
        return None
    return bool(value)


def _safe_int(value: Any) -> int:
    if value is None or pd.isna(value):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)
