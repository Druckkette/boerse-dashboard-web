from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd


BENCHMARK_TICKER = "SPY"
VIX_TICKER = "^VIX"
VXX_TICKER = "VXX"
VOLATILITY_TICKERS = [BENCHMARK_TICKER, VIX_TICKER, VXX_TICKER]


@dataclass(frozen=True)
class VolatilityDashboardPoint:
    date: str
    spx_close: float | None
    spx_ret_5d: float | None
    vix_close: float | None
    vix_sma10: float | None
    vix_ema21: float | None
    vix_ret_5d: float | None
    vix_pct_rank_252: float | None
    vix_pct_above_sma10: float | None
    vix_panic_overextension: bool
    vix_regime: str
    vxx_close: float | None
    vxx_ema21: float | None
    vxx_ret_5d: float | None
    vxx_state: str
    vxx_stress_confirmation: bool
    vxx_carry_decay: bool
    vol_regime: str
    fragile_rally: bool


def compute_volatility_dashboard(
    series: Mapping[str, Iterable[Any]],
    *,
    benchmark_ticker: str = BENCHMARK_TICKER,
    vix_ticker: str = VIX_TICKER,
    vxx_ticker: str = VXX_TICKER,
    limit: int = 180,
) -> list[VolatilityDashboardPoint]:
    spx = _frame_from_points(series.get(benchmark_ticker) or [])
    if spx.empty:
        return []

    vix = analyze_vix(_frame_from_points(series.get(vix_ticker) or []))
    vxx = analyze_vxx(_frame_from_points(series.get(vxx_ticker) or []))
    dashboard = _build_dashboard(spx, vix if not vix.empty else None, vxx if not vxx.empty else None)
    return [_dashboard_point(index, row) for index, row in dashboard.tail(max(1, min(500, limit))).iterrows()]


def summarize_volatility_points(points: list[VolatilityDashboardPoint]) -> dict[str, Any]:
    if not points:
        return {
            "regime": "Nicht berechnet",
            "status_cards": [
                {
                    "title": "Vol Regime",
                    "status": "Keine Daten",
                    "detail": "SPY, ^VIX und VXX zuerst per Price-Refresh laden.",
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
            _tone_for_vix_regime(latest.vix_regime),
        ),
        _status_card(
            "VIX Überdehnung",
            "Überdehnt" if latest.vix_panic_overextension else "Normal",
            _vix_overextension_detail(latest),
            "warning" if latest.vix_panic_overextension else "good",
        ),
        _status_card(
            "VXX Trend",
            "Stress" if latest.vxx_stress_confirmation else "Entspannt" if latest.vxx_carry_decay else latest.vxx_state,
            _vxx_detail(latest),
            "bad" if latest.vxx_stress_confirmation else "good" if latest.vxx_carry_decay else "warning",
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
            "S&P 500 steigt, aber VIX oder VXX bleiben zu stark"
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
    dv["Panic_Overextension"] = (dv["Pct_Above_SMA10"] > 20).fillna(False)

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


def analyze_vxx(frame: pd.DataFrame) -> pd.DataFrame:
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

    ema21_rising = dx["EMA21"] > dx["EMA21"].shift(5)
    ema21_falling = dx["EMA21"] < dx["EMA21"].shift(5)
    dx["Stress_Confirmation"] = ((dx["Close"] > dx["EMA21"]) & ema21_rising).fillna(False)
    dx["Carry_Decay"] = ((dx["Close"] < dx["EMA21"]) & ema21_falling).fillna(False)
    dx["VXX_State"] = np.select(
        [dx["Stress_Confirmation"], dx["Carry_Decay"]],
        ["Steigend", "Entspannt"],
        default="Gemischt",
    )
    return dx


def _build_dashboard(spx_df: pd.DataFrame, vix_df: pd.DataFrame | None, vxx_df: pd.DataFrame | None) -> pd.DataFrame:
    out = pd.DataFrame(index=spx_df.index.copy())
    out["SPX_Close"] = spx_df["Close"]
    out["SPX_Ret_5d"] = spx_df["Close"].pct_change(5)

    if vix_df is not None and not vix_df.empty:
        # A short calendar mismatch is normal. Older volatility observations
        # must not be presented as if they belonged to a current SPX bar.
        vix = vix_df.reindex(out.index).ffill(limit=3)
        out["VIX_Close"] = vix["Close"]
        out["VIX_SMA10"] = vix.get("SMA10")
        out["VIX_EMA21"] = vix.get("EMA21")
        out["VIX_Ret_5d"] = vix.get("Ret_5d")
        out["VIX_PctRank252"] = vix.get("PctRank252")
        out["VIX_Pct_Above_SMA10"] = vix.get("Pct_Above_SMA10")
        out["VIX_Panic_Overextension"] = vix.get("Panic_Overextension", False).fillna(False)
        out["VIX_Is_Panic"] = vix.get("Is_Panic", False).fillna(False)
        out["VIX_Is_Calm"] = vix.get("Is_Calm", False).fillna(False)
        out["VIX_Regime"] = vix.get("VIX_Regime", pd.Series(index=out.index, dtype=object)).fillna("n/a")
    else:
        out["VIX_Close"] = np.nan
        out["VIX_SMA10"] = np.nan
        out["VIX_EMA21"] = np.nan
        out["VIX_Ret_5d"] = np.nan
        out["VIX_PctRank252"] = np.nan
        out["VIX_Pct_Above_SMA10"] = np.nan
        out["VIX_Panic_Overextension"] = False
        out["VIX_Is_Panic"] = False
        out["VIX_Is_Calm"] = False
        out["VIX_Regime"] = "n/a"

    if vxx_df is not None and not vxx_df.empty:
        vxx = vxx_df.reindex(out.index).ffill(limit=3)
        out["VXX_Close"] = vxx["Close"]
        out["VXX_EMA21"] = vxx.get("EMA21")
        out["VXX_Ret_5d"] = vxx.get("Ret_5d")
        out["VXX_Stress_Confirmation"] = vxx.get("Stress_Confirmation", False).fillna(False)
        out["VXX_Carry_Decay"] = vxx.get("Carry_Decay", False).fillna(False)
        out["VXX_State"] = vxx.get("VXX_State", pd.Series(index=out.index, dtype=object)).fillna("n/a")
    else:
        out["VXX_Close"] = np.nan
        out["VXX_EMA21"] = np.nan
        out["VXX_Ret_5d"] = np.nan
        out["VXX_Stress_Confirmation"] = False
        out["VXX_Carry_Decay"] = False
        out["VXX_State"] = "n/a"

    out["Fragile_Rally"] = (
        (out["SPX_Ret_5d"] > 0)
        & (
            out["VXX_Stress_Confirmation"]
            | (out["VIX_Ret_5d"] > 0)
            | ((out["VXX_Ret_5d"] > 0.03) & (out["VIX_PctRank252"] > 0.55))
        )
    ).fillna(False)

    conditions = [
        out["VIX_Is_Panic"] & out["VXX_Stress_Confirmation"],
        out["VIX_Is_Panic"] & ~out["VXX_Stress_Confirmation"],
        out["Fragile_Rally"],
        out["VIX_Is_Calm"] & out["VXX_Carry_Decay"] & (out["SPX_Ret_5d"] > 0),
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
        vix_sma10=_safe_float(row.get("VIX_SMA10")),
        vix_ema21=_safe_float(row.get("VIX_EMA21")),
        vix_ret_5d=_safe_float(row.get("VIX_Ret_5d")),
        vix_pct_rank_252=_safe_float(row.get("VIX_PctRank252")),
        vix_pct_above_sma10=_safe_float(row.get("VIX_Pct_Above_SMA10")),
        vix_panic_overextension=bool(row.get("VIX_Panic_Overextension", False)),
        vix_regime=str(row.get("VIX_Regime") or "n/a"),
        vxx_close=_safe_float(row.get("VXX_Close")),
        vxx_ema21=_safe_float(row.get("VXX_EMA21")),
        vxx_ret_5d=_safe_float(row.get("VXX_Ret_5d")),
        vxx_state=str(row.get("VXX_State") or "n/a"),
        vxx_stress_confirmation=bool(row.get("VXX_Stress_Confirmation", False)),
        vxx_carry_decay=bool(row.get("VXX_Carry_Decay", False)),
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


def _vix_overextension_detail(latest: VolatilityDashboardPoint) -> str:
    if latest.vix_close is None or latest.vix_pct_above_sma10 is None:
        return "Keine ausreichenden VIX-Daten für den Abstand zur 10-Tage-Linie"
    detail = f"VIX {latest.vix_close:.1f} liegt {latest.vix_pct_above_sma10:+.1f}% zur 10-Tage-Linie"
    if latest.vix_panic_overextension:
        return f"{detail} · >20% spricht oft für Panik-Übertreibung und mögliche Gegenbewegung"
    return f"{detail} · keine Panik-Überdehnung"


def _tone_for_vix_regime(regime: str) -> str:
    if regime == "Stress":
        return "bad"
    if regime == "Ruhig":
        return "good"
    if regime == "Neutral":
        return "neutral"
    return "neutral"


def _vxx_detail(latest: VolatilityDashboardPoint) -> str:
    if latest.vxx_close is None:
        return "Keine VXX-Daten verfügbar"
    if latest.vxx_stress_confirmation:
        return f"VXX {latest.vxx_close:.1f} liegt über einer steigenden 21-Tage-Linie · Risiko drosseln"
    if latest.vxx_carry_decay:
        return f"VXX {latest.vxx_close:.1f} liegt unter einer fallenden 21-Tage-Linie · Volatilität entspannt"
    return f"VXX {latest.vxx_close:.1f} · keine klare 21-Tage-Bestätigung"


def _volatility_detail(regime: str) -> str:
    return {
        "Risk Off bestätigt": "VIX und VXX ziehen gleichzeitig an",
        "Kurzer Volatilitätsschock": "VIX springt an, Futures bestätigen aber nicht voll",
        "Fragile Rally": "Aktienmarkt steigt, Volatilität bleibt aber zu fest",
        "Risk On / ruhig": "Ruhiges Umfeld mit entspannendem VXX",
    }.get(regime, "Keine klare Volatilitätslage")


def _tone_for_volatility_regime(regime: str) -> str:
    if regime == "Risk Off bestätigt":
        return "bad"
    if regime in {"Kurzer Volatilitätsschock", "Fragile Rally"}:
        return "warning"
    if regime == "Risk On / ruhig":
        return "good"
    return "neutral"
