from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.domain.market.regime import MarketPhase


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


def compute_trend_ampel(bars: Sequence[TrendAmpelBar | Mapping[str, Any]]) -> list[TrendAmpelPoint]:
    frame = _frame_from_bars(bars)
    if frame.empty:
        return []

    indicator_frame = add_trend_indicators(frame)
    distribution_frame = detect_distribution_days(indicator_frame)
    ampel_frame = _compute_ampel_frame(distribution_frame)
    return [_trend_ampel_point(index, row) for index, row in ampel_frame.iterrows()]


def add_trend_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    df["EMA21"] = _ema(df["Close"], 21)
    df["SMA50"] = _sma(df["Close"], 50)
    df["SMA200"] = _sma(df["Close"], 200)
    df["SMA10"] = _sma(df["Close"], 10)
    df["ATR21"] = _atr(df, 21)
    df["ATR_pct"] = df["ATR21"] / df["Close"] * 100
    df["Vol_SMA50"] = _sma(df["Volume"], 50)
    df["Pct_Change"] = df["Close"].pct_change(fill_method=None) * 100

    daily_range = df["High"] - df["Low"]
    df["Closing_Range"] = np.where(
        daily_range > 0,
        (df["Close"] - df["Low"]) / daily_range,
        0.5,
    )
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
    df["Dist_Count_25"] = _count_active_distribution_days(df["Is_Distribution"], df["Close"])
    return df


def _compute_ampel_frame(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    row_count = len(df)
    phase: MarketPhase = "neutral"
    anchor_idx: int | None = None
    floor_mark: float | None = None
    startschuss_idx: int | None = None
    startschuss_low: float | None = None
    gruen_since: int | None = None
    startschuss_bonus: bool | None = None

    phases: list[MarketPhase] = ["neutral"] * row_count
    anchor_dates: list[str | None] = [None] * row_count
    floor_marks: list[float | None] = [None] * row_count
    startschuss_lows: list[float | None] = [None] * row_count
    startschuss_bonuses: list[bool | None] = [None] * row_count

    close = df["Close"].to_numpy(dtype=float)
    open_ = df["Open"].to_numpy(dtype=float)
    high = df["High"].to_numpy(dtype=float)
    low = df["Low"].to_numpy(dtype=float)
    volume = df["Volume"].to_numpy(dtype=float)
    pct_change = df["Pct_Change"].to_numpy(dtype=float)
    closing_range = df["Closing_Range"].to_numpy(dtype=float)
    dist_count_25 = df["Dist_Count_25"].to_numpy(dtype=float)
    sma50 = df["SMA50"].to_numpy(dtype=float)
    sma200 = df["SMA200"].to_numpy(dtype=float)
    ema21 = df["EMA21"].to_numpy(dtype=float)

    def clear_state() -> None:
        nonlocal anchor_idx, floor_mark, startschuss_idx, startschuss_low, gruen_since
        nonlocal startschuss_bonus
        anchor_idx = None
        floor_mark = None
        startschuss_idx = None
        startschuss_low = None
        gruen_since = None
        startschuss_bonus = None

    def correction_detected(index: int) -> bool:
        lookback = max(0, index - 60)
        recent_high = np.nanmax(high[lookback : index + 1])
        if not np.isfinite(recent_high) or recent_high <= 0:
            return False
        drawdown_pct = (close[index] - recent_high) / recent_high * 100
        below_sma50_with_distribution = (
            _is_finite(sma50[index]) and close[index] < sma50[index] and dist_count_25[index] >= 4
        )
        return drawdown_pct < -10 or below_sma50_with_distribution

    for index in range(1, row_count):
        daily_pct = pct_change[index] if _is_finite(pct_change[index]) else 0.0
        range_position = closing_range[index] if _is_finite(closing_range[index]) else 0.5

        if phase in {"neutral", "aufwaertstrend"}:
            if correction_detected(index):
                phase = "rot"
                clear_state()
            elif (
                phase == "aufwaertstrend"
                and _is_finite(ema21[index])
                and _is_finite(sma50[index])
                and ema21[index] < sma50[index]
            ):
                phase = "rot"
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

            if anchor_idx is None and (daily_pct > 0.0 or (close[index] > open_[index] and range_position >= 0.5)):
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
                phase = "gelb"
                startschuss_idx = index
                startschuss_low = float(low[index])
                startschuss_bonus = _is_finite(ema21[index]) and close[index] > ema21[index]
        elif phase == "gelb":
            if startschuss_low is not None and close[index] < startschuss_low:
                phase = "rot"
                clear_state()
            elif startschuss_idx is not None and index > startschuss_idx + 2:
                phase = "gruen"
                gruen_since = index
        elif phase == "gruen":
            if startschuss_low is not None and close[index] < startschuss_low:
                phase = "rot"
                clear_state()
            elif (
                _is_finite(sma200[index])
                and close[index] > sma200[index]
                and _is_finite(ema21[index])
                and _is_finite(sma50[index])
                and ema21[index] > sma50[index]
                and gruen_since is not None
                and index - gruen_since >= 10
            ):
                phase = "aufwaertstrend"

        phases[index] = phase
        if anchor_idx is not None:
            anchor_dates[index] = pd.Timestamp(df.index[anchor_idx]).strftime("%Y-%m-%d")
        if floor_mark is not None:
            floor_marks[index] = round(floor_mark, 2)
        if startschuss_low is not None:
            startschuss_lows[index] = round(startschuss_low, 2)
        if startschuss_bonus is not None:
            startschuss_bonuses[index] = bool(startschuss_bonus)

    df["Ampel_Phase"] = phases
    df["Anchor_Date"] = anchor_dates
    df["Floor_Mark"] = floor_marks
    df["Startschuss_Low"] = startschuss_lows
    df["Startschuss_Bonus"] = startschuss_bonuses
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


def _safe_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)
