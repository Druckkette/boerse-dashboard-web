from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


RS_METHOD_UNIVERSE_PERCENTILE = "universe_percentile"
DEFAULT_RS_WINDOWS: tuple[tuple[int, float], ...] = ((63, 0.4), (126, 0.2), (189, 0.2), (252, 0.2))


@dataclass(frozen=True)
class ClosePoint:
    date: date
    close: float


@dataclass(frozen=True)
class RelativeStrengthRating:
    ticker: str
    date: date
    rating: int
    score: float
    percentile: float
    method: str
    universe_size: int
    metadata: dict[str, Any]


def compute_relative_strength_ratings(
    series: Mapping[str, Sequence[Any]],
    *,
    benchmark_ticker: str = "SPY",
    windows: tuple[tuple[int, float], ...] = DEFAULT_RS_WINDOWS,
    min_common_points: int = 80,
    max_staleness_days: int = 4,
) -> list[RelativeStrengthRating]:
    """Compute universe-percentile RS ratings from cached close series.

    This mirrors the old Streamlit approach conceptually:
    stock/benchmark relative-strength lines are scored across 3/6/9/12 month
    windows and then converted to 1-99 percentile ratings across the universe.
    """

    clean_benchmark = benchmark_ticker.strip().upper()
    benchmark_close = _coerce_close_series(series.get(clean_benchmark) or [])
    if benchmark_close.empty:
        return []
    benchmark_as_of = benchmark_close.index[-1]
    required_common_points = max(
        min_common_points,
        max((lookback for lookback, _weight in windows), default=0) + 1,
    )

    scored_rows: list[dict[str, Any]] = []
    for raw_ticker, points in series.items():
        ticker = raw_ticker.strip().upper()
        if not ticker or ticker == clean_benchmark:
            continue

        stock_close = _coerce_close_series(points)
        raw_rs = _build_relative_strength_line(stock_close, benchmark_close, normalize_to=None)
        if raw_rs is None or len(raw_rs) < required_common_points:
            continue
        if (benchmark_as_of - raw_rs.index[-1]).days > max(0, max_staleness_days):
            continue

        score = _weighted_rs_score(raw_rs, windows=windows)
        if score is None:
            continue

        plot_rs = _build_relative_strength_line(stock_close, benchmark_close, normalize_to=100.0)
        metadata = _build_metadata(stock_close, raw_rs, plot_rs)
        scored_rows.append(
            {
                "ticker": ticker,
                "date": raw_rs.index[-1].date(),
                "score": float(score),
                "metadata": metadata,
            }
        )

    if not scored_rows:
        return []

    score_series = pd.Series({row["ticker"]: row["score"] for row in scored_rows}, dtype=float)
    percentile_ranks = score_series.rank(pct=True, method="average")
    universe_size = int(len(score_series))

    ratings: list[RelativeStrengthRating] = []
    for row in scored_rows:
        ticker = str(row["ticker"])
        percentile = float(percentile_ranks.loc[ticker] * 100)
        rating = int(np.clip(round(float(percentile_ranks.loc[ticker]) * 99), 1, 99))
        ratings.append(
            RelativeStrengthRating(
                ticker=ticker,
                date=row["date"],
                rating=rating,
                score=float(row["score"]),
                percentile=percentile,
                method=RS_METHOD_UNIVERSE_PERCENTILE,
                universe_size=universe_size,
                metadata=row["metadata"],
            )
        )

    return sorted(ratings, key=lambda item: (item.rating, item.score), reverse=True)


def _coerce_close_series(points: Sequence[Any]) -> pd.Series:
    values: list[tuple[pd.Timestamp, float]] = []
    for point in points:
        point_date = _point_value(point, "date")
        close = _point_value(point, "close")
        if point_date is None or close is None:
            continue
        timestamp = pd.to_datetime(point_date, errors="coerce")
        if pd.isna(timestamp):
            continue
        close_value = pd.to_numeric(close, errors="coerce")
        if pd.isna(close_value) or float(close_value) <= 0:
            continue
        values.append((pd.Timestamp(timestamp).normalize(), float(close_value)))

    if not values:
        return pd.Series(dtype=float)

    index = [item[0] for item in values]
    closes = [item[1] for item in values]
    series = pd.Series(closes, index=pd.DatetimeIndex(index), dtype=float)
    return series[~series.index.duplicated(keep="last")].sort_index().dropna()


def _build_relative_strength_line(
    stock_close: pd.Series,
    benchmark_close: pd.Series,
    *,
    normalize_to: float | None,
) -> pd.Series | None:
    if stock_close.empty or benchmark_close.empty:
        return None
    common = stock_close.index.intersection(benchmark_close.index)
    if len(common) < 60:
        return None

    stock_common = stock_close.reindex(common)
    benchmark_common = benchmark_close.reindex(common)
    rs_line = (stock_common / benchmark_common).replace([np.inf, -np.inf], np.nan).dropna()
    if rs_line.empty:
        return None

    if normalize_to is not None:
        base = rs_line.iloc[0]
        if pd.notna(base) and base != 0:
            rs_line = rs_line / base * float(normalize_to)

    return rs_line


def _weighted_rs_score(
    rs_line: pd.Series,
    *,
    windows: tuple[tuple[int, float], ...],
) -> float | None:
    series = pd.to_numeric(rs_line, errors="coerce").dropna()
    if len(series) < 80:
        return None

    last = float(series.iloc[-1])
    score = 0.0
    weight_sum = 0.0
    for lookback, weight in windows:
        if len(series) <= lookback:
            continue
        previous = float(series.iloc[-lookback - 1])
        if previous == 0 or np.isnan(previous):
            continue
        score += ((last / previous) - 1.0) * weight
        weight_sum += weight

    if weight_sum == 0:
        return None
    return score / weight_sum


def _build_metadata(stock_close: pd.Series, raw_rs: pd.Series, plot_rs: pd.Series | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "ret_1m_pct": _return_pct(stock_close, 21),
        "ret_3m_pct": _return_pct(stock_close, 63),
        "ret_6m_pct": _return_pct(stock_close, 126),
        "ret_12m_pct": _return_pct(stock_close, 252),
        "excess_return_3m_pct": _return_pct(raw_rs, 63),
        "excess_return_6m_pct": _return_pct(raw_rs, 126),
        "excess_return_12m_pct": _return_pct(raw_rs, 252),
    }
    if plot_rs is None or plot_rs.empty:
        return metadata

    ema21 = plot_rs.ewm(span=21, adjust=False).mean()
    ema50 = plot_rs.ewm(span=50, adjust=False).mean()
    sma50 = plot_rs.rolling(50, min_periods=50).mean()
    sma200 = plot_rs.rolling(200).mean()
    last = float(plot_rs.iloc[-1])
    metadata.update(
        {
            "rs_line_last": last,
            "above_21": _last_bool(plot_rs, ema21),
            "above_50": _last_bool(plot_rs, sma50),
            "above_200": _last_bool(plot_rs, sma200),
            "rs_ema21_last": _last_float(ema21),
            "rs_ema50_last": _last_float(ema50),
            "rs_sma50_last": _last_float(sma50),
            "rs_history": _rs_history(plot_rs, ema21=ema21, ema50=ema50, sma50=sma50),
            "trend_5w": _trend_bool(plot_rs, 25),
            "trend_13w": _trend_bool(plot_rs, 65),
        }
    )
    high_52w = plot_rs.rolling(252, min_periods=50).max().iloc[-1] if len(plot_rs) >= 50 else np.nan
    if pd.notna(high_52w) and float(high_52w) != 0:
        metadata.update(
            {
                "distance_to_high_pct": float((last / float(high_52w) - 1) * 100),
                "near_high_52w": bool(last >= float(high_52w) * 0.97),
                "new_high_52w": bool(last >= float(high_52w) * 0.999),
            }
        )
    return metadata


def _return_pct(series: pd.Series, lookback: int) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) <= lookback:
        return None
    previous = float(clean.iloc[-lookback - 1])
    if previous == 0 or np.isnan(previous):
        return None
    return float((float(clean.iloc[-1]) / previous - 1.0) * 100)


def _last_bool(series: pd.Series, average: pd.Series) -> bool | None:
    if series.empty or average.empty or pd.isna(average.iloc[-1]):
        return None
    return bool(float(series.iloc[-1]) > float(average.iloc[-1]))


def _last_float(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(clean.iloc[-1])


def _rs_history(
    plot_rs: pd.Series,
    *,
    ema21: pd.Series,
    ema50: pd.Series,
    sma50: pd.Series,
    limit: int = 370,
) -> list[dict[str, Any]]:
    frame = pd.DataFrame({"rs": plot_rs, "rs_ema21": ema21, "rs_ema50": ema50, "rs_sma50": sma50}).dropna(
        subset=["rs"]
    ).tail(limit)
    history: list[dict[str, Any]] = []
    for timestamp, row in frame.iterrows():
        history.append(
            {
                "date": pd.Timestamp(timestamp).date().isoformat(),
                "rs": _rounded_or_none(row.get("rs")),
                "rs_ema21": _rounded_or_none(row.get("rs_ema21")),
                "rs_ema50": _rounded_or_none(row.get("rs_ema50")),
                "rs_sma50": _rounded_or_none(row.get("rs_sma50")),
            }
        )
    return history


def _rounded_or_none(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _trend_bool(series: pd.Series, lookback: int) -> bool | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) <= lookback:
        return None
    return bool(float(clean.iloc[-1]) > float(clean.iloc[-lookback - 1]))


def _point_value(point: Any, key: str) -> Any:
    if isinstance(point, Mapping):
        return point.get(key)
    return getattr(point, key, None)
