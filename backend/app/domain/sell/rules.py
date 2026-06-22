"""UI-independent sell-rule engine.

The engine deliberately separates feature detection from strategy decisions:
1. Detect all configured sell features for emergency, offensive and defensive selling.
2. Apply the selected per-stock strategy to those features.
3. Emit the legacy signal lists as compatibility output for ranking/diagnostics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import math

import pandas as pd


ALLOWED_RECOMMENDATION_LEVELS = [0, 25, 33, 50, 66, 75, 100]
BEARISH_MARKET_LABEL = "Bärisch"
DEFENSIVE_MODE = "Defensiv verkaufen: Verluste begrenzen"
STRENGTH_OFFENSIVE_MODE = "Offensiv verkaufen: Stärke/Überdehnung in Tranchen sichern"
STRENGTH_DEFENSIVE_MODE = "Defensiv verkaufen: Trend- und Einstandsrisiko reduzieren"
LOSS_LIMIT_STYLE = "Nothalt"
STRENGTH_OFFENSIVE_STYLE = "Gewinn in Stärke mitnehmen"
STRENGTH_DEFENSIVE_STYLE = "Gewinn nach Rückzug sichern"

SELL_STRATEGY_LABELS = {
    "custom": "Benutzerdefinierte Verkaufsstrategie",
    "rs_line": "RS-Linie mit 21/50-Durchschnitt",
    "ema21_risk_averse": "21-EMA-Bruch risikoavers",
    "ema21_offensive": "21-EMA-Bruch offensiv",
    "peak_drawdown": "Starker Rückgang vom 20-Tage-Hoch",
    "buy_day_low": "Unterschreitung des Kauftags",
    "ma_breaks": "Bruch gleitender Durchschnitte",
}
SELL_STRATEGY_DESCRIPTIONS = {
    "custom": "Nutzt die pro Aktie konfigurierten Merkmale und Tranche-Prozente. Ohne Setup gelten robuste Defaults.",
    "rs_line": "Teilverkauf in drei Stufen, wenn die Relative-Stärke-Linie ihre 21- und 50-Tage-Linien verliert.",
    "ema21_risk_averse": "Frühe Tranchen bei erstem Bruch der 21-EMA, schwachem Folgetag und fortgesetztem Bruch.",
    "ema21_offensive": "Geduldiger: erste Tranche erst nach drei Schlüssen unter der 21-EMA.",
    "peak_drawdown": "Sichert Gewinner über Rückgangsstufen vom 20-Tage-Hoch und Trendbrüche.",
    "buy_day_low": "Überwacht das Tief des Kauftags und das Tief des Vortags vor dem Kauf.",
    "ma_breaks": "Erste Tranche nach bestätigtem 50-SMA-Bruch, finale Tranche beim 200-SMA-Bruch.",
}

# Compatibility exports for the previous Hub option layer. They are no longer used
# to run the decision engine, but keeping the names avoids breaking imports.
LM_HUB_STRATEGIES_ALL = list(SELL_STRATEGY_LABELS)
LM_HUB_WARNUNGEN = [
    "offensive_low_closes",
    "offensive_loss_days_cluster",
    "offensive_stall_days",
]
LM_HUB_STRATEGIEN = [key for key in LM_HUB_STRATEGIES_ALL if key not in LM_HUB_WARNUNGEN]
LM_HUB_STRATEGIEN_DEFAULT = ["custom"]
LM_HUB_WARNUNGEN_DEFAULT = []
LM_HUB_PROFILE_DEFAULT = "custom"
LM_HUB_PROFILES: dict[str, dict[str, object]] = {
    key: {
        "label": label,
        "beschreibung": SELL_STRATEGY_DESCRIPTIONS.get(key, ""),
        "strategien": [key],
        "warnungen": [],
    }
    for key, label in SELL_STRATEGY_LABELS.items()
}
LM_HUB_STRATEGIES_DEFAULT = LM_HUB_STRATEGIEN_DEFAULT + LM_HUB_WARNUNGEN_DEFAULT
LM_HUB_STRATEGIES = LM_HUB_STRATEGIES_DEFAULT

DEFAULT_CUSTOM_STRATEGY_STEPS = [
    {"feature_id": "offensive_profit_target", "tranche_percent": 25},
    {"feature_id": "offensive_ema21_break", "tranche_percent": 50},
    {"feature_id": "offensive_peak_drop", "tranche_percent": 25},
    {"feature_id": "emergency_loss_limit", "tranche_percent": 100},
]

LEGACY_CUSTOM_STRATEGY_STEPS = [
    {"feature_id": "offensive_profit_target", "tranche_percent": 25},
    {"feature_id": "offensive_ema21_break", "tranche_percent": 50},
    {"feature_id": "offensive_peak_drop", "tranche_percent": 25},
    {"feature_id": "offensive_ma_extension_sma10", "tranche_percent": 20},
    {"feature_id": "offensive_ma_extension_ema21", "tranche_percent": 25},
    {"feature_id": "offensive_ma_extension_sma50", "tranche_percent": 33},
    {"feature_id": "offensive_ma_extension_sma200", "tranche_percent": 100},
    {"feature_id": "offensive_biggest_gain", "tranche_percent": 33},
    {"feature_id": "offensive_stall_days", "tranche_percent": 20},
    {"feature_id": "defensive_buy_day_low", "tranche_percent": 50},
    {"feature_id": "defensive_previous_day_low", "tranche_percent": 50},
    {"feature_id": "defensive_ma_break_50", "tranche_percent": 50},
    {"feature_id": "defensive_ma_break_200", "tranche_percent": 100},
    {"feature_id": "emergency_loss_limit", "tranche_percent": 100},
]

DEFAULT_SELL_RULE_SETUP: dict[str, Any] = {
    "strategy_key": "custom",
    "emergency_stop_unit": "pct",
    "emergency_stop_value": 7.0,
    "profit_target_unit": "pct",
    "profit_target_value": 20.0,
    "ema21_break_unit": "pct",
    "ema21_break_value": 2.0,
    "peak_drop_unit": "pct",
    "peak_drop_value": 8.0,
    "ma_extension_unit": "pct",
    "ma_extension_sma200_pct": 70.0,
    "ma_extension_ema21_pct": 15.0,
    "ma_extension_sma10_pct": 10.0,
    "ma_extension_sma50_pct": 25.0,
    "low_closes_window": 10,
    "low_closes_count": 4,
    "sharp_drop_unit": "pct",
    "sharp_drop_value": 6.0,
    "sharp_drop_reclaim_days": 4,
    "loss_days_window": 10,
    "biggest_gain_unit": "pct",
    "biggest_gain_value": 10.0,
    "biggest_gain_multiplier": 1.5,
    "biggest_gain_lookback": 20,
    "stall_days_window": 10,
    "stall_days_count": 3,
    "stall_days_max_change_pct": 1.0,
    "stall_days_volume_ratio": 1.3,
    "buy_day_reclaim_days": 3,
    "ma_break_reclaim_days": 3,
    "loss_weeks_count": 3,
    "loss_weeks_require_rising_volume": False,
    "worst_drop_warmup_days": 20,
    "worst_drop_warmup_weeks": 4,
    "rs_tranche_1_pct": 25,
    "rs_tranche_2_pct": 25,
    "rs_tranche_3_pct": 50,
    "ema21_risk_averse_first_pct": 25,
    "ema21_risk_averse_second_pct": 25,
    "ema21_risk_averse_third_pct": 25,
    "ema21_offensive_first_pct": 33,
    "peak_drawdown_first_unit": "pct",
    "peak_drawdown_first_value": 8.0,
    "peak_drawdown_second_unit": "pct",
    "peak_drawdown_second_value": 15.0,
    "peak_drawdown_first_pct": 25,
    "peak_drawdown_second_pct": 25,
    "custom_strategy_steps": DEFAULT_CUSTOM_STRATEGY_STEPS,
}
LM_HUB_DEFAULTS = dict(DEFAULT_SELL_RULE_SETUP)

BOOK_REFERENCES = {
    "emergency_loss_limit": "Nothalt: definierte Verlusthöhe",
    "offensive_profit_target": "Offensiv: festgelegter Gewinn",
    "offensive_ema21_break": "Offensiv: deutlicher Bruch der 21-EMA",
    "offensive_peak_drop": "Offensiv: starker Preisrückgang vom 20-Tage-Hoch",
    "offensive_ma_extension_sma10": "Offensiv: Rückfall nach Überdehnung über 10-SMA",
    "offensive_ma_extension_ema21": "Offensiv: Rückfall nach Überdehnung über 21-EMA",
    "offensive_ma_extension_sma50": "Offensiv: Rückfall nach Überdehnung über 50-SMA",
    "offensive_ma_extension_sma200": "Offensiv: Rückfall nach Überdehnung über 200-SMA",
    "offensive_low_closes": "Offensiv: viele Schlusskurse im unteren Kerzendrittel",
    "offensive_sharp_drop_no_reclaim": "Offensiv: scharfer Einbruch ohne schnelle Rückeroberung",
    "offensive_loss_days_cluster": "Offensiv: Häufung von Verlusttagen",
    "offensive_biggest_gain": "Offensiv: außergewöhnlich großer Gewinn-Tag mit Volumen",
    "offensive_stall_days": "Offensiv: gehäufte Stau-Tage",
    "offensive_buy_price_reached": "Offensiv: Rückfall auf Kaufpreis",
    "defensive_buy_day_low": "Defensiv: Tief des Kauftags unterschritten",
    "defensive_previous_day_low": "Defensiv: Tief vor dem Kauftag unterschritten",
    "defensive_ma_break_10": "Defensiv: 10-SMA nicht zurückerobert",
    "defensive_ma_break_21": "Defensiv: 21-EMA nicht zurückerobert",
    "defensive_ma_break_50": "Defensiv: 50-SMA nicht zurückerobert",
    "defensive_ma_break_200": "Defensiv: 200-SMA nicht zurückerobert",
    "defensive_loss_weeks": "Defensiv: mehrere Verlustwochen in Folge",
    "defensive_worst_daily_drop": "Defensiv: größter Tagesverlust seit Kauf",
    "defensive_worst_weekly_drop": "Defensiv: größter Wochenverlust seit Kauf",
}


@dataclass(frozen=True)
class RuleSignal:
    id: str
    label: str
    contribution_percent: int = 0
    book_reference: str = ""
    signal_date: str = ""
    event_note: str = ""
    sell_mode: str = ""
    sell_style: str = ""
    strategy_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleFeature:
    id: str
    category: Literal["emergency", "offensive", "defensive"]
    label: str
    active: bool = False
    severity: Literal["inactive", "watch", "warning", "tranche", "killer"] = "inactive"
    value: str = ""
    threshold: str = ""
    detail: str = ""
    signal_date: str = ""
    contribution_percent: int = 0
    strategy_key: str = ""
    setup: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyRecommendation:
    id: str
    label: str
    active: bool = False
    tranche_percent: int = 0
    detail: str = ""
    trigger: str = ""
    feature_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_profile_strategies(profile_key: str) -> tuple[list[str], list[str]]:
    profile = LM_HUB_PROFILES.get(str(profile_key or "").strip().lower())
    if not profile:
        profile = LM_HUB_PROFILES[LM_HUB_PROFILE_DEFAULT]
    return list(profile.get("strategien") or []), list(profile.get("warnungen") or [])


def _safe_float(value, default=None):
    if value is None:
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
    except Exception:
        pass
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def _safe_int(value, default: int = 0) -> int:
    parsed = _safe_float(value)
    if parsed is None:
        return int(default)
    return int(parsed)


def _safe_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ja", "on", "x"}
    return bool(value)


def _metric(metrics: dict, key: str, default=None):
    return _safe_float(metrics.get(key), default)


def _extract_inputs(metrics_payload: dict) -> tuple[dict, str, float, float]:
    if not isinstance(metrics_payload, dict):
        return {}, "", 0.0, 0.0
    metrics = metrics_payload.get("metrics") if isinstance(metrics_payload.get("metrics"), dict) else metrics_payload
    ticker = str(metrics_payload.get("ticker") or "").upper().strip()
    buy_price = _safe_float(metrics_payload.get("buy_price"), _safe_float(metrics.get("buy_price"), 0.0)) or 0.0
    shares = _safe_float(metrics_payload.get("shares"), _safe_float(metrics.get("shares"), 0.0)) or 0.0
    return metrics, ticker, buy_price, shares


def normalize_sell_setup_payload(raw_setup: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw_setup, dict):
        return {}
    setup = dict(raw_setup)
    if _strategy_steps_equal(setup.get("custom_strategy_steps"), LEGACY_CUSTOM_STRATEGY_STEPS):
        setup["custom_strategy_steps"] = [dict(item) for item in DEFAULT_CUSTOM_STRATEGY_STEPS]
    return setup


def _strategy_steps_equal(raw_steps: Any, expected_steps: list[dict[str, Any]]) -> bool:
    if not isinstance(raw_steps, list) or len(raw_steps) != len(expected_steps):
        return False
    for raw_step, expected_step in zip(raw_steps, expected_steps, strict=True):
        if not isinstance(raw_step, dict):
            return False
        feature_id = str(raw_step.get("feature_id") or "").strip()
        try:
            tranche_percent = int(float(raw_step.get("tranche_percent", -1)))
        except (TypeError, ValueError):
            return False
        if feature_id != expected_step["feature_id"] or tranche_percent != int(expected_step["tranche_percent"]):
            return False
    return True


def _manual_value(manual_data: dict, metrics_payload: dict, key: str):
    if isinstance(manual_data, dict) and manual_data.get(key) not in (None, ""):
        return manual_data.get(key)
    defaults = metrics_payload.get("manual_defaults", {}) if isinstance(metrics_payload, dict) else {}
    if isinstance(defaults, dict):
        return defaults.get(key)
    return None


def _resolve_setup(metrics_payload: dict, manual_data: dict | None) -> dict:
    setup = dict(DEFAULT_SELL_RULE_SETUP)
    # Keep nested lists/dicts independent from defaults.
    setup["custom_strategy_steps"] = [dict(item) for item in DEFAULT_CUSTOM_STRATEGY_STEPS]
    manual_setup = (manual_data or {}).get("sell_setup") if isinstance(manual_data, dict) else None
    if isinstance(manual_setup, dict):
        setup.update(normalize_sell_setup_payload(manual_setup))
    payload_setup = (metrics_payload or {}).get("lm_setup") if isinstance(metrics_payload, dict) else None
    if isinstance(payload_setup, dict):
        setup.update(normalize_sell_setup_payload(payload_setup))
    setup = normalize_sell_setup_payload(setup)
    strategy_key = str(setup.get("strategy_key") or setup.get("active_strategy") or setup.get("profile") or "custom").strip()
    if strategy_key not in SELL_STRATEGY_LABELS:
        strategy_key = "custom"
    setup["strategy_key"] = strategy_key
    return setup


def _frame(metrics_payload: dict, key: str) -> pd.DataFrame:
    ohlc = metrics_payload.get("ohlc_frames", {}) if isinstance(metrics_payload, dict) else {}
    frame = ohlc.get(key) if isinstance(ohlc, dict) else None
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    out = frame.copy()
    out.columns = [str(col).lower() for col in out.columns]
    required = ["open", "high", "low", "close", "volume"]
    for col in required:
        if col not in out.columns:
            out[col] = pd.Series(dtype=float)
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")
        out = out[out.index.notna()]
    return out.sort_index().dropna(subset=["close"])


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if not isinstance(frame, pd.DataFrame) or column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _sma(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window, min_periods=window).mean()


def _ema(series: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").ewm(span=window, adjust=False, min_periods=window).mean()


def _trailing_true_count(mask: pd.Series) -> int:
    if mask is None or mask.empty:
        return 0
    count = 0
    for value in mask.fillna(False).iloc[::-1]:
        if bool(value):
            count += 1
        else:
            break
    return int(count)


def _first_true_date(mask: pd.Series) -> str:
    if mask is None or mask.empty:
        return ""
    valid = mask.fillna(False)
    if not valid.any():
        return ""
    try:
        return pd.Timestamp(valid[valid].index[0]).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _last_true_date(mask: pd.Series) -> str:
    if mask is None or mask.empty:
        return ""
    valid = mask.fillna(False)
    if not valid.any():
        return ""
    try:
        return pd.Timestamp(valid[valid].index[-1]).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _last_date(frame_or_series) -> str:
    if frame_or_series is None or len(frame_or_series) == 0:
        return ""
    try:
        return pd.Timestamp(frame_or_series.index[-1]).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _fmt_pct(value, digits: int = 1) -> str:
    parsed = _safe_float(value)
    return "-" if parsed is None else f"{parsed:.{digits}f}%"


def _fmt_price(value) -> str:
    parsed = _safe_float(value)
    return "-" if parsed is None else f"{parsed:.2f}"


def _fmt_count(value: int, total: int | None = None) -> str:
    return f"{int(value)}/{int(total)}" if total is not None else str(int(value))


def _threshold_label(unit: str, value: float) -> str:
    clean_unit = str(unit or "pct").lower()
    if clean_unit == "atr":
        return f"{value:g} ATR"
    return f"{value:g}%"


def _threshold_crossed(*, distance_pct: float | None, distance_abs: float | None, atr: float | None, unit: str, value: float) -> bool:
    if str(unit or "pct").lower() == "atr":
        return atr is not None and atr > 0 and distance_abs is not None and distance_abs >= atr * value
    return distance_pct is not None and distance_pct >= value


def _feature(
    feature_id: str,
    category: Literal["emergency", "offensive", "defensive"],
    label: str,
    *,
    active: bool,
    severity: Literal["watch", "warning", "tranche", "killer"] = "warning",
    value: str = "",
    threshold: str = "",
    detail: str = "",
    signal_date: str = "",
    contribution_percent: int = 0,
    strategy_key: str = "",
    setup: dict[str, Any] | None = None,
) -> RuleFeature:
    return RuleFeature(
        id=feature_id,
        category=category,
        label=label,
        active=bool(active),
        severity=severity if active else "inactive",
        value=str(value or ""),
        threshold=str(threshold or ""),
        detail=str(detail or ""),
        signal_date=str(signal_date or ""),
        contribution_percent=int(contribution_percent or 0),
        strategy_key=strategy_key or feature_id,
        setup=dict(setup or {}),
    )


def _signal_from_feature(feature: RuleFeature, *, contribution: int | None = None, strategy_key: str = "") -> RuleSignal:
    pct = int(feature.contribution_percent if contribution is None else contribution)
    return RuleSignal(
        id=feature.id,
        label=feature.label,
        contribution_percent=pct,
        book_reference=BOOK_REFERENCES.get(feature.id, ""),
        signal_date=feature.signal_date,
        event_note=feature.detail or feature.value or feature.threshold,
        sell_mode=_sell_mode_for_category(feature.category),
        sell_style=_sell_style_for_category(feature.category),
        strategy_key=strategy_key or feature.strategy_key or feature.id,
    )


def _signal_from_recommendation(recommendation: StrategyRecommendation, features_by_id: dict[str, RuleFeature], strategy_key: str) -> RuleSignal:
    feature = next((features_by_id.get(feature_id) for feature_id in recommendation.feature_ids if features_by_id.get(feature_id)), None)
    return RuleSignal(
        id=recommendation.id,
        label=recommendation.label,
        contribution_percent=int(recommendation.tranche_percent),
        book_reference=BOOK_REFERENCES.get(feature.id if feature else recommendation.id, ""),
        signal_date=feature.signal_date if feature else "",
        event_note=recommendation.detail or recommendation.trigger,
        sell_mode=_sell_mode_for_category(feature.category if feature else "offensive"),
        sell_style=_sell_style_for_category(feature.category if feature else "offensive"),
        strategy_key=strategy_key,
    )


def _sell_mode_for_category(category: str) -> str:
    if category == "emergency":
        return DEFENSIVE_MODE
    if category == "defensive":
        return STRENGTH_DEFENSIVE_MODE
    return STRENGTH_OFFENSIVE_MODE


def _sell_style_for_category(category: str) -> str:
    if category == "emergency":
        return LOSS_LIMIT_STYLE
    if category == "defensive":
        return STRENGTH_DEFENSIVE_STYLE
    return STRENGTH_OFFENSIVE_STYLE


def _floor_allowed(value: float) -> int:
    value = max(0.0, min(100.0, float(value or 0.0)))
    candidates = [level for level in ALLOWED_RECOMMENDATION_LEVELS if level <= value]
    return max(candidates) if candidates else 0


def _next_allowed(value: int) -> int:
    for level in ALLOWED_RECOMMENDATION_LEVELS:
        if level > value:
            return level
    return 100


def _sum_already_sold(ticker: str, tranche_log: list[dict] | None) -> float:
    clean_ticker = str(ticker or "").upper().strip()
    total = 0.0
    for entry in tranche_log or []:
        if not isinstance(entry, dict):
            continue
        entry_ticker = str(entry.get("ticker") or clean_ticker).upper().strip()
        if clean_ticker and entry_ticker and entry_ticker != clean_ticker:
            continue
        pct = _safe_float(entry.get("tranche_percent"), _safe_float(entry.get("pct"), 0.0)) or 0.0
        if pct > 0:
            total += pct
    return max(0.0, min(100.0, total))


def _regime(pnl_pct: float | None, market_environment: str) -> str:
    pnl = _safe_float(pnl_pct, 0.0) or 0.0
    if pnl < 0:
        return "Defensiv"
    if str(market_environment) == BEARISH_MARKET_LABEL and pnl >= 10:
        return "Erste Gewinnmitnahme"
    if pnl < 15:
        return "Schutz"
    if pnl < 25:
        return "Erste Gewinnmitnahme"
    if pnl <= 80:
        return "Trailing"
    return "Großgewinner"


def _build_stop_price(setup: dict, buy_price: float, atr: float | None) -> float | None:
    unit = str(setup.get("emergency_stop_unit") or "pct")
    value = _safe_float(setup.get("emergency_stop_value"), 7.0) or 7.0
    if buy_price <= 0:
        return None
    if unit == "atr" and atr and atr > 0:
        return max(0.0, buy_price - atr * value)
    return buy_price * (1 - value / 100)


def _build_trigger_prices(metrics: dict, setup: dict, stop_price: float | None) -> tuple[float | None, float | None]:
    ema21 = _metric(metrics, "ema21")
    sma50 = _metric(metrics, "sma50")
    next_trigger = ema21 or sma50 or stop_price
    full_exit = sma50 or stop_price
    return next_trigger, full_exit


def compute_sell_health_score(metrics_payload: dict, manual_data: dict | None = None) -> dict[str, Any]:
    """Compute the portfolio-ranking health score from sell metrics and manual data."""
    manual_data = manual_data or {}
    metrics, _ticker, _buy_price, _shares = _extract_inputs(metrics_payload or {})
    score = 50.0
    reasons: list[str] = []

    pnl = _metric(metrics, "pnl_pct")
    if pnl is not None:
        if pnl >= 20:
            score += 12
            reasons.append("P&L >= 20%")
        elif pnl >= 10:
            score += 8
            reasons.append("P&L 10-20%")
        elif pnl >= 0:
            score += 3
            reasons.append("P&L 0-10%")
        elif pnl >= -3:
            score -= 5
            reasons.append("P&L -3-0%")
        elif pnl >= -7:
            score -= 15
            reasons.append("P&L -7--3%")
        else:
            score -= 30
            reasons.append("P&L < -7%")

    current = _metric(metrics, "current_price")
    ema21 = _metric(metrics, "ema21")
    sma50 = _metric(metrics, "sma50")
    low_day_1 = _safe_float(_manual_value(manual_data, metrics_payload or {}, "low_day_1"))

    if current is not None and ema21 is not None:
        if current >= ema21:
            score += 8
            reasons.append("Kurs >= 21-EMA")
        else:
            score -= 12
            reasons.append("Kurs < 21-EMA")
    if current is not None and sma50 is not None:
        if current >= sma50:
            score += 6
            reasons.append("Kurs >= 50-MA")
        elif current >= sma50 * 0.98:
            score -= 5
            reasons.append("Kurs knapp unter 50-MA")
        else:
            score -= 20
            reasons.append("Kurs < 50-MA -2%")
    if current is not None and low_day_1 is not None and current < low_day_1:
        score -= 15
        reasons.append("Schluss unter Tief Tag 1")

    drawdown = abs(_metric(metrics, "drawdown_from_high_since_buy_pct", 0.0) or 0.0)
    if drawdown >= 15:
        score -= 15
        reasons.append("Drawdown >= 15%")
    elif drawdown >= 12:
        score -= 10
        reasons.append("Drawdown 12-15%")
    elif drawdown >= 8:
        score -= 5
        reasons.append("Drawdown 8-12%")

    rs_line = _metric(metrics, "rs_line")
    rs_ma21 = _metric(metrics, "rs_ma21")
    rs_ma50 = _metric(metrics, "rs_ma50")
    days_under_rs21 = int(_metric(metrics, "days_under_rs_ma21", 0) or 0)
    if rs_line is not None and rs_ma21 is not None and rs_ma50 is not None:
        if rs_line >= rs_ma21 and rs_line >= rs_ma50 and days_under_rs21 == 0:
            rs_trend = "hoch"
            score += 10
            reasons.append("RS hoch")
        elif rs_line < rs_ma21 or rs_line < rs_ma50 or days_under_rs21 >= 3:
            rs_trend = "runter"
            score -= 12
            reasons.append("RS runter/unter MAs")
        else:
            rs_trend = "seitwärts"
    else:
        rs_trend = "seitwärts"

    dist_days = int(_metric(metrics, "distribution_days_25", 0) or 0)
    if dist_days >= 6:
        score -= 15
        reasons.append("Distribution >= 6")
    elif dist_days >= 4:
        score -= 8
        reasons.append("Distribution 4-5")
    elif dist_days >= 2:
        score -= 3
        reasons.append("Distribution 2-3")

    score = max(0.0, min(100.0, score))
    if score >= 65:
        status = "Halten"
    elif score >= 40:
        status = "Beobachten"
    else:
        status = "Verkaufen"
    return {"health_score": round(score, 1), "status": status, "rs_trend": rs_trend, "reasons": reasons}


HYSTERESIS_MIN_CONTRIBUTION = 33
HYSTERESIS_MIN_CONSECUTIVE_DAYS = 2
HYSTERESIS_BYPASS_CONTRIBUTION = 75


def _normalize_state_date(value) -> str:
    if value in (None, ""):
        return ""
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value).strip()


def _compute_recommendation_status(
    *,
    sell_now: int,
    has_killer: bool,
    as_of_date: str,
    prior_state: dict | None,
) -> tuple[str, dict]:
    today = _normalize_state_date(as_of_date) or _normalize_state_date(pd.Timestamp.now())
    state = dict(prior_state or {})
    next_state: dict[str, Any] = {
        "last_seen_date": today,
        "last_pct": int(sell_now),
        "consecutive_days": 1,
        "snoozed_until": state.get("snoozed_until") or "",
        "snoozed_pct": int(state.get("snoozed_pct") or 0),
    }
    if has_killer:
        next_state["snoozed_until"] = ""
        next_state["snoozed_pct"] = 0
        return "scharf", next_state
    if sell_now <= 0:
        next_state["consecutive_days"] = 0
        return "halten", next_state
    snoozed_until = _normalize_state_date(state.get("snoozed_until"))
    snoozed_pct = int(state.get("snoozed_pct") or 0)
    if snoozed_until and snoozed_until >= today and sell_now <= snoozed_pct:
        next_state["snoozed_until"] = snoozed_until
        next_state["snoozed_pct"] = snoozed_pct
        return "snoozed", next_state
    if snoozed_until and (snoozed_until < today or sell_now > snoozed_pct):
        next_state["snoozed_until"] = ""
        next_state["snoozed_pct"] = 0
    prior_pct = int(state.get("last_pct") or 0)
    prior_date = _normalize_state_date(state.get("last_seen_date"))
    prior_streak = int(state.get("consecutive_days") or 0)
    if prior_date == today:
        next_state["consecutive_days"] = max(1, prior_streak)
    elif prior_pct == sell_now and prior_date:
        next_state["consecutive_days"] = prior_streak + 1
    else:
        next_state["consecutive_days"] = 1
    if sell_now < HYSTERESIS_MIN_CONTRIBUTION or sell_now >= HYSTERESIS_BYPASS_CONTRIBUTION:
        return "scharf", next_state
    if next_state["consecutive_days"] >= HYSTERESIS_MIN_CONSECUTIVE_DAYS:
        return "scharf", next_state
    return "in_bestaetigung", next_state


def _detect_emergency_features(
    metrics_payload: dict,
    manual_data: dict,
    setup: dict,
    metrics: dict,
    buy_price: float,
) -> list[RuleFeature]:
    current = _metric(metrics, "current_price")
    atr = _metric(metrics, "atr14")
    unit = str(setup.get("emergency_stop_unit") or "pct")
    value = _safe_float(setup.get("emergency_stop_value"), 7.0) or 7.0
    distance_abs = (buy_price - current) if current is not None and buy_price > 0 else None
    distance_pct = (distance_abs / buy_price * 100) if distance_abs is not None and buy_price > 0 else None
    active = _threshold_crossed(distance_pct=distance_pct, distance_abs=distance_abs, atr=atr, unit=unit, value=value)
    as_of = str(metrics_payload.get("as_of") or metrics.get("as_of_date") or "")
    return [
        _feature(
            "emergency_loss_limit",
            "emergency",
            "Verkauf nach definierter Verlusthöhe",
            active=active,
            severity="killer",
            value=f"Verlust {_fmt_pct(distance_pct)}" if distance_pct is not None else "kein Verlust",
            threshold=_threshold_label(unit, value),
            detail="Nothalt greift sofort, wenn die pro Aktie definierte Verlusthöhe erreicht wird.",
            signal_date=as_of if active else "",
            contribution_percent=100,
            setup={"unit": unit, "value": value},
        )
    ]


def _detect_offensive_features(
    metrics_payload: dict,
    setup: dict,
    metrics: dict,
    buy_price: float,
) -> list[RuleFeature]:
    daily = _frame(metrics_payload, "daily_since_buy")
    close = _series(daily, "close")
    high = _series(daily, "high")
    low = _series(daily, "low")
    volume = _series(daily, "volume")
    current = _metric(metrics, "current_price")
    atr = _metric(metrics, "atr14")
    as_of = str(metrics_payload.get("as_of") or metrics.get("as_of_date") or _last_date(daily))
    features: list[RuleFeature] = []

    # 1. Fixed profit target.
    profit_unit = str(setup.get("profit_target_unit") or "pct")
    profit_value = _safe_float(setup.get("profit_target_value"), 20.0) or 20.0
    profit_abs = (current - buy_price) if current is not None and buy_price > 0 else None
    profit_pct = (profit_abs / buy_price * 100) if profit_abs is not None and buy_price > 0 else None
    profit_active = _threshold_crossed(distance_pct=profit_pct, distance_abs=profit_abs, atr=atr, unit=profit_unit, value=profit_value)
    features.append(_feature(
        "offensive_profit_target",
        "offensive",
        "Verkauf bei festgelegtem Gewinn",
        active=profit_active,
        severity="tranche",
        value=f"Gewinn {_fmt_pct(profit_pct)}",
        threshold=_threshold_label(profit_unit, profit_value),
        detail="Gewinnschwelle erreicht; Strategie kann eine Teiltranche vorschlagen.",
        signal_date=as_of if profit_active else "",
        contribution_percent=25,
        setup={"unit": profit_unit, "value": profit_value},
    ))

    # 2. Clear 21 EMA break.
    ema21 = _metric(metrics, "ema21")
    ema_unit = str(setup.get("ema21_break_unit") or "pct")
    ema_value = _safe_float(setup.get("ema21_break_value"), 2.0) or 2.0
    ema_distance_abs = (ema21 - current) if current is not None and ema21 is not None else None
    ema_distance_pct = (ema_distance_abs / ema21 * 100) if ema_distance_abs is not None and ema21 and ema21 > 0 else None
    ema_active = bool(current is not None and ema21 is not None and current < ema21 and _threshold_crossed(
        distance_pct=ema_distance_pct,
        distance_abs=ema_distance_abs,
        atr=atr,
        unit=ema_unit,
        value=ema_value,
    ))
    features.append(_feature(
        "offensive_ema21_break",
        "offensive",
        "Bruch der 21-Tage-Linie",
        active=ema_active,
        severity="tranche",
        value=f"{_fmt_pct(ema_distance_pct)} unter 21-EMA" if ema_distance_pct is not None and current is not None and ema21 is not None and current < ema21 else "über/nahe 21-EMA",
        threshold=_threshold_label(ema_unit, ema_value),
        detail=f"{int(_metric(metrics, 'days_under_ema21', 0) or 0)} Tage unter 21-EMA.",
        signal_date=str(metrics.get("under_ema21_start_date") or as_of) if ema_active else "",
        contribution_percent=50,
        setup={"unit": ema_unit, "value": ema_value},
    ))

    # 3. Drawdown from 20-day high.
    peak_unit = str(setup.get("peak_drop_unit") or "pct")
    peak_value = _safe_float(setup.get("peak_drop_value"), 8.0) or 8.0
    high20 = _safe_float(high.tail(20).max()) if not high.empty else None
    peak_abs = (high20 - current) if current is not None and high20 and high20 > 0 else None
    peak_pct = (peak_abs / high20 * 100) if peak_abs is not None and high20 and high20 > 0 else None
    peak_active = _threshold_crossed(distance_pct=peak_pct, distance_abs=peak_abs, atr=atr, unit=peak_unit, value=peak_value)
    features.append(_feature(
        "offensive_peak_drop",
        "offensive",
        "Starker Preisrückgang vom Peak",
        active=peak_active,
        severity="tranche",
        value=f"{_fmt_pct(peak_pct)} unter 20T-Hoch",
        threshold=_threshold_label(peak_unit, peak_value),
        detail=f"20T-Hoch {_fmt_price(high20)}; Abstand wird laufend mitgeführt.",
        signal_date=as_of if peak_active else "",
        contribution_percent=25,
        setup={"unit": peak_unit, "value": peak_value},
    ))

    # 4. MA extension anchors: threshold first, sell feature after anchor close is undercut.
    ma_specs = [
        ("sma10", "10-SMA", _sma(close, 10), _safe_float(setup.get("ma_extension_sma10_pct"), 10.0) or 10.0, 20),
        ("ema21", "21-EMA", _ema(close, 21), _safe_float(setup.get("ma_extension_ema21_pct"), 15.0) or 15.0, 25),
        ("sma50", "50-SMA", _sma(close, 50), _safe_float(setup.get("ma_extension_sma50_pct"), 25.0) or 25.0, 33),
        ("sma200", "200-SMA", _sma(close, 200), _safe_float(setup.get("ma_extension_sma200_pct"), 70.0) or 70.0, 100),
    ]
    for key, label, ma_series, threshold_pct, contribution in ma_specs:
        feature = _ma_extension_feature(
            key=key,
            label=label,
            close=close,
            ma_series=ma_series,
            threshold_pct=threshold_pct,
            current=current,
            as_of=as_of,
            contribution=contribution,
        )
        features.append(feature)

    # Shared candle/volume derived series.
    day_range = (high - low).replace(0, pd.NA)
    close_range = ((close - low) / day_range).clip(lower=0, upper=1)
    pct_change = close.pct_change(fill_method=None) * 100
    volume_sma50 = volume.rolling(50, min_periods=10).mean()

    # 5. Many lower-third closes.
    low_window = max(1, _safe_int(setup.get("low_closes_window"), 10))
    low_count_threshold = max(1, _safe_int(setup.get("low_closes_count"), 4))
    low_count = int((close_range <= (1 / 3)).tail(low_window).sum()) if not close_range.empty else 0
    features.append(_feature(
        "offensive_low_closes",
        "offensive",
        "Viele Tagesabschlüsse im unteren Drittel",
        active=low_count >= low_count_threshold,
        severity="warning",
        value=_fmt_count(low_count, low_window),
        threshold=f"{low_count_threshold} in {low_window} Tagen",
        detail="Schlusskurse im unteren Kerzendrittel zeigen nachlassende Nachfrage.",
        signal_date=as_of if low_count >= low_count_threshold else "",
        contribution_percent=15,
        setup={"window": low_window, "count": low_count_threshold},
    ))

    # 6. Sharp drop without quick reclaim.
    sharp_unit = str(setup.get("sharp_drop_unit") or "pct")
    sharp_value = _safe_float(setup.get("sharp_drop_value"), 6.0) or 6.0
    reclaim_days = max(1, _safe_int(setup.get("sharp_drop_reclaim_days"), 4))
    sharp = _sharp_drop_without_reclaim(daily, pct_change, atr, sharp_unit, sharp_value, reclaim_days)
    features.append(_feature(
        "offensive_sharp_drop_no_reclaim",
        "offensive",
        "Keine schnelle Rückeroberung eines scharfen Einbruchs",
        active=sharp["active"],
        severity="warning",
        value=sharp["value"],
        threshold=f"{_threshold_label(sharp_unit, sharp_value)} und Reclaim in {reclaim_days} Tagen",
        detail=sharp["detail"],
        signal_date=sharp["signal_date"],
        contribution_percent=20,
        setup={"unit": sharp_unit, "value": sharp_value, "reclaim_days": reclaim_days},
    ))

    # 7. Cluster of loss days.
    loss_window = max(2, _safe_int(setup.get("loss_days_window"), 10))
    recent_pct = pct_change.tail(loss_window)
    loss_days = int((recent_pct < 0).sum())
    gain_days = int((recent_pct > 0).sum())
    loss_active = loss_days > gain_days
    features.append(_feature(
        "offensive_loss_days_cluster",
        "offensive",
        "Häufung von Verlusttagen",
        active=loss_active,
        severity="warning",
        value=f"{loss_days} Verlusttage vs. {gain_days} Gewinntage",
        threshold=f"Verlusttage überwiegen im {loss_window}T-Fenster",
        detail="Zählt Schlusskursveränderungen im konfigurierten Fenster.",
        signal_date=as_of if loss_active else "",
        contribution_percent=15,
        setup={"window": loss_window},
    ))

    # 8. Biggest price increase with volume.
    biggest = _biggest_gain_feature(daily, pct_change, volume, volume_sma50, atr, setup, as_of)
    features.append(biggest)

    # 9. Stall days.
    stall_window = max(2, _safe_int(setup.get("stall_days_window"), 10))
    stall_count_threshold = max(1, _safe_int(setup.get("stall_days_count"), 3))
    max_change = _safe_float(setup.get("stall_days_max_change_pct"), 1.0) or 1.0
    volume_ratio = _safe_float(setup.get("stall_days_volume_ratio"), 1.3) or 1.3
    stall_mask = (pct_change.abs() <= max_change) & (volume >= volume_sma50 * volume_ratio) & (close_range <= 0.55)
    stall_count = int(stall_mask.tail(stall_window).sum()) if not stall_mask.empty else 0
    stall_active = stall_count >= stall_count_threshold
    features.append(_feature(
        "offensive_stall_days",
        "offensive",
        "Gehäufte Stautage",
        active=stall_active,
        severity="warning",
        value=_fmt_count(stall_count, stall_window),
        threshold=f"{stall_count_threshold} Stautage in {stall_window} Tagen",
        detail=f"Tagesänderung <= {max_change:g}%, Volumen >= {volume_ratio:g}x 50T-Schnitt, Close in unterer Hälfte.",
        signal_date=_last_true_date(stall_mask.tail(stall_window)) if stall_active else "",
        contribution_percent=20,
        setup={"window": stall_window, "count": stall_count_threshold, "max_change_pct": max_change, "volume_ratio": volume_ratio},
    ))

    # 10. Back to buy price.
    high_since_buy = _metric(metrics, "high_since_buy")
    buy_price_active = bool(current is not None and buy_price > 0 and current <= buy_price and high_since_buy and high_since_buy > buy_price * 1.03)
    features.append(_feature(
        "offensive_buy_price_reached",
        "offensive",
        "Erreichen des Kaufpreises",
        active=buy_price_active,
        severity="tranche",
        value=f"Kurs {_fmt_price(current)} vs. Kauf {_fmt_price(buy_price)}",
        threshold="Schlusskurs <= Kaufpreis nach vorherigem Gewinn",
        detail="Gewinn ist wieder bis zum Einstand zurückgelaufen.",
        signal_date=as_of if buy_price_active else "",
        contribution_percent=50,
        setup={},
    ))
    return features


def _ma_extension_feature(
    *,
    key: str,
    label: str,
    close: pd.Series,
    ma_series: pd.Series,
    threshold_pct: float,
    current: float | None,
    as_of: str,
    contribution: int,
) -> RuleFeature:
    feature_id = f"offensive_ma_extension_{key}"
    if close.empty or ma_series.empty or current is None:
        return _feature(
            feature_id,
            "offensive",
            f"Abstand zu {label}",
            active=False,
            value="-",
            threshold=f"{threshold_pct:g}% Abstand",
            detail="Nicht genügend Kursdaten für diese Durchschnittslinie.",
            contribution_percent=contribution,
            setup={"line": key, "threshold_pct": threshold_pct},
        )
    extension_pct = (close / ma_series - 1) * 100
    trigger_mask = extension_pct >= threshold_pct
    if not trigger_mask.fillna(False).any():
        latest_extension = _safe_float(extension_pct.dropna().iloc[-1]) if not extension_pct.dropna().empty else None
        return _feature(
            feature_id,
            "offensive",
            f"Abstand zu {label}",
            active=False,
            value=f"aktuell {_fmt_pct(latest_extension)}",
            threshold=f"{threshold_pct:g}% Abstand",
            detail="Überdehnungsschwelle wurde seit Kauf nicht erreicht.",
            contribution_percent=contribution,
            setup={"line": key, "threshold_pct": threshold_pct},
        )
    anchor_date = trigger_mask[trigger_mask.fillna(False)].index[-1]
    anchor_close = _safe_float(close.loc[anchor_date])
    latest_extension = _safe_float(extension_pct.dropna().iloc[-1]) if not extension_pct.dropna().empty else None
    active = bool(anchor_close is not None and current < anchor_close and close.index[-1] > anchor_date)
    return _feature(
        feature_id,
        "offensive",
        f"Abstand zu {label}",
        active=active,
        severity="tranche",
        value=f"aktuell {_fmt_pct(latest_extension)} · Anker {_fmt_price(anchor_close)}",
        threshold=f"{threshold_pct:g}% Abstand",
        detail=(
            f"Schwelle am {pd.Timestamp(anchor_date).strftime('%Y-%m-%d')} erreicht; "
            f"Signal, sobald der damalige Schlusskurs unterschritten wird."
        ),
        signal_date=as_of if active else "",
        contribution_percent=contribution,
        setup={"line": key, "threshold_pct": threshold_pct},
    )


def _sharp_drop_without_reclaim(
    daily: pd.DataFrame,
    pct_change: pd.Series,
    atr: float | None,
    unit: str,
    value: float,
    reclaim_days: int,
) -> dict[str, Any]:
    if daily.empty or pct_change.empty:
        return {"active": False, "value": "-", "detail": "Nicht genügend Kursdaten.", "signal_date": ""}
    high = _series(daily, "high")
    close = _series(daily, "close")
    result = {"active": False, "value": "kein unreclaimter Einbruch", "detail": "Kein scharfer Einbruch ohne Reclaim.", "signal_date": ""}
    for idx, pct in pct_change.dropna().items():
        drop_abs = abs(_safe_float(pct, 0.0) or 0.0)
        price_abs = None
        if unit == "atr" and atr and atr > 0:
            previous_close = _safe_float(close.shift(1).loc[idx])
            current_close = _safe_float(close.loc[idx])
            if previous_close is not None and current_close is not None:
                price_abs = previous_close - current_close
        crossed = _threshold_crossed(distance_pct=drop_abs, distance_abs=price_abs, atr=atr, unit=unit, value=value)
        if pct >= 0 or not crossed:
            continue
        pos = daily.index.get_loc(idx)
        if not isinstance(pos, int):
            continue
        if pos + reclaim_days >= len(daily):
            result = {
                "active": False,
                "value": f"{drop_abs:.1f}% Einbruch läuft noch",
                "detail": f"Reclaim-Fenster von {reclaim_days} Tagen noch nicht vollständig abgeschlossen.",
                "signal_date": "",
            }
            continue
        selloff_high = _safe_float(high.loc[idx])
        future_high = high.iloc[pos + 1 : pos + reclaim_days + 1]
        reclaimed = bool(selloff_high is not None and (future_high >= selloff_high).fillna(False).any())
        if not reclaimed:
            result = {
                "active": True,
                "value": f"{drop_abs:.1f}% Einbruch",
                "detail": f"Hoch des Verkaufstags {_fmt_price(selloff_high)} wurde in {reclaim_days} Tagen nicht erreicht.",
                "signal_date": pd.Timestamp(idx).strftime("%Y-%m-%d"),
            }
    return result


def _biggest_gain_feature(
    daily: pd.DataFrame,
    pct_change: pd.Series,
    volume: pd.Series,
    volume_sma50: pd.Series,
    atr: float | None,
    setup: dict,
    as_of: str,
) -> RuleFeature:
    unit = str(setup.get("biggest_gain_unit") or "pct")
    value = _safe_float(setup.get("biggest_gain_value"), 10.0) or 10.0
    lookback = max(2, _safe_int(setup.get("biggest_gain_lookback"), 20))
    multiplier = _safe_float(setup.get("biggest_gain_multiplier"), 1.5) or 1.5
    high = _series(daily, "high")
    low = _series(daily, "low")
    recent_pct = pct_change.tail(lookback).dropna()
    if recent_pct.empty:
        return _feature(
            "offensive_biggest_gain",
            "offensive",
            "Größter Preisanstieg",
            active=False,
            value="-",
            threshold=f"{_threshold_label(unit, value)} oder {multiplier:g}x höchster Vortagesanstieg",
            detail="Nicht genügend Tagesdaten.",
            contribution_percent=33,
            setup={"unit": unit, "value": value, "lookback": lookback, "multiplier": multiplier},
        )
    active_date = ""
    active_pct = None
    active_detail = ""
    for idx, pct in recent_pct.items():
        previous_pct = pct_change[pct_change.index < idx].tail(lookback)
        previous_max = _safe_float(previous_pct.max(), 0.0) or 0.0
        prev_vol = _safe_float(volume.shift(1).loc[idx])
        vol = _safe_float(volume.loc[idx])
        avg_vol = _safe_float(volume_sma50.loc[idx])
        higher_volume = bool(vol is not None and ((prev_vol is not None and vol > prev_vol) or (avg_vol is not None and vol > avg_vol)))
        day_abs = None
        if unit == "atr" and atr and atr > 0:
            day_abs = _safe_float(high.loc[idx]) - _safe_float(low.loc[idx]) if _safe_float(high.loc[idx]) is not None and _safe_float(low.loc[idx]) is not None else None
        crossed = _threshold_crossed(distance_pct=float(pct), distance_abs=day_abs, atr=atr, unit=unit, value=value)
        multiplier_hit = previous_max > 0 and float(pct) >= previous_max * multiplier
        if pct > 0 and higher_volume and (crossed or multiplier_hit):
            active_date = pd.Timestamp(idx).strftime("%Y-%m-%d")
            active_pct = float(pct)
            active_detail = f"Volumen höher als Vortag oder 50T-Schnitt; vorheriges Maximum {previous_max:.1f}%."
    active = bool(active_date)
    return _feature(
        "offensive_biggest_gain",
        "offensive",
        "Größter Preisanstieg",
        active=active,
        severity="tranche",
        value=f"{active_pct:.1f}% am {active_date}" if active_pct is not None else f"max {recent_pct.max():.1f}%/{lookback}T",
        threshold=f"{_threshold_label(unit, value)} oder {multiplier:g}x höchster Anstieg der letzten {lookback} Tage",
        detail=active_detail or "Kein außergewöhnlicher Gewinn-Tag mit bestätigendem Volumen.",
        signal_date=active_date if active else "",
        contribution_percent=33,
        setup={"unit": unit, "value": value, "lookback": lookback, "multiplier": multiplier},
    )


def _detect_defensive_features(
    metrics_payload: dict,
    manual_data: dict,
    setup: dict,
    metrics: dict,
) -> list[RuleFeature]:
    daily = _frame(metrics_payload, "daily_since_buy")
    weekly = _frame(metrics_payload, "weekly_since_buy")
    close = _series(daily, "close")
    low = _series(daily, "low")
    weekly_close = _series(weekly, "close")
    weekly_volume = _series(weekly, "volume")
    current = _metric(metrics, "current_price")
    as_of = str(metrics_payload.get("as_of") or metrics.get("as_of_date") or _last_date(daily))
    features: list[RuleFeature] = []

    buy_low = _safe_float(_manual_value(manual_data, metrics_payload, "low_day_1"))
    previous_low = _safe_float(_manual_value(manual_data, metrics_payload, "low_day_0"))
    reclaim_days = max(1, _safe_int(setup.get("buy_day_reclaim_days"), 3))
    buy_breach = _breach_reclaim_status(close, low, buy_low, reclaim_days)
    features.append(_feature(
        "defensive_buy_day_low",
        "defensive",
        "Unterschreitung des Kauftags",
        active=buy_breach["active"],
        severity="tranche",
        value=buy_breach["value"],
        threshold=f"Tief {_fmt_price(buy_low)} in {reclaim_days} Tagen zurückerobern",
        detail=buy_breach["detail"],
        signal_date=buy_breach["signal_date"],
        contribution_percent=50,
        setup={"reclaim_days": reclaim_days},
    ))
    prev_breach_active = bool(previous_low is not None and current is not None and current < previous_low)
    features.append(_feature(
        "defensive_previous_day_low",
        "defensive",
        "Tief des Vortags vor dem Kauftag unterschritten",
        active=prev_breach_active,
        severity="warning",
        value=f"Kurs {_fmt_price(current)} vs. Tief {_fmt_price(previous_low)}",
        threshold="Schlusskurs unter Vortagestief vor Kauf",
        detail="Zusätzliche Warnung zur Kauftag-Tief-Regel.",
        signal_date=as_of if prev_breach_active else "",
        contribution_percent=25,
        setup={},
    ))

    ma_days = max(1, _safe_int(setup.get("ma_break_reclaim_days"), 3))
    ma_specs = [
        ("10", "10-SMA", _sma(close, 10), 25),
        ("21", "21-EMA", _ema(close, 21), 33),
        ("50", "50-SMA", _sma(close, 50), 50),
        ("200", "200-SMA", _sma(close, 200), 100),
    ]
    for key, label, ma_series, contribution in ma_specs:
        features.append(_ma_break_feature(key, label, close, ma_series, ma_days, as_of, contribution))

    loss_weeks = max(1, _safe_int(setup.get("loss_weeks_count"), 3))
    require_volume = _safe_bool(setup.get("loss_weeks_require_rising_volume"))
    weekly_loss = weekly_close < weekly_close.shift(1)
    if require_volume:
        weekly_loss = weekly_loss & (weekly_volume > weekly_volume.shift(1))
    consecutive_weeks = _trailing_true_count(weekly_loss)
    loss_weeks_active = consecutive_weeks >= loss_weeks
    volume_detail = " mit steigendem Wochenvolumen" if require_volume else ""
    features.append(_feature(
        "defensive_loss_weeks",
        "defensive",
        "x Wochen in Folge Verluste",
        active=loss_weeks_active,
        severity="warning",
        value=f"{consecutive_weeks} Wochen",
        threshold=f"{loss_weeks} Verlustwochen{volume_detail}",
        detail="Vergleicht Wochenschluss mit der jeweiligen Vorwoche.",
        signal_date=as_of if loss_weeks_active else "",
        contribution_percent=25,
        setup={"weeks": loss_weeks, "require_rising_volume": require_volume},
    ))

    pct_change = close.pct_change(fill_method=None) * 100
    daily_worst = _worst_drop_feature(
        feature_id="defensive_worst_daily_drop",
        label="Größter Tageseinbruch seit Kauf",
        changes=pct_change,
        warmup=max(1, _safe_int(setup.get("worst_drop_warmup_days"), 20)),
        as_of=as_of,
        period_label="Tage",
    )
    weekly_worst = _worst_drop_feature(
        feature_id="defensive_worst_weekly_drop",
        label="Größter Wocheneinbruch seit Kauf",
        changes=weekly_close.pct_change(fill_method=None) * 100,
        warmup=max(1, _safe_int(setup.get("worst_drop_warmup_weeks"), 4)),
        as_of=as_of,
        period_label="Wochen",
    )
    features.extend([daily_worst, weekly_worst])
    return features


def _breach_reclaim_status(close: pd.Series, low: pd.Series, threshold: float | None, reclaim_days: int) -> dict[str, Any]:
    if threshold is None or close.empty or low.empty:
        return {"active": False, "value": "-", "detail": "Kein Referenztief gespeichert.", "signal_date": ""}
    breaches = low < threshold
    if not breaches.fillna(False).any():
        return {"active": False, "value": f"Referenztief {_fmt_price(threshold)} hält", "detail": "Nicht unterschritten.", "signal_date": ""}
    breach_idx = breaches[breaches.fillna(False)].index[-1]
    pos = close.index.get_loc(breach_idx)
    if not isinstance(pos, int):
        return {"active": False, "value": "-", "detail": "Breach-Index nicht auswertbar.", "signal_date": ""}
    future = close.iloc[pos + 1 : pos + reclaim_days + 1]
    reclaimed = bool((future > threshold).fillna(False).any())
    days_since = len(close.iloc[pos + 1 :])
    if reclaimed:
        return {
            "active": False,
            "value": "Unterschritten, danach zurückerobert",
            "detail": f"Referenztief {_fmt_price(threshold)} wurde innerhalb von {reclaim_days} Tagen zurückerobert.",
            "signal_date": "",
        }
    if days_since < reclaim_days:
        return {
            "active": False,
            "value": f"{days_since}/{reclaim_days} Tage im Reclaim-Fenster",
            "detail": f"Referenztief {_fmt_price(threshold)} wurde unterschritten; Reclaim-Fenster läuft.",
            "signal_date": "",
        }
    return {
        "active": True,
        "value": f"Referenztief {_fmt_price(threshold)} nicht zurückerobert",
        "detail": f"Seit {pd.Timestamp(breach_idx).strftime('%Y-%m-%d')} nicht innerhalb von {reclaim_days} Tagen zurückerobert.",
        "signal_date": pd.Timestamp(breach_idx).strftime("%Y-%m-%d"),
    }


def _ma_break_feature(
    key: str,
    label: str,
    close: pd.Series,
    ma_series: pd.Series,
    reclaim_days: int,
    as_of: str,
    contribution: int,
) -> RuleFeature:
    feature_id = f"defensive_ma_break_{key}"
    if close.empty or ma_series.empty or ma_series.dropna().empty:
        return _feature(
            feature_id,
            "defensive",
            f"Bruch {label}",
            active=False,
            value="-",
            threshold=f"{reclaim_days} Tage nicht zurückerobert",
            detail="Nicht genügend Daten für diese Durchschnittslinie.",
            contribution_percent=contribution,
            setup={"line": key, "reclaim_days": reclaim_days},
        )
    below = close < ma_series
    consecutive = _trailing_true_count(below)
    active = consecutive >= reclaim_days
    latest_ma = _safe_float(ma_series.dropna().iloc[-1]) if not ma_series.dropna().empty else None
    latest_close = _safe_float(close.dropna().iloc[-1]) if not close.dropna().empty else None
    return _feature(
        feature_id,
        "defensive",
        f"Bruch {label}",
        active=active,
        severity="tranche" if key in {"50", "200"} else "warning",
        value=f"{consecutive} Tage darunter · Kurs {_fmt_price(latest_close)} / Linie {_fmt_price(latest_ma)}",
        threshold=f"{reclaim_days} Tage nicht zurückerobert",
        detail="Schlusskurse zählen; pro Durchschnitt eigenes Merkmal.",
        signal_date=as_of if active else "",
        contribution_percent=contribution,
        setup={"line": key, "reclaim_days": reclaim_days},
    )


def _worst_drop_feature(
    *,
    feature_id: str,
    label: str,
    changes: pd.Series,
    warmup: int,
    as_of: str,
    period_label: str,
) -> RuleFeature:
    valid = changes.dropna()
    if len(valid) <= warmup:
        return _feature(
            feature_id,
            "defensive",
            label,
            active=False,
            value=f"{len(valid)}/{warmup} {period_label}",
            threshold=f"Benchmark nach {warmup} {period_label}",
            detail="Benchmarkphase läuft noch.",
            contribution_percent=20,
            setup={"warmup": warmup},
        )
    warmup_worst = _safe_float(valid.iloc[:warmup].min())
    later = valid.iloc[warmup:]
    later_worst = _safe_float(later.min()) if not later.empty else None
    active = bool(warmup_worst is not None and later_worst is not None and later_worst < warmup_worst)
    signal_date = ""
    if active:
        try:
            signal_date = pd.Timestamp(later.idxmin()).strftime("%Y-%m-%d")
        except Exception:
            signal_date = as_of
    return _feature(
        feature_id,
        "defensive",
        label,
        active=active,
        severity="warning",
        value=f"Benchmark {_fmt_pct(warmup_worst)} · aktuell schlechtester {_fmt_pct(later_worst)}",
        threshold=f"neuer schlechterer Verlust nach {warmup} {period_label}",
        detail="Der neue höhere Verlusttag beziehungsweise die neue höhere Verlustwoche wird zum nächsten Benchmark.",
        signal_date=signal_date,
        contribution_percent=20,
        setup={"warmup": warmup},
    )


def _strategy_recommendations(
    strategy_key: str,
    setup: dict,
    features_by_id: dict[str, RuleFeature],
    metrics: dict,
) -> list[StrategyRecommendation]:
    if strategy_key == "rs_line":
        return _rs_strategy(setup, metrics, features_by_id)
    if strategy_key == "ema21_risk_averse":
        return _ema21_risk_averse_strategy(setup, metrics, features_by_id)
    if strategy_key == "ema21_offensive":
        return _ema21_offensive_strategy(setup, metrics, features_by_id)
    if strategy_key == "peak_drawdown":
        return _peak_drawdown_strategy(setup, features_by_id)
    if strategy_key == "buy_day_low":
        return _buy_day_low_strategy(setup, features_by_id)
    if strategy_key == "ma_breaks":
        return _ma_break_strategy(features_by_id)
    return _custom_strategy(setup, features_by_id)


def _rec(
    rec_id: str,
    label: str,
    *,
    active: bool,
    pct: int,
    detail: str,
    trigger: str,
    feature_ids: list[str],
) -> StrategyRecommendation:
    return StrategyRecommendation(
        id=rec_id,
        label=label,
        active=bool(active),
        tranche_percent=int(pct if active else 0),
        detail=detail,
        trigger=trigger,
        feature_ids=feature_ids,
    )


def _custom_strategy(setup: dict, features_by_id: dict[str, RuleFeature]) -> list[StrategyRecommendation]:
    steps = setup.get("custom_strategy_steps")
    if not isinstance(steps, list) or not steps:
        steps = DEFAULT_CUSTOM_STRATEGY_STEPS
    recs: list[StrategyRecommendation] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        feature_id = str(step.get("feature_id") or "").strip()
        feature = features_by_id.get(feature_id)
        if not feature:
            continue
        pct = _safe_int(step.get("tranche_percent"), feature.contribution_percent or 25)
        recs.append(_rec(
            f"custom_step_{index}_{feature_id}",
            f"Tranche {pct}%: {feature.label}",
            active=feature.active,
            pct=pct,
            detail=feature.detail or feature.value,
            trigger=feature.threshold,
            feature_ids=[feature_id],
        ))
    return recs


def _rs_strategy(setup: dict, metrics: dict, features_by_id: dict[str, RuleFeature]) -> list[StrategyRecommendation]:
    rs_line = _metric(metrics, "rs_line")
    rs_ma21 = _metric(metrics, "rs_ma21")
    rs_ma50 = _metric(metrics, "rs_ma50")
    days21 = int(_metric(metrics, "days_under_rs_ma21", 0) or 0)
    days50 = int(_metric(metrics, "days_under_rs_ma50", 0) or 0)
    under21 = bool(rs_line is not None and rs_ma21 is not None and rs_line < rs_ma21)
    under50 = bool(rs_line is not None and rs_ma50 is not None and rs_line < rs_ma50)
    pct1 = _safe_int(setup.get("rs_tranche_1_pct"), 25)
    pct2 = _safe_int(setup.get("rs_tranche_2_pct"), 25)
    pct3 = _safe_int(setup.get("rs_tranche_3_pct"), 50)
    return [
        _rec("rs_line_tranche_1", "1. Tranche: RS-Linie unter 21-EMA", active=under21, pct=pct1, detail=f"RS {rs_line or 0:.4f} vs. 21 {_safe_float(rs_ma21, 0) or 0:.4f}", trigger="RS schließt unter 21-EMA", feature_ids=[]),
        _rec("rs_line_tranche_2", "2. Tranche: RS bestätigt Bruch", active=under21 and days21 >= 3, pct=pct2, detail=f"{days21} Tage unter RS-21-EMA", trigger="3 Tage unter 21-EMA oder tiefer als Bruchtag", feature_ids=[]),
        _rec("rs_line_tranche_3", "3. Tranche: RS-Linie unter 50-EMA", active=under50 or days50 > 0, pct=pct3, detail=f"{days50} Tage unter RS-50-EMA", trigger="RS schließt unter 50-EMA", feature_ids=[]),
        _emergency_rec(features_by_id),
    ]


def _ema21_risk_averse_strategy(setup: dict, metrics: dict, features_by_id: dict[str, RuleFeature]) -> list[StrategyRecommendation]:
    ema_break = features_by_id.get("offensive_ema21_break")
    ma50 = features_by_id.get("defensive_ma_break_50")
    emergency = features_by_id.get("emergency_loss_limit")
    days = int(_metric(metrics, "days_under_ema21", 0) or 0)
    first = bool(ema_break and ema_break.active)
    lower_next = bool(first and days >= 2)
    third = bool(first and days >= 3)
    return [
        _rec("ema21_risk_first", "1/4 beim ersten deutlichen Schluss unter der 21-EMA", active=first, pct=_safe_int(setup.get("ema21_risk_averse_first_pct"), 25), detail=ema_break.detail if ema_break else "", trigger="21-EMA-Bruch", feature_ids=["offensive_ema21_break"]),
        _rec("ema21_risk_second", "weiteres 1/4 bei tieferem Folgetag", active=lower_next, pct=_safe_int(setup.get("ema21_risk_averse_second_pct"), 25), detail=f"{days} Tage unter 21-EMA", trigger="Folgetag schwächer", feature_ids=["offensive_ema21_break"]),
        _rec("ema21_risk_third", "weiteres 1/4 am dritten Tag unter der Linie", active=third, pct=_safe_int(setup.get("ema21_risk_averse_third_pct"), 25), detail=f"{days} Tage unter 21-EMA", trigger="Tag 3 weiterhin darunter", feature_ids=["offensive_ema21_break"]),
        _rec("ema21_risk_final", "Restverkauf bei Nothalt oder 50-Tage-Bruch", active=bool((emergency and emergency.active) or (ma50 and ma50.active)), pct=100, detail="Finale Bedingung erreicht.", trigger="Nothalt oder 50-SMA", feature_ids=["emergency_loss_limit", "defensive_ma_break_50"]),
    ]


def _ema21_offensive_strategy(setup: dict, metrics: dict, features_by_id: dict[str, RuleFeature]) -> list[StrategyRecommendation]:
    ema_break = features_by_id.get("offensive_ema21_break")
    ma50 = features_by_id.get("defensive_ma_break_50")
    emergency = features_by_id.get("emergency_loss_limit")
    days = int(_metric(metrics, "days_under_ema21", 0) or 0)
    lower_lows = int(_metric(metrics, "lower_lows_count", 0) or _metric(metrics, "lower_low_days", 0) or 0)
    return [
        _rec("ema21_offensive_first", "1/3 nach drei Tagen unter der 21-EMA", active=bool(ema_break and ema_break.active and days >= 3), pct=_safe_int(setup.get("ema21_offensive_first_pct"), 33), detail=f"{days} Tage unter 21-EMA", trigger="3 bestätigte Schlüsse", feature_ids=["offensive_ema21_break"]),
        _rec("ema21_offensive_followup", "Weitere Tranche bei 50-SMA-Bruch oder drei tieferen Tiefs", active=bool((ma50 and ma50.active) or lower_lows >= 3), pct=33, detail=f"{lower_lows} tiefere Tiefs in Folge", trigger="50-SMA oder tiefere Tiefs", feature_ids=["defensive_ma_break_50"]),
        _rec("ema21_offensive_final", "Finale Tranche beim Nothalt", active=bool(emergency and emergency.active), pct=100, detail="Nothalt erreicht.", trigger="Nothalt", feature_ids=["emergency_loss_limit"]),
    ]


def _peak_drawdown_strategy(setup: dict, features_by_id: dict[str, RuleFeature]) -> list[StrategyRecommendation]:
    peak = features_by_id.get("offensive_peak_drop")
    ma21 = features_by_id.get("defensive_ma_break_21")
    ma50 = features_by_id.get("defensive_ma_break_50")
    emergency = features_by_id.get("emergency_loss_limit")
    return [
        _rec("peak_drawdown_first", "1/4 bei erster Rückgangsschwelle vom 20T-Hoch", active=bool(peak and peak.active), pct=_safe_int(setup.get("peak_drawdown_first_pct"), 25), detail=peak.value if peak else "", trigger=_threshold_label(str(setup.get("peak_drawdown_first_unit") or "pct"), _safe_float(setup.get("peak_drawdown_first_value"), 8.0) or 8.0), feature_ids=["offensive_peak_drop"]),
        _rec("peak_drawdown_second", "1/4 bei zweiter Rückgangsschwelle vom 20T-Hoch", active=bool(peak and peak.active and ("15" in peak.threshold or (_safe_float(str(peak.value).replace('%', '').split()[0], 0.0) or 0.0) >= 15)), pct=_safe_int(setup.get("peak_drawdown_second_pct"), 25), detail=peak.value if peak else "", trigger=_threshold_label(str(setup.get("peak_drawdown_second_unit") or "pct"), _safe_float(setup.get("peak_drawdown_second_value"), 15.0) or 15.0), feature_ids=["offensive_peak_drop"]),
        _rec("peak_drawdown_trend_break", "Weitere Tranche bei 21/50-Linienbruch", active=bool((ma21 and ma21.active) or (ma50 and ma50.active)), pct=25, detail="Trendbruch nach Peak-Rückgang.", trigger="21-EMA oder 50-SMA drei Tage darunter", feature_ids=["defensive_ma_break_21", "defensive_ma_break_50"]),
        _rec("peak_drawdown_final", "Finale Tranche beim Nothalt", active=bool(emergency and emergency.active), pct=100, detail="Nothalt erreicht.", trigger="Nothalt", feature_ids=["emergency_loss_limit"]),
    ]


def _buy_day_low_strategy(setup: dict, features_by_id: dict[str, RuleFeature]) -> list[StrategyRecommendation]:
    buy_low = features_by_id.get("defensive_buy_day_low")
    previous = features_by_id.get("defensive_previous_day_low")
    emergency = features_by_id.get("emergency_loss_limit")
    return [
        _rec("buy_day_low_warning", "Warnung: Kauftag-Tief unterschritten", active=bool(buy_low and buy_low.signal_date), pct=0, detail=buy_low.detail if buy_low else "", trigger="Kauftag-Tief", feature_ids=["defensive_buy_day_low"]),
        _rec("buy_day_low_tranche", "Verkaufstranche, wenn Kauftag-Tief nicht zurückerobert wird", active=bool(buy_low and buy_low.active), pct=50, detail=buy_low.detail if buy_low else "", trigger="kein Reclaim in 3 Tagen", feature_ids=["defensive_buy_day_low"]),
        _rec("buy_day_low_previous", "Zusatzwarnung: Tief vor dem Kauftag unterschritten", active=bool(previous and previous.active), pct=25, detail=previous.detail if previous else "", trigger="Vortagestief vor Kauf", feature_ids=["defensive_previous_day_low"]),
        _rec("buy_day_low_final", "Komplettverkauf beim Nothalt", active=bool(emergency and emergency.active), pct=100, detail="Nothalt erreicht.", trigger="Nothalt", feature_ids=["emergency_loss_limit"]),
    ]


def _ma_break_strategy(features_by_id: dict[str, RuleFeature]) -> list[StrategyRecommendation]:
    ma50 = features_by_id.get("defensive_ma_break_50")
    ma200 = features_by_id.get("defensive_ma_break_200")
    return [
        _rec("ma_breaks_first", "Erste Tranche: 50-SMA drei Tage gebrochen", active=bool(ma50 and ma50.active), pct=50, detail=ma50.detail if ma50 else "", trigger="50-SMA bestätigt gebrochen", feature_ids=["defensive_ma_break_50"]),
        _rec("ma_breaks_final", "Finale Tranche: 200-SMA gebrochen", active=bool(ma200 and ma200.active), pct=100, detail=ma200.detail if ma200 else "", trigger="200-SMA-Bruch", feature_ids=["defensive_ma_break_200"]),
        _emergency_rec(features_by_id),
    ]


def _emergency_rec(features_by_id: dict[str, RuleFeature]) -> StrategyRecommendation:
    emergency = features_by_id.get("emergency_loss_limit")
    return _rec(
        "emergency_final",
        "Komplettverkauf beim Nothalt",
        active=bool(emergency and emergency.active),
        pct=100,
        detail=emergency.detail if emergency else "",
        trigger="Nothalt",
        feature_ids=["emergency_loss_limit"],
    )


def _build_strategy_result(strategy_key: str, recommendations: list[StrategyRecommendation]) -> dict[str, Any]:
    active_recs = [rec for rec in recommendations if rec.active and rec.tranche_percent > 0]
    recommendation_percent = max((rec.tranche_percent for rec in active_recs), default=0)
    # If multiple active custom steps fire, their intended tranche sizes add up to a
    # target total, capped at 100. Predefined strategies keep the highest active stage.
    if strategy_key == "custom":
        recommendation_percent = min(100, sum(rec.tranche_percent for rec in active_recs))
    return {
        "strategy_key": strategy_key,
        "label": SELL_STRATEGY_LABELS.get(strategy_key, SELL_STRATEGY_LABELS["custom"]),
        "description": SELL_STRATEGY_DESCRIPTIONS.get(strategy_key, SELL_STRATEGY_DESCRIPTIONS["custom"]),
        "recommendation_percent": int(recommendation_percent),
        "recommendations": [rec.to_dict() for rec in recommendations],
    }


def evaluate_sell_decision(
    metrics_payload: dict,
    manual_data: dict | None = None,
    tranche_log: list[dict] | None = None,
    recommendation_state: dict | None = None,
) -> dict[str, Any]:
    """Evaluate per-stock sell features and the selected selling strategy."""
    manual_data = manual_data or {}
    metrics, ticker, buy_price, _shares = _extract_inputs(metrics_payload or {})
    if not ticker and isinstance(manual_data, dict):
        ticker = str(manual_data.get("ticker") or "").upper().strip()
    market_environment = str(manual_data.get("market_environment") or "Unsicher").strip() or "Unsicher"
    pnl = _metric(metrics, "pnl_pct", 0.0) or 0.0
    as_of_date = str(metrics_payload.get("as_of") or metrics.get("as_of_date") or "")
    regime = _regime(pnl, market_environment)
    setup = _resolve_setup(metrics_payload or {}, manual_data)
    strategy_key = str(setup.get("strategy_key") or "custom")

    emergency_features = _detect_emergency_features(metrics_payload or {}, manual_data, setup, metrics, buy_price)
    offensive_features = _detect_offensive_features(metrics_payload or {}, setup, metrics, buy_price)
    defensive_features = _detect_defensive_features(metrics_payload or {}, manual_data, setup, metrics)
    all_features = [*emergency_features, *offensive_features, *defensive_features]
    features_by_id = {feature.id: feature for feature in all_features}

    recommendations = _strategy_recommendations(strategy_key, setup, features_by_id, metrics)
    strategy = _build_strategy_result(strategy_key, recommendations)

    killer_signals: list[RuleSignal] = [
        _signal_from_feature(feature, contribution=100, strategy_key="nothalt")
        for feature in emergency_features
        if feature.active
    ]
    tranche_signals: list[RuleSignal] = [
        _signal_from_recommendation(rec, features_by_id, strategy_key)
        for rec in recommendations
        if rec.active and rec.tranche_percent > 0 and rec.tranche_percent < 100
    ]
    # Keep full-exit recommendations that are not the emergency feature visible as tranche
    # signals unless the emergency killer is already active.
    if not killer_signals:
        tranche_signals.extend(
            _signal_from_recommendation(rec, features_by_id, strategy_key)
            for rec in recommendations
            if rec.active and rec.tranche_percent >= 100
        )
    warning_signals = [
        _signal_from_feature(feature, contribution=feature.contribution_percent, strategy_key=feature.id)
        for feature in [*offensive_features, *defensive_features]
        if feature.active and feature.severity == "warning"
    ]
    watch_signals = [
        _signal_from_feature(feature, contribution=0, strategy_key=feature.id)
        for feature in all_features
        if not feature.active and feature.value
    ][:12]

    target_total = 100 if killer_signals else int(strategy["recommendation_percent"])
    if not killer_signals and strategy_key == "custom":
        active_contributing = [feature for feature in all_features if feature.active and feature.contribution_percent > 0]
        if len(active_contributing) >= 4:
            target_total = max(target_total, 75)
        if any(feature.id == "offensive_ma_extension_sma200" and feature.active for feature in active_contributing):
            target_total = 100
        if pnl >= 100 and any(feature.id == "offensive_biggest_gain" and feature.active for feature in active_contributing):
            target_total = 100
        if market_environment == BEARISH_MARKET_LABEL and target_total < 100 and target_total > 0:
            target_total = _next_allowed(target_total)

    already_sold = _sum_already_sold(ticker, tranche_log)
    sell_now_raw = max(0.0, min(100.0, target_total - already_sold))
    sell_now = _floor_allowed(sell_now_raw)
    recommendation_percent = int(sell_now)
    remaining_after_sale = max(0.0, 100.0 - already_sold - sell_now)

    if recommendation_percent >= 100 or (target_total == 100 and remaining_after_sale <= 0):
        label = "KOMPLETTVERKAUF"
    elif recommendation_percent > 0:
        label = "TEILVERKAUF"
    else:
        label = "HALTEN"

    stop_price = _build_stop_price(setup, buy_price, _metric(metrics, "atr14"))
    next_tranche_trigger, full_exit = _build_trigger_prices(metrics, setup, stop_price)
    add_again_condition = "Erst wieder aufstocken, wenn die verletzte Linie zurückerobert wurde und die Verkaufsmerkmale inaktiv sind."

    if killer_signals:
        explanation = f"{killer_signals[0].label}: Nothalt aktiv, kompletter Verkauf erforderlich."
    elif recommendation_percent > 0:
        active_rec_count = len([rec for rec in recommendations if rec.active])
        explanation = f"{active_rec_count} aktive Strategie-Bedingung(en) ergeben Zielverkauf {target_total}%; bereits verkauft {already_sold:.0f}%; jetzt zusätzlich {recommendation_percent}%."
    elif warning_signals:
        explanation = f"Keine Verkaufstranche, aber {len(warning_signals)} aktive Warnmerkmale beobachten."
    else:
        explanation = "Keine aktiven Verkaufsmerkmale. Position halten."

    sell_mode_summary = "Keine neue Verkaufstranche"
    sell_style_summary = ""
    if recommendation_percent > 0:
        if killer_signals or pnl < 0:
            sell_mode_summary = DEFENSIVE_MODE
            sell_style_summary = LOSS_LIMIT_STYLE
        elif any(features_by_id.get(fid) and features_by_id[fid].category == "defensive" for rec in recommendations if rec.active for fid in rec.feature_ids):
            sell_mode_summary = STRENGTH_DEFENSIVE_MODE
            sell_style_summary = STRENGTH_DEFENSIVE_STYLE
        else:
            sell_mode_summary = STRENGTH_OFFENSIVE_MODE
            sell_style_summary = STRENGTH_OFFENSIVE_STYLE

    pending_status, next_state = _compute_recommendation_status(
        sell_now=int(sell_now),
        has_killer=bool(killer_signals),
        as_of_date=as_of_date,
        prior_state=recommendation_state,
    )

    display_label = label
    if pending_status == "in_bestaetigung" and recommendation_percent > 0:
        display_label = "BESTÄTIGUNG ABWARTEN"
    elif pending_status == "snoozed" and recommendation_percent > 0:
        display_label = "STUMM GESCHALTET"

    all_signals = [*killer_signals, *tranche_signals, *warning_signals, *watch_signals]
    book_references = {sig.id: sig.book_reference for sig in all_signals if sig.book_reference}
    return {
        "recommendation_percent": int(recommendation_percent),
        "recommendation_label": label,
        "display_label": display_label,
        "regime": regime,
        "killer_signals": [sig.to_dict() for sig in killer_signals],
        "tranche_signals": [sig.to_dict() for sig in tranche_signals],
        "warning_signals": [sig.to_dict() for sig in warning_signals],
        "watch_signals": [sig.to_dict() for sig in watch_signals],
        "emergency_features": [feature.to_dict() for feature in emergency_features],
        "offensive_features": [feature.to_dict() for feature in offensive_features],
        "defensive_features": [feature.to_dict() for feature in defensive_features],
        "strategy": strategy,
        "stop_price": stop_price,
        "next_tranche_trigger_price": next_tranche_trigger,
        "full_exit_price": full_exit,
        "add_again_condition": add_again_condition,
        "explanation_short": explanation,
        "book_references": book_references,
        "target_total_sold_percent": int(target_total),
        "already_sold_percent": already_sold,
        "sell_now_percent": int(sell_now),
        "remaining_after_sale_percent": remaining_after_sale,
        "sell_mode": sell_mode_summary,
        "sell_style": sell_style_summary,
        "pending_status": pending_status,
        "next_recommendation_state": next_state,
    }
