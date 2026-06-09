from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


BENCHMARK_TICKER = "SPY"
VIX_TICKER = "^VIX"
VIXY_TICKER = "VIXY"
VOLATILITY_TICKERS = [BENCHMARK_TICKER, VIX_TICKER, VIXY_TICKER]


@dataclass(frozen=True)
class VolatilityDashboardPoint:
    date: str
    spx_close: float | None
    spx_ret_5d: float | None
    vix_close: float | None
    vix_ret_5d: float | None
    vix_pct_rank_252: float | None
    vix_regime: str
    vixy_close: float | None
    vixy_ret_5d: float | None
    vixy_state: str
    vixy_stress_confirmation: bool
    vixy_carry_decay: bool
    vol_regime: str
    fragile_rally: bool


def compute_volatility_dashboard(
    series: Mapping[str, Iterable[Any]],
    *,
    benchmark_ticker: str = BENCHMARK_TICKER,
    vix_ticker: str = VIX_TICKER,
    vixy_ticker: str = VIXY_TICKER,
    limit: int = 180,
) -> list[VolatilityDashboardPoint]:
    spx = _frame_from_points(series.get(benchmark_ticker) or [])
    if spx.empty:
        return []

    vix = analyze_vix(_frame_from_points(series.get(vix_ticker) or []))
    vixy = analyze_vixy(_frame_from_points(series.get(vixy_ticker) or []))
    dashboard = _build_dashboard(spx, vix if not vix.empty else None, vixy if not vixy.empty else None)
    return [_dashboard_point(index, row) for index, row in dashboard.tail(max(1, min(500, limit))).iterrows()]


def summarize_volatility_points(points: list[VolatilityDashboardPoint]) -> dict[str, Any]:
    if not points:
        return {
            "regime": "Nicht berechnet",
            "status_cards": [
                {
                    "title": "Vol Regime",
                    "status": "Keine Daten",
                    "detail": "SPY, ^VIX und VIXY zuerst per Price-Refresh laden.",
                    "tone": "neutral",
                }
            ],
        }

    latest = points[-1]
    status_cards = [
        _status_card(
            "VIX Regime",
            latest.vix_regime,
            _vix_detail(latest),
            "bad" if latest.vix_regime == "Stress" else "good" if latest.vix_regime == "Ruhig" else "warning",
        ),
        _status_card(
            "VIXY Bestätigung",
            "Bestätigt" if latest.vixy_stress_confirmation else "Kein Stress" if latest.vixy_carry_decay else latest.vixy_state,
            _vixy_detail(latest),
            "bad" if latest.vixy_stress_confirmation else "good" if latest.vixy_carry_decay else "warning",
        ),
        _status_card(
            "Vol Regime",
            latest.vol_regime,
            _volatility_detail(latest.vol_regime),
            _tone_for_volatility_regime(latest.vol_regime),
        ),
        _status_card(
            "Fragile Rally",
            "Warnung" if latest.fragile_rally else "Keine",
            "S&P 500 steigt, aber VIX oder VIXY bleiben zu stark"
            if latest.fragile_rally
            else "Keine belastbare Divergenz zwischen Rally und Volatilität",
            "warning" if latest.fragile_rally else "good",
        ),
    ]
    return {"regime": latest.vol_regime, "status_cards": status_cards}


def analyze_vix(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    dv = frame.copy()
    dv["SMA10"] = _sma(dv["Close"], 10)
    dv["EMA10"] = _ema(dv["Close"], 10)
    dv["EMA21"] = _ema(dv["Close"], 21)
    dv["Ret_5d"] = dv["Close"].pct_change(5)
    dv["Ret_20d"] = dv["Close"].pct_change(20)
    dv["Z63"] = _rolling_zscore(dv["Close"], 63)
    dv["PctRank252"] = _rolling_percentile(dv["Close"], 252)
    dv["Pct_Above_SMA10"] = (dv["Close"] - dv["SMA10"]) / dv["SMA10"] * 100

    panic_rule = (dv["PctRank252"] >= 0.85) & (dv["Z63"] >= 1.5)
    fallback_panic = (dv["Close"] > 20) & (dv["Close"] > dv["EMA10"])
    calm_rule = (dv["PctRank252"] <= 0.25) & (dv["Z63"] <= -0.5)
    fallback_calm = (dv["Close"] < 16) & (dv["Close"] < dv["EMA10"])

    dv["Is_Panic"] = panic_rule.fillna(False) | fallback_panic.fillna(False)
    dv["Is_Calm"] = calm_rule.fillna(False) | fallback_calm.fillna(False)
    dv["VIX_Regime"] = np.select(
        [dv["Is_Panic"], dv["Is_Calm"]],
        ["Stress", "Ruhig"],
        default="Neutral",
    )
    return dv


def analyze_vixy(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    dx = frame.copy()
    dx["EMA10"] = _ema(dx["Close"], 10)
    dx["EMA21"] = _ema(dx["Close"], 21)
    dx["EMA50"] = _ema(dx["Close"], 50)
    dx["Ret_5d"] = dx["Close"].pct_change(5)
    dx["Ret_20d"] = dx["Close"].pct_change(20)
    dx["Z63"] = _rolling_zscore(dx["Close"], 63)
    dx["PctRank252"] = _rolling_percentile(dx["Close"], 252)

    trend_up = (dx["Close"] > dx["EMA21"]) & (dx["EMA21"] > dx["EMA21"].shift(5))
    dx["Stress_Confirmation"] = (
        ((dx["Ret_5d"] > 0.08) & (dx["PctRank252"] > 0.70) & trend_up)
        | ((dx["Ret_5d"] > 0.05) & trend_up)
    ).fillna(False)
    dx["Carry_Decay"] = ((dx["Close"] < dx["EMA21"]) & (dx["Ret_20d"] < 0)).fillna(False)
    dx["VIXY_State"] = np.select(
        [dx["Stress_Confirmation"], dx["Carry_Decay"]],
        ["Bestätigt", "Abbau"],
        default="Gemischt",
    )
    return dx


def _build_dashboard(spx_df: pd.DataFrame, vix_df: pd.DataFrame | None, vixy_df: pd.DataFrame | None) -> pd.DataFrame:
    out = pd.DataFrame(index=spx_df.index.copy())
    out["SPX_Close"] = spx_df["Close"]
    out["SPX_Ret_5d"] = spx_df["Close"].pct_change(5)

    if vix_df is not None and not vix_df.empty:
        vix = vix_df.reindex(out.index).ffill()
        out["VIX_Close"] = vix["Close"]
        out["VIX_Ret_5d"] = vix.get("Ret_5d")
        out["VIX_PctRank252"] = vix.get("PctRank252")
        out["VIX_Is_Panic"] = vix.get("Is_Panic", False).fillna(False)
        out["VIX_Is_Calm"] = vix.get("Is_Calm", False).fillna(False)
        out["VIX_Regime"] = vix.get("VIX_Regime", "Neutral")
    else:
        out["VIX_Close"] = np.nan
        out["VIX_Ret_5d"] = np.nan
        out["VIX_PctRank252"] = np.nan
        out["VIX_Is_Panic"] = False
        out["VIX_Is_Calm"] = False
        out["VIX_Regime"] = "n/a"

    if vixy_df is not None and not vixy_df.empty:
        vixy = vixy_df.reindex(out.index).ffill()
        out["VIXY_Close"] = vixy["Close"]
        out["VIXY_Ret_5d"] = vixy.get("Ret_5d")
        out["VIXY_Stress_Confirmation"] = vixy.get("Stress_Confirmation", False).fillna(False)
        out["VIXY_Carry_Decay"] = vixy.get("Carry_Decay", False).fillna(False)
        out["VIXY_State"] = vixy.get("VIXY_State", "Gemischt")
    else:
        out["VIXY_Close"] = np.nan
        out["VIXY_Ret_5d"] = np.nan
        out["VIXY_Stress_Confirmation"] = False
        out["VIXY_Carry_Decay"] = False
        out["VIXY_State"] = "n/a"

    out["Fragile_Rally"] = (
        (out["SPX_Ret_5d"] > 0)
        & (
            out["VIXY_Stress_Confirmation"]
            | (out["VIX_Ret_5d"] > 0)
            | ((out["VIXY_Ret_5d"] > 0.03) & (out["VIX_PctRank252"] > 0.55))
        )
    ).fillna(False)

    conditions = [
        out["VIX_Is_Panic"] & out["VIXY_Stress_Confirmation"],
        out["VIX_Is_Panic"] & ~out["VIXY_Stress_Confirmation"],
        out["Fragile_Rally"],
        out["VIX_Is_Calm"] & out["VIXY_Carry_Decay"] & (out["SPX_Ret_5d"] > 0),
    ]
    labels = [
        "Risk Off bestätigt",
        "Kurzer Volatilitätsschock",
        "Fragile Rally",
        "Risk On / ruhig",
    ]
    out["Vol_Regime"] = np.select(conditions, labels, default="Neutral")
    return out


def _dashboard_point(index: Any, row: pd.Series) -> VolatilityDashboardPoint:
    return VolatilityDashboardPoint(
        date=pd.Timestamp(index).strftime("%Y-%m-%d"),
        spx_close=_safe_float(row.get("SPX_Close")),
        spx_ret_5d=_safe_float(row.get("SPX_Ret_5d")),
        vix_close=_safe_float(row.get("VIX_Close")),
        vix_ret_5d=_safe_float(row.get("VIX_Ret_5d")),
        vix_pct_rank_252=_safe_float(row.get("VIX_PctRank252")),
        vix_regime=str(row.get("VIX_Regime") or "n/a"),
        vixy_close=_safe_float(row.get("VIXY_Close")),
        vixy_ret_5d=_safe_float(row.get("VIXY_Ret_5d")),
        vixy_state=str(row.get("VIXY_State") or "n/a"),
        vixy_stress_confirmation=bool(row.get("VIXY_Stress_Confirmation", False)),
        vixy_carry_decay=bool(row.get("VIXY_Carry_Decay", False)),
        vol_regime=str(row.get("Vol_Regime") or "Neutral"),
        fragile_rally=bool(row.get("Fragile_Rally", False)),
    )


def _frame_from_points(points: Iterable[Any]) -> pd.DataFrame:
    rows = []
    for point in points:
        close = _safe_float(getattr(point, "close", None))
        if close is None:
            continue
        rows.append({"Date": pd.Timestamp(getattr(point, "date")), "Close": close})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["Date"], keep="last").set_index("Date").sort_index()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window, min_periods=window).mean()


def _ema(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").ewm(span=window, adjust=False, min_periods=window).mean()


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce")
    mean = clean.rolling(window, min_periods=max(20, window // 3)).mean()
    std = clean.rolling(window, min_periods=max(20, window // 3)).std()
    return (clean - mean) / std.replace(0, np.nan)


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce")
    min_periods = max(60, window // 4)

    def _pct_rank(values: np.ndarray) -> float:
        ranked = pd.Series(values).rank(pct=True)
        return float(ranked.iloc[-1])

    return clean.rolling(window, min_periods=min_periods).apply(_pct_rank, raw=True)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _status_card(title: str, status: str, detail: str, tone: str) -> dict[str, str]:
    return {"title": title, "status": status, "detail": detail, "tone": tone}


def _vix_detail(latest: VolatilityDashboardPoint) -> str:
    if latest.vix_close is None:
        return "Keine VIX-Daten verfügbar"
    if latest.vix_regime == "Stress":
        return f"VIX {latest.vix_close:.1f} · erhöht gegenüber der eigenen Historie"
    if latest.vix_regime == "Ruhig":
        return f"VIX {latest.vix_close:.1f} · wenig Angst im Optionsmarkt"
    return f"VIX {latest.vix_close:.1f} · keine Extremzone"


def _vixy_detail(latest: VolatilityDashboardPoint) -> str:
    if latest.vixy_close is None:
        return "Keine VIXY-Daten verfügbar"
    if latest.vixy_stress_confirmation:
        return f"VIXY {latest.vixy_close:.1f} · Futures-Stress wird getragen"
    if latest.vixy_carry_decay:
        return f"VIXY {latest.vixy_close:.1f} · eher normales Carry-Umfeld"
    return f"VIXY {latest.vixy_close:.1f} · keine klare Bestätigung"


def _volatility_detail(regime: str) -> str:
    return {
        "Risk Off bestätigt": "VIX und VIXY ziehen gleichzeitig an",
        "Kurzer Volatilitätsschock": "VIX springt an, Futures bestätigen aber nicht voll",
        "Fragile Rally": "Aktienmarkt steigt, Volatilität bleibt aber zu fest",
        "Risk On / ruhig": "Ruhiges Umfeld mit abbauendem VIXY",
    }.get(regime, "Keine klare Volatilitätslage")


def _tone_for_volatility_regime(regime: str) -> str:
    if regime == "Risk Off bestätigt":
        return "bad"
    if regime in {"Kurzer Volatilitätsschock", "Fragile Rally"}:
        return "warning"
    if regime == "Risk On / ruhig":
        return "good"
    return "neutral"
