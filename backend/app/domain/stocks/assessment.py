from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

import numpy as np
import pandas as pd
from app.domain.stocks.instrument_type import inapplicable_reason


AssessmentCategory = Literal["fundamental", "technical", "trend", "risk"]
SignalCategory = Literal["positive", "negative", "neutral"]
VerdictTone = Literal["good", "neutral", "warning", "bad"]
ScoreStatus = Literal["available", "partial", "neutral", "insufficient_history", "missing"]


OVERALL_WEIGHTS = {"technical": 3, "fundamental": 3, "chart": 3, "moving_average": 1}
TECHNICAL_WEIGHTS = {
    "k4_rs_leadership": 36,
    "k13_rs_dynamics": 28,
    "rs_rating": 24,
    "high_position": 12,
    "up_down_volume": 10,
    "cmf": 10,
}
K4_WEIGHTS = {"above_21_ema": 25, "above_50_sma": 15, "persistence": 20, "rs_52w_high": 30, "white_space": 10}
K13_WEIGHTS = {"three_vs_six": 35, "six_vs_twelve": 25, "sequence": 25, "acceleration": 15}
FUNDAMENTAL_WEIGHTS = {"fundamental_core": 5, "k9_eps_sales_alignment": 1}
CHART_WEIGHTS = {"price_action_core": 4, "k35_down_week_quality": 1, "k38_hh_hl_good_close": 1}
MOVING_AVERAGE_WEIGHTS = {
    "price_above_200_sma": 20,
    "price_above_50_sma": 15,
    "price_above_21_ema": 10,
    "price_above_10_sma": 5,
    "ma_order": 15,
    "persistence": 15,
    "slope": 20,
}
SCOREABLE_STATUSES = {"available", "partial"}


@dataclass(frozen=True)
class StockAssessmentBar:
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: float | None = None


@dataclass(frozen=True)
class AssessmentCheck:
    category: AssessmentCategory
    label: str
    passed: bool
    detail: str
    severity: Literal["info", "warning", "critical"] = "info"


@dataclass(frozen=True)
class ChartSignal:
    category: SignalCategory
    label: str
    detail: str = ""
    key: str = ""
    source: str = "price_action"
    score_relevant: bool = True
    display_relevant: bool = True


@dataclass(frozen=True)
class ChartSignalState:
    active: bool
    available: bool
    detail: str


@dataclass(frozen=True)
class StockAssessmentScores:
    overall: int
    technical: float
    fundamental: float
    moving_averages: float
    chart_behavior: int


@dataclass(frozen=True)
class StockAssessmentMetrics:
    last_close: float | None
    change_pct: float | None
    atr_pct: float | None
    volume_ratio_50d: float | None
    dollar_volume_mio: float | None
    cmf_20: float | None
    drawdown_52w_pct: float | None
    distance_sma10_pct: float | None
    distance_ema21_pct: float | None
    distance_sma50_pct: float | None
    distance_sma200_pct: float | None
    rs_rating: int | None = None
    rs_percentile: float | None = None
    beta: float | None = None
    next_earnings_calendar_days: int | None = None
    next_earnings_trading_days: int | None = None


@dataclass(frozen=True)
class EarningsWarning:
    next_earnings_date: str | None
    calendar_days: int | None
    trading_days: int | None
    tone: VerdictTone
    message: str


@dataclass(frozen=True)
class StockAssessmentResult:
    ticker: str
    as_of: str
    source: Literal["database", "missing"]
    data_status: Literal["fresh", "missing", "stale"]
    message: str
    verdict_label: str
    verdict_tone: VerdictTone
    verdict_text: str
    fundamentals_available: bool
    scores: StockAssessmentScores
    metrics: StockAssessmentMetrics
    fundamentals: Mapping[str, Any] | None = None
    earnings: EarningsWarning | None = None
    checks: list[AssessmentCheck] = field(default_factory=list)
    chart_signals: list[ChartSignal] = field(default_factory=list)
    chart_signal_states: Mapping[str, ChartSignalState] = field(default_factory=dict)
    drivers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    overall_v2: Mapping[str, Any] = field(default_factory=dict)
    technical_v2: Mapping[str, Any] = field(default_factory=dict)
    fundamental_v2: Mapping[str, Any] = field(default_factory=dict)
    chart_v2: Mapping[str, Any] = field(default_factory=dict)
    moving_average_v2: Mapping[str, Any] = field(default_factory=dict)
    setup: Mapping[str, Any] = field(default_factory=dict)
    eligibility: Mapping[str, Any] = field(default_factory=dict)


def compute_stock_assessment(
    ticker: str,
    bars: Sequence[Any],
    *,
    rs_context: Mapping[str, Any] | None = None,
    fundamentals_context: Mapping[str, Any] | None = None,
    institutional_context: Mapping[str, Any] | None = None,
    score_weights: Mapping[str, Mapping[str, float]] | None = None,
) -> StockAssessmentResult:
    clean = ticker.strip().upper()
    df = _coerce_bars_to_frame(bars)
    today = date.today().isoformat()
    if df.empty or len(df) < 50:
        return StockAssessmentResult(
            ticker=clean,
            as_of=df.index[-1].date().isoformat() if not df.empty else today,
            source="missing",
            data_status="missing",
            message="Für die Aktienbewertung fehlen mindestens 50 gecachte Tagesbars.",
            verdict_label="Nicht bewertbar",
            verdict_tone="bad",
            verdict_text="Lade zuerst Preise über den Price-Refresh-Job.",
            fundamentals_available=False,
            scores=StockAssessmentScores(
                overall=0,
                technical=0.0,
                fundamental=50.0,
                moving_averages=0.0,
                chart_behavior=50,
            ),
            metrics=StockAssessmentMetrics(
                last_close=None,
                change_pct=None,
                atr_pct=None,
                volume_ratio_50d=None,
                dollar_volume_mio=None,
                cmf_20=None,
                drawdown_52w_pct=None,
                distance_sma10_pct=None,
                distance_ema21_pct=None,
                distance_sma50_pct=None,
                distance_sma200_pct=None,
            ),
            warnings=["Price Cache fehlt oder enthält zu wenige Tagesbars."],
        )

    rs = dict(rs_context or {})
    fundamentals = dict(fundamentals_context or {})
    institutional = dict(institutional_context or {})
    fundamentals = _merge_institutional_fields(fundamentals, institutional)
    technical_checks, cmf_value = evaluate_technicals(df, rs_context=rs)
    fundamental_checks, fundamental_core_score, fundamentals_available = evaluate_fundamentals_context(
        fundamentals,
        institutional_context=institutional,
    )
    earnings = _build_earnings_warning(fundamentals.get("next_earnings_date"))
    earnings_check = _earnings_check(earnings)
    checks = [*technical_checks, *fundamental_checks]
    if earnings_check is not None:
        checks.append(earnings_check)
    weekly_bars = _weekly_bars(df)
    chart_signals = evaluate_chart_signs(df, rs_context=rs, weekly_bars=weekly_bars)
    chart_signal_states = evaluate_negative_chart_signal_states(df, rs_context=rs)
    metrics = _compute_metrics(
        df,
        cmf_value=cmf_value,
        rs_context=rs,
        fundamentals_context=fundamentals,
        earnings=earnings,
    )
    weekly = _completed_weekly_bars(df, weekly_bars=weekly_bars)
    configured_weights = dict(score_weights or {})
    technical_v2 = _technical_score_v2(
        df, technical_checks, metrics, rs, cmf_value,
        weights=_weight_group(configured_weights, "technical", TECHNICAL_WEIGHTS),
    )
    fundamental_v2 = _fundamental_score_v2(
        fundamentals,
        core_score=fundamental_core_score,
        core_available=fundamentals_available,
        weights=_weight_group(configured_weights, "fundamental", FUNDAMENTAL_WEIGHTS),
    )
    moving_average_v2 = _moving_average_score_v2(
        df, weights=_weight_group(configured_weights, "moving_average", MOVING_AVERAGE_WEIGHTS),
    )
    chart_v2 = _chart_score_v2(
        chart_signals, weekly, weights=_weight_group(configured_weights, "chart", CHART_WEIGHTS),
    )
    overall_v2 = _overall_score_v2(
        technical_v2=technical_v2,
        fundamental_v2=fundamental_v2,
        chart_v2=chart_v2,
        moving_average_v2=moving_average_v2,
        weights=_weight_group(configured_weights, "overall", OVERALL_WEIGHTS),
    )
    technical_score = float(technical_v2["score"] or 0.0)
    # The legacy scalar remains numeric for old consumers. The v2 status is the
    # authoritative representation when a complete area is unavailable.
    fundamental_score = float(fundamental_v2["score"] if fundamental_v2["score"] is not None else 50.0)
    ma_score = float(moving_average_v2["score"] or 0.0)
    chart_score_value = float(chart_v2["score"] or 0.0)
    chart_score = _round_half_up_int(chart_score_value)
    overall = _round_half_up_int(float(overall_v2["score"] or 0.0))
    setup = _setup_context(df, chart_signals)
    eligibility = _eligibility_context(technical_checks)
    verdict_label, verdict_tone, verdict_text = _build_verdict(overall, checks, metrics)
    drivers, warnings = _build_drivers_and_warnings(
        checks,
        chart_signals,
        fundamentals_available=fundamentals_available or bool(inapplicable_reason(str(fundamentals.get("instrument_type") or ""))),
        earnings=earnings,
    )

    return StockAssessmentResult(
        ticker=clean,
        as_of=df.index[-1].date().isoformat(),
        source="database",
        data_status="fresh",
        message="Bewertung aus gecachten Price-Bars, gespeichertem RS-Kontext und Fundamental-Cache.",
        verdict_label=verdict_label,
        verdict_tone=verdict_tone,
        verdict_text=verdict_text,
        fundamentals_available=fundamentals_available,
        scores=StockAssessmentScores(
            overall=overall,
            technical=technical_score,
            fundamental=fundamental_score,
            moving_averages=ma_score,
            chart_behavior=chart_score,
        ),
        metrics=metrics,
        fundamentals=fundamentals or None,
        earnings=earnings,
        checks=checks,
        chart_signals=chart_signals,
        chart_signal_states=chart_signal_states,
        drivers=drivers,
        warnings=warnings,
        overall_v2=overall_v2,
        technical_v2=technical_v2,
        fundamental_v2=fundamental_v2,
        chart_v2=chart_v2,
        moving_average_v2=moving_average_v2,
        setup=setup,
        eligibility=eligibility,
    )


def evaluate_technicals(
    df: pd.DataFrame,
    *,
    rs_context: Mapping[str, Any] | None = None,
) -> tuple[list[AssessmentCheck], float | None]:
    checks: list[AssessmentCheck] = []
    rs = dict(rs_context or {})
    close = pd.to_numeric(df["Close"], errors="coerce")
    high = pd.to_numeric(df["High"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    price = _safe_float(close.iloc[-1])

    checks.append(
        AssessmentCheck(
            category="technical",
            label="Preis >= $15",
            passed=price is not None and price >= 15,
            detail=f"${price:,.2f}" if price is not None else "Nicht verfügbar",
            severity="critical",
        )
    )

    avg_volume_20 = volume.tail(20).mean()
    dollar_volume_mio = avg_volume_20 * price / 1_000_000 if price and pd.notna(avg_volume_20) else np.nan
    if pd.notna(dollar_volume_mio):
        checks.append(
            AssessmentCheck(
                category="technical",
                label="Dollar-Volumen >= $30 Mio.",
                passed=float(dollar_volume_mio) >= 30,
                detail=f"${float(dollar_volume_mio):,.0f} Mio./Tag",
                severity="critical",
            )
        )
    else:
        checks.append(_missing_check("technical", "Dollar-Volumen >= $30 Mio.", severity="critical"))

    prior_highs = high.iloc[:-1].dropna()
    ath = _safe_float(prior_highs.max()) if len(prior_highs) else None
    if ath is None:
        ath = _safe_float(high.max())
    if price is not None and ath is not None and ath > 0:
        distance = (price / ath - 1) * 100
        checks.append(
            AssessmentCheck(
                category="technical",
                label="Entfernung zum All-Time-High",
                passed=distance >= 0,
                detail=f"{distance:+.1f}% zum bisherigen ATH (${ath:,.2f})",
            )
        )
    else:
        checks.append(_missing_check("technical", "Entfernung zum All-Time-High"))

    prior_high_52w = high.iloc[:-1].tail(252).dropna()
    high_52w = _safe_float(prior_high_52w.max()) if len(prior_high_52w) >= 20 else None
    if high_52w is None:
        high_52w = _safe_float(high.rolling(252, min_periods=20).max().iloc[-1])
    if price is not None and high_52w is not None and high_52w > 0:
        distance = (price / high_52w - 1) * 100
        checks.append(
            AssessmentCheck(
                category="technical",
                label="Entfernung zum 52-Wochen-Hoch",
                passed=distance >= 0,
                detail=f"{distance:+.1f}% zum bisherigen 52W-Hoch (${high_52w:,.2f})",
            )
        )
    else:
        checks.append(_missing_check("technical", "Entfernung zum 52-Wochen-Hoch"))

    pct = close.pct_change(fill_method=None)
    up_volume = volume.where(pct > 0).tail(50).sum()
    down_volume = volume.where(pct < 0).tail(50).sum()
    if pd.notna(down_volume) and float(down_volume) > 0:
        ratio = float(up_volume / down_volume)
        detail = f"{ratio:.2f}" + (" (ideal >=1.1)" if ratio >= 1.1 else "")
        checks.append(
            AssessmentCheck(
                category="technical",
                label="Up/Down Vol. Ratio >=1.0",
                passed=ratio >= 1.0,
                detail=detail,
            )
        )
    else:
        checks.append(_missing_check("technical", "Up/Down Vol. Ratio >=1.0"))

    checks.extend(_rs_checks(rs))

    cmf = _calc_cmf(df, 20)
    cmf_value = _safe_float(cmf.iloc[-1]) if len(cmf) else None
    cmf_rating = _cmf_rating(cmf_value)
    checks.append(
        AssessmentCheck(
            category="technical",
            label="CMF Rating A oder B",
            passed=cmf_rating[0] in {"A", "B"},
            detail=(
                f"CMF: {cmf_value:+.3f} -> {cmf_rating[0]} ({cmf_rating[1]})"
                if cmf_value is not None
                else "Nicht verfügbar"
            ),
        )
    )

    ema21 = close.ewm(span=21, adjust=False).mean()
    sma10 = close.rolling(10, min_periods=10).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    average_map = {"10-SMA": sma10, "21-EMA": ema21, "50-SMA": sma50, "200-SMA": sma200}
    for label, series in average_map.items():
        average = _safe_float(series.iloc[-1])
        checks.append(
            AssessmentCheck(
                category="trend",
                label=f"Kurs über {label}",
                passed=price is not None and average is not None and price > average,
                detail=f"{price:,.2f} vs {average:,.2f}" if price is not None and average is not None else "Nicht verfügbar",
            )
        )

    e21 = _safe_float(ema21.iloc[-1])
    s50 = _safe_float(sma50.iloc[-1])
    s200 = _safe_float(sma200.iloc[-1])
    checks.append(
        AssessmentCheck(
            category="trend",
            label="MA-Ordnung (21>50>200)",
            passed=e21 is not None and s50 is not None and s200 is not None and e21 > s50 > s200,
            detail=f"21:{e21:,.0f} · 50:{s50:,.0f} · 200:{s200:,.0f}"
            if e21 is not None and s50 is not None and s200 is not None
            else "Nicht verfügbar",
        )
    )

    for label, series, threshold in [
        ("10-SMA", sma10, 10.0),
        ("21-EMA", ema21, 14.0),
        ("50-SMA", sma50, 25.0),
        ("200-SMA", sma200, 70.0),
    ]:
        average = _safe_float(series.iloc[-1])
        if price is None or average is None or average == 0:
            checks.append(_missing_check("risk", f"Abstand {label} (<{threshold:.0f}%)"))
            continue
        distance = (price / average - 1) * 100
        checks.append(
            AssessmentCheck(
                category="risk",
                label=f"Abstand {label} (<{threshold:.0f}%)",
                passed=abs(distance) < threshold,
                detail=f"{distance:+.1f}% (Schwelle: ±{threshold:.0f}%)",
                severity="warning",
            )
        )

    return checks, cmf_value


def evaluate_fundamentals_context(
    fundamentals_context: Mapping[str, Any] | None,
    *,
    institutional_context: Mapping[str, Any] | None = None,
) -> tuple[list[AssessmentCheck], float, bool]:
    fundamentals = dict(fundamentals_context or {})
    instrument_type = str(fundamentals.get("instrument_type") or "unknown")
    if inapplicable_reason(instrument_type):
        return ([AssessmentCheck(category="fundamental", label="Operative Fundamentalkriterien",
                                 passed=True, detail="Fundamentalkriterium für diesen Wertpapiertyp nicht anwendbar.")],
                50.0, False)
    institutional = dict(institutional_context or {})
    available = _has_fundamental_data(fundamentals)
    checks: list[AssessmentCheck] = []

    source = str(fundamentals.get("source") or "").strip()
    as_of = str(fundamentals.get("as_of") or "").strip()
    period = str(fundamentals.get("fiscal_period") or "").strip()
    detail_parts = [part for part in [source, period, as_of] if part]
    checks.append(
        AssessmentCheck(
            category="fundamental",
            label="Fundamental-Datenquelle",
            passed=available,
            detail=" · ".join(detail_parts) if detail_parts else "Noch kein Fundamental-Cache",
        )
    )

    eps_quarter_history = _normalize_eps_quarter_history(fundamentals.get("eps_quarter_history"))
    checks.append(_eps_three_quarter_growth_check(eps_quarter_history))

    eps_accel = _eps_growth_accelerating(eps_quarter_history)
    if eps_accel is None:
        eps_accel = _optional_bool(fundamentals.get("quarterly_eps_accelerating"))
    checks.append(
        AssessmentCheck(
            category="fundamental",
            label="Bonus: EPS-Beschleunigung letzte 3 Quartale",
            passed=bool(eps_accel),
            detail=_eps_acceleration_detail(eps_accel, eps_quarter_history),
        )
    )

    annual_eps_history = _normalize_annual_eps_history(fundamentals.get("annual_eps_history"))
    checks.append(_eps_three_year_growth_check(annual_eps_history))

    trailing_eps = _safe_float(fundamentals.get("trailing_eps"))
    checks.append(
        AssessmentCheck(
            category="fundamental",
            label="Summe EPS letzte 4 Quartale > 0",
            passed=trailing_eps is not None and trailing_eps > 0,
            detail=f"{trailing_eps:.2f}" if trailing_eps is not None else "Nicht verfügbar",
        )
    )

    revenue_quarter_history = _normalize_revenue_quarter_history(fundamentals.get("revenue_quarter_history"))
    checks.append(_revenue_three_quarter_growth_check(revenue_quarter_history))

    revenue_accel = _revenue_growth_accelerating(revenue_quarter_history)
    if revenue_accel is None:
        revenue_accel = _optional_bool(fundamentals.get("quarterly_revenue_accelerating"))
    checks.append(
        AssessmentCheck(
            category="fundamental",
            label="Bonus: Umsatz-Beschleunigung letzte 3 Quartale",
            passed=bool(revenue_accel),
            detail=_revenue_acceleration_detail(revenue_accel, revenue_quarter_history),
        )
    )

    annual_revenue_history = _normalize_annual_revenue_history(fundamentals.get("annual_revenue_history"))
    checks.append(_revenue_three_year_growth_check(annual_revenue_history))

    roe_history = _normalize_roe_history(fundamentals.get("roe_history"))
    checks.append(_roe_three_year_check(roe_history, current_roe=_safe_float(fundamentals.get("roe_pct"))))

    margin = _safe_float(fundamentals.get("profit_margin_pct"))
    checks.append(
        AssessmentCheck(
            category="fundamental",
            label="Gewinnmarge positiv",
            passed=margin is not None and margin > 0,
            detail=f"{margin:.1f}%" if margin is not None else "Nicht verfügbar",
        )
    )

    checks.append(_institutional_support_check(fundamentals, institutional))
    if instrument_type == "foreign_private_issuer":
        excluded = {"EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY",
                    "Bonus: EPS-Beschleunigung letzte 3 Quartale", "Summe EPS letzte 4 Quartale > 0",
                    "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY",
                    "Bonus: Umsatz-Beschleunigung letzte 3 Quartale"}
        checks = [check for check in checks if check.label not in excluded]
        margin_score = min(max(margin or 0, 0) / 25.0, 1.0) * 25.0
        score = (_eps_three_year_score(fundamentals, unit=25.0)
                 + _revenue_three_year_score(fundamentals, unit=25.0)
                 + _roe_three_year_score(fundamentals, unit=25.0)
                 + margin_score)
    else:
        score = _fundamental_checklist_score_100(checks, fundamentals)
    return checks, score if available else 50.0, available


def evaluate_chart_signs(
    df: pd.DataFrame,
    *,
    rs_context: Mapping[str, Any] | None = None,
    weekly_bars: pd.DataFrame | None = None,
) -> list[ChartSignal]:
    if len(df) < 50:
        return []
    rs = dict(rs_context or {})
    close = pd.to_numeric(df["Close"], errors="coerce")
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    open_ = pd.to_numeric(df["Open"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    pct = close.pct_change(fill_method=None)
    vol_avg_50 = volume.rolling(50).mean()
    sma10 = close.rolling(10, min_periods=10).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    weekly = weekly_bars if weekly_bars is not None else _weekly_bars(df)
    signals: list[ChartSignal] = []

    high_volume_up = int(((close.tail(20) > close.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    high_volume_down = int(((close.tail(20) < close.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    if high_volume_up > high_volume_down:
        signals.append(ChartSignal("positive", "Mehr Gewinn- als Verlusttage mit hohem Vol.", f"{high_volume_up} vs {high_volume_down} (20T)"))
    elif high_volume_down > high_volume_up:
        signals.append(ChartSignal("negative", "Mehr Verlust- als Gewinntage mit hohem Vol.", f"{high_volume_down} vs {high_volume_up} (20T)"))

    above_21_streak = _trailing_true_count(close > ema21)
    above_50_streak = _trailing_true_count(close > sma50)
    if above_21_streak >= 4 or above_50_streak >= 4:
        parts = []
        if above_21_streak >= 4:
            parts.append(f"{above_21_streak}T über 21-EMA")
        if above_50_streak >= 4:
            parts.append(f"{above_50_streak}T über 50-SMA")
        signals.append(ChartSignal("positive", "Leben über den Durchschnitten", ", ".join(parts)))
    below_21_streak = _trailing_true_count(close < ema21)
    below_50_streak = _trailing_true_count(close < sma50)
    if below_21_streak >= 4 or below_50_streak >= 4:
        parts = []
        if below_21_streak >= 4:
            parts.append(f"{below_21_streak}T unter 21-EMA")
        if below_50_streak >= 4:
            parts.append(f"{below_50_streak}T unter 50-SMA")
        signals.append(ChartSignal("negative", "Leben unter den Durchschnitten", ", ".join(parts)))

    e21 = _safe_float(ema21.iloc[-1])
    s50 = _safe_float(sma50.iloc[-1])
    s200 = _safe_float(sma200.iloc[-1])
    if e21 is not None and s50 is not None and s200 is not None:
        if e21 > s50 > s200:
            signals.append(ChartSignal("positive", "Durchschnitte in richtiger Ordnung", "21>50>200"))
        elif e21 < s50 < s200:
            signals.append(ChartSignal("negative", "Durchschnitte in falscher Ordnung", "21<50<200"))

    if len(ema21) >= 10 and s50 is not None:
        ema_up = bool(
            _safe_float(ema21.iloc[-1]) is not None
            and _safe_float(ema21.iloc[-10]) is not None
            and ema21.iloc[-1] > ema21.iloc[-10]
        )
        sma_up = bool(pd.notna(sma50.iloc[-10]) and sma50.iloc[-1] > sma50.iloc[-10])
        if ema_up and sma_up:
            signals.append(ChartSignal("positive", "Nach oben zeigende Durchschnittslinien"))
        elif not ema_up and not sma_up:
            signals.append(ChartSignal("negative", "Nach unten zeigende Durchschnittslinien"))

    close_range = _close_range_position(close, high, low)
    up_gaps = int(((open_.tail(10) > high.shift(1).tail(10)) & (close_range.tail(10) >= 0.5)).sum())
    down_gaps = int(((open_.tail(10) < low.shift(1).tail(10)) & (volume.tail(10) > vol_avg_50.tail(10))).sum())
    if up_gaps > 0:
        signals.append(ChartSignal("positive", "Positive Kurslücken", f"{up_gaps} in 10T, Schluss obere Hälfte"))
    if down_gaps > 0:
        signals.append(ChartSignal("negative", "Negative Kurslücken bei hohem Vol.", f"{down_gaps} in 10T"))

    material_drops = pct.tail(15) <= -0.009
    high_volume = (volume.tail(15) > volume.shift(1).tail(15)) | (volume.tail(15) > vol_avg_50.tail(15))
    low_volume_drops = int((material_drops & (volume.tail(15) < vol_avg_50.tail(15) * 0.8)).sum())
    high_volume_drops = int((material_drops & high_volume).sum())
    if low_volume_drops >= 3:
        signals.append(ChartSignal("positive", "Preisrückgänge bei niedrigem Vol.", f"{low_volume_drops}/15 Tage, Kurs <= -0.9%, Vol. <80% 50T"))
    if high_volume_drops >= 5:
        signals.append(ChartSignal("negative", "Preisrückgänge bei hohem Vol.", f"{high_volume_drops}/15 Tage, Kurs <= -0.9%, Vol. > Vortag oder 50T"))

    high_volume_rises = int(((pct.tail(15) >= 0.009) & ((volume.tail(15) > volume.shift(1).tail(15)) | (volume.tail(15) > vol_avg_50.tail(15)))).sum())
    if high_volume_rises >= 5:
        signals.append(ChartSignal("positive", "Preissteigerungen bei hohem Vol.", f"{high_volume_rises}/15 Tage, Kurs >= +0.9%, Vol. > Vortag oder 50T"))

    stall_days = int(((pct.tail(10).abs() <= 0.005) & (volume.tail(10) >= volume.shift(1).tail(10) * 0.95) & (close_range.tail(10) < 0.5)).sum())
    if stall_days >= 2:
        signals.append(ChartSignal("negative", "Stau-Tage", f"{stall_days} in 10T"))

    upside_reversals = int(((open_.tail(10) < close.shift(1).tail(10)) & (close.tail(10) > open_.tail(10)) & (close_range.tail(10) > 0.5)).sum())
    confirmed_downside_reversals = int(_confirmed_downside_reversal_mask(open_, high, close, close_range).tail(10).sum())
    if upside_reversals >= 2:
        signals.append(ChartSignal("positive", "Upside Reversals", f"{upside_reversals} in 10T"))
    if confirmed_downside_reversals >= 1:
        signals.append(ChartSignal("positive", "Bestätigte Downside Reversals", f"{confirmed_downside_reversals} in 10T, Folgetag über Hoch und Schluss obere 20%"))

    bullish_outside_days = int(_bullish_outside_day_mask(open_, high, low, close).tail(15).sum())
    if bullish_outside_days >= 1:
        signals.append(ChartSignal("positive", "Positiver Outside Day", f"{bullish_outside_days} in 15T"))

    bullish_engulfing = int(_bullish_engulfing_mask(open_, close, close_range).tail(15).sum())
    if bullish_engulfing >= 1:
        signals.append(ChartSignal("positive", "Bullish Engulfing", f"{bullish_engulfing} in 15T"))

    bearish_outside_days = int(_bearish_outside_day_mask(open_, high, low, close, close_range).tail(15).sum())
    if bearish_outside_days >= 1:
        signals.append(ChartSignal("negative", "Bearisher Outside Day", f"{bearish_outside_days} in 15T"))

    bearish_engulfing = int(_bearish_engulfing_mask(open_, close, close_range).tail(15).sum())
    if bearish_engulfing >= 1:
        signals.append(ChartSignal("negative", "Bearish Engulfing", f"{bearish_engulfing} in 15T"))

    support_week = _support_week_signal(open_, high, low, close, volume, sma50, weekly_bars=weekly)
    if support_week is not None:
        signals.append(support_week)

    signals.extend(_rs_chart_signals(rs))

    avg_close_range = _safe_float(close_range.tail(5).mean())
    if avg_close_range is not None and avg_close_range > 0.6:
        signals.append(ChartSignal("positive", "Schlussposition obere 40%", f"Ø {avg_close_range:.0%}"))
    elif avg_close_range is not None and avg_close_range < 0.25:
        signals.append(ChartSignal("negative", "Tiefe Schlussposition", f"Ø {avg_close_range:.0%}"))

    current_close = _safe_float(close.iloc[-1])
    distance_warnings = _moving_average_distance_warnings(
        current_close,
        {
            "10-SMA": (_safe_float(sma10.iloc[-1]), 10.0),
            "21-EMA": (_safe_float(ema21.iloc[-1]), 14.0),
            "50-SMA": (s50, 25.0),
            "200-SMA": (s200, 70.0),
        },
    )
    if distance_warnings:
        signals.append(ChartSignal("negative", "Großer Abstand zu Durchschnitten", ", ".join(distance_warnings)))

    weekly_close = weekly["Close"]
    if len(weekly_close) >= 6 and bool((weekly_close.pct_change(fill_method=None).tail(5) > 0).all()):
        signals.append(ChartSignal("positive", "5 positive Wochen in Folge"))

    if len(close) >= 2 and high.iloc[-1] <= high.iloc[-2] and low.iloc[-1] >= low.iloc[-2]:
        signals.append(ChartSignal("neutral", "Inside Day"))

    range_5d = _safe_float((high.tail(5).max() - low.tail(5).min()) / close.iloc[-1] * 100)
    if range_5d is not None and range_5d < 3:
        signals.append(ChartSignal("neutral", "Enge Konsolidierung", f"5T-Range: {range_5d:.1f}%"))

    if current_close is not None and e21 is not None and abs(low.iloc[-1] - e21) / e21 < 0.005:
        signals.append(ChartSignal("neutral", "Test der 21-EMA"))
    if current_close is not None and s50 is not None and abs(low.iloc[-1] - s50) / s50 < 0.005:
        signals.append(ChartSignal("neutral", "Test der 50-SMA"))

    signals.extend(_recent_reaction_signals(close, high, low, open_, pct, s50, volume, _safe_float(vol_avg_50.iloc[-1])))
    return _decorate_chart_signals(signals)


def _decorate_chart_signals(signals: Sequence[ChartSignal]) -> list[ChartSignal]:
    moving_average_labels = {
        "Leben über den Durchschnitten",
        "Leben unter den Durchschnitten",
        "Durchschnitte in richtiger Ordnung",
        "Durchschnitte in falscher Ordnung",
        "Nach oben zeigende Durchschnittslinien",
        "Nach unten zeigende Durchschnittslinien",
    }
    setup_labels = {
        "Großer Abstand zu Durchschnitten",
        "Natürliche Reaktion",
        "Test der 21-EMA",
        "Test der 50-SMA",
        "2,5-Tage-Korrektur",
        "Inside Day",
        "Enge Konsolidierung",
    }
    decorated: list[ChartSignal] = []
    for signal in signals:
        if signal.label in moving_average_labels:
            source = "moving_average"
            score_relevant = False
        elif signal.label.startswith("RS-") or signal.label.startswith("Schwaches RS"):
            source = "technical"
            score_relevant = False
        elif signal.label in setup_labels or signal.category == "neutral":
            source = "setup"
            score_relevant = False
        else:
            source = signal.source
            score_relevant = signal.score_relevant
        decorated.append(
            ChartSignal(
                category=signal.category,
                label=signal.label,
                detail=signal.detail,
                key=signal.key or _signal_key(signal.label),
                source=source,
                score_relevant=score_relevant,
                display_relevant=signal.display_relevant,
            )
        )
    return decorated


def _signal_key(label: str) -> str:
    clean = label.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return "_".join("".join(char if char.isalnum() else " " for char in clean).split())


def evaluate_negative_chart_signal_states(
    df: pd.DataFrame,
    *,
    rs_context: Mapping[str, Any] | None = None,
) -> dict[str, ChartSignalState]:
    """Return current values for every negative chart signal.

    ``evaluate_chart_signs`` intentionally returns active signals only. Alert
    transitions also need the current inactive value so a resolved message does
    not accidentally repeat the previous trigger value.
    """

    if len(df) < 50:
        return {}
    rs = dict(rs_context or {})
    close = pd.to_numeric(df["Close"], errors="coerce")
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    open_ = pd.to_numeric(df["Open"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    pct = close.pct_change(fill_method=None)
    vol_avg_50 = volume.rolling(50).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    close_range = _close_range_position(close, high, low)
    states: dict[str, ChartSignalState] = {}

    def add(label: str, *, active: bool, detail: str, available: bool = True) -> None:
        states[label] = ChartSignalState(active=active, available=available, detail=detail)

    high_volume_up = int(((close.tail(20) > close.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    high_volume_down = int(((close.tail(20) < close.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    add(
        "Mehr Verlust- als Gewinntage mit hohem Vol.",
        active=high_volume_down > high_volume_up,
        detail=f"Verlusttage {high_volume_down} vs Gewinntage {high_volume_up} (20T) · Warnung nur bei Verlusttage > Gewinntage",
    )

    below_21_streak = _trailing_true_count(close < ema21)
    below_50_streak = _trailing_true_count(close < sma50)
    add(
        "Leben unter den Durchschnitten",
        active=below_21_streak >= 4 or below_50_streak >= 4,
        detail=f"{below_21_streak}T unter 21-EMA · {below_50_streak}T unter 50-SMA · Warnung ab 4T",
    )

    e21 = _safe_float(ema21.iloc[-1])
    s50 = _safe_float(sma50.iloc[-1])
    s200 = _safe_float(sma200.iloc[-1])
    ma_available = e21 is not None and s50 is not None and s200 is not None
    add(
        "Durchschnitte in falscher Ordnung",
        active=bool(ma_available and e21 < s50 < s200),
        available=ma_available,
        detail=(
            f"21-EMA {e21:.2f} · 50-SMA {s50:.2f} · 200-SMA {s200:.2f} · Warnung bei 21<50<200"
            if ma_available
            else "200-SMA oder weitere Durchschnittsdaten fehlen"
        ),
    )

    slope_available = len(ema21) >= 10 and s50 is not None and pd.notna(sma50.iloc[-10])
    ema_up = bool(slope_available and ema21.iloc[-1] > ema21.iloc[-10])
    sma_up = bool(slope_available and sma50.iloc[-1] > sma50.iloc[-10])
    add(
        "Nach unten zeigende Durchschnittslinien",
        active=bool(slope_available and not ema_up and not sma_up),
        available=slope_available,
        detail=(
            f"21-EMA über 10T {'steigend' if ema_up else 'fallend'} · 50-SMA {'steigend' if sma_up else 'fallend'}"
            if slope_available
            else "Steigungsdaten der Durchschnitte fehlen"
        ),
    )

    down_gaps = int(((open_.tail(10) < low.shift(1).tail(10)) & (volume.tail(10) > vol_avg_50.tail(10))).sum())
    add(
        "Negative Kurslücken bei hohem Vol.",
        active=down_gaps > 0,
        detail=f"{down_gaps}/10 Tage · Warnung ab 1",
    )

    material_drops = pct.tail(15) <= -0.009
    high_volume = (volume.tail(15) > volume.shift(1).tail(15)) | (volume.tail(15) > vol_avg_50.tail(15))
    high_volume_drops = int((material_drops & high_volume).sum())
    add(
        "Preisrückgänge bei hohem Vol.",
        active=high_volume_drops >= 5,
        detail=f"{high_volume_drops}/15 Tage · Kurs <= -0,9% und Volumen > Vortag oder 50T · Warnung ab 5",
    )

    stall_days = int(((pct.tail(10).abs() <= 0.005) & (volume.tail(10) >= volume.shift(1).tail(10) * 0.95) & (close_range.tail(10) < 0.5)).sum())
    add("Stau-Tage", active=stall_days >= 2, detail=f"{stall_days}/10 Tage · Warnung ab 2")

    bearish_outside_days = int(_bearish_outside_day_mask(open_, high, low, close, close_range).tail(15).sum())
    add(
        "Bearisher Outside Day",
        active=bearish_outside_days >= 1,
        detail=f"{bearish_outside_days}/15 Tage · Warnung ab 1",
    )
    bearish_engulfing = int(_bearish_engulfing_mask(open_, close, close_range).tail(15).sum())
    add(
        "Bearish Engulfing",
        active=bearish_engulfing >= 1,
        detail=f"{bearish_engulfing}/15 Tage · Warnung ab 1",
    )

    trend_5w = rs.get("trend_5w")
    add(
        "RS-Linie fällt",
        active=trend_5w is False,
        available=isinstance(trend_5w, bool),
        detail=("5W-Trend fallend" if trend_5w is False else "5W-Trend steigend" if trend_5w is True else "5W-Trend nicht verfügbar"),
    )
    for label, state_key, average_key in (
        ("RS-Linie unter 21-EMA", "above_21", "ema21"),
        ("RS-Linie unter 50-SMA", "above_50", "sma50"),
    ):
        above = rs.get(state_key)
        add(
            label,
            active=above is False,
            available=isinstance(above, bool),
            detail=f"{_rs_line_detail(rs, average_key)} · aktuell {'darüber' if above is True else 'darunter' if above is False else 'nicht verfügbar'}",
        )

    distance_to_high = _safe_float(rs.get("distance_to_high_pct"))
    add(
        "RS-Linie deutlich unter Hoch",
        active=distance_to_high is not None and distance_to_high <= -10,
        available=distance_to_high is not None,
        detail=(f"{distance_to_high:+.1f}% zum RS-Hoch · Warnung ab -10,0%" if distance_to_high is not None else "Distanz zum RS-Hoch nicht verfügbar"),
    )
    rating = _safe_float(rs.get("rating"))
    add(
        "Schwaches RS-Rating",
        active=rating is not None and rating < 70,
        available=rating is not None,
        detail=(f"RS {int(rating)} · Warnung unter 70" if rating is not None else "RS-Rating nicht verfügbar"),
    )

    avg_close_range = _safe_float(close_range.tail(5).mean())
    add(
        "Tiefe Schlussposition",
        active=avg_close_range is not None and avg_close_range < 0.25,
        available=avg_close_range is not None,
        detail=(f"Ø {avg_close_range:.0%} in 5T · Warnung unter 25%" if avg_close_range is not None else "Schlussposition nicht verfügbar"),
    )

    current_close = _safe_float(close.iloc[-1])
    distance_warnings = _moving_average_distance_warnings(
        current_close,
        {
            "10-SMA": (_safe_float(close.rolling(10, min_periods=10).mean().iloc[-1]), 10.0),
            "21-EMA": (e21, 14.0),
            "50-SMA": (s50, 25.0),
            "200-SMA": (s200, 70.0),
        },
    )
    all_distances = _moving_average_distance_details(
        current_close,
        {
            "10-SMA": (_safe_float(close.rolling(10, min_periods=10).mean().iloc[-1]), 10.0),
            "21-EMA": (e21, 14.0),
            "50-SMA": (s50, 25.0),
            "200-SMA": (s200, 70.0),
        },
    )
    add(
        "Großer Abstand zu Durchschnitten",
        active=bool(distance_warnings),
        available=bool(all_distances),
        detail=", ".join(all_distances) if all_distances else "Abstände nicht verfügbar",
    )

    accelerated = False
    accelerated_detail = "Weniger als drei Veränderungswerte verfügbar"
    if len(pct.dropna()) >= 3:
        r1, r2, r3 = pct.iloc[-3] * 100, pct.iloc[-2] * 100, pct.iloc[-1] * 100
        accelerated = bool(r1 < 0 and r2 < 0 and r3 < 0 and r3 < r2 < r1 and r3 <= -2.0)
        accelerated_detail = f"letzte 3 Tage {r1:+.1f}% → {r2:+.1f}% → {r3:+.1f}%"
    add(
        "Beschleunigte Verluste",
        active=accelerated,
        available=len(pct.dropna()) >= 3,
        detail=accelerated_detail,
    )
    return states


def _rs_checks(rs_context: Mapping[str, Any]) -> list[AssessmentCheck]:
    rating = _safe_float(rs_context.get("rating"))
    checks: list[AssessmentCheck] = []
    if rating is None:
        for label in [
            "RS-Bewertung >=80",
            "RS-Bewertung >=90",
            "RS-Linie über 21-EMA",
            "RS-Linie über 50-SMA",
            "RS-Linie steigt über 5 Wochen",
            "RS-Linie steigt über 13 Wochen",
            "RS-Linie nahe 52W-Hoch",
        ]:
            checks.append(_missing_check("technical", label))
        return checks

    label = "Elite" if rating >= 90 else "Stark" if rating >= 80 else "Meiden (<70)" if rating < 70 else "OK"
    checks.append(
        AssessmentCheck(
            category="technical",
            label="RS-Bewertung >=80",
            passed=rating >= 80,
            detail=f"RS: {int(rating)} ({label})",
        )
    )
    checks.append(
        AssessmentCheck(
            category="technical",
            label="RS-Bewertung >=90",
            passed=rating >= 90,
            detail=f"Aktuell {int(rating)}",
        )
    )
    checks.append(
        AssessmentCheck(
            category="technical",
            label="RS-Linie über 21-EMA",
            passed=bool(rs_context.get("above_21")),
            detail=_rs_line_detail(rs_context, "ema21"),
        )
    )
    checks.append(
        AssessmentCheck(
            category="technical",
            label="RS-Linie über 50-SMA",
            passed=bool(rs_context.get("above_50")),
            detail=_rs_line_detail(rs_context, "sma50"),
        )
    )
    checks.append(
        AssessmentCheck(
            category="technical",
            label="RS-Linie steigt über 5 Wochen",
            passed=bool(rs_context.get("trend_5w")),
            detail=_pct_detail(rs_context.get("excess_return_3m_pct"), "Excess 3M"),
        )
    )
    checks.append(
        AssessmentCheck(
            category="technical",
            label="RS-Linie steigt über 13 Wochen",
            passed=bool(rs_context.get("trend_13w")),
            detail=_pct_detail(rs_context.get("excess_return_6m_pct"), "Excess 6M"),
        )
    )
    distance = _safe_float(rs_context.get("distance_to_high_pct"))
    near_high = bool(rs_context.get("near_high_52w"))
    checks.append(
        AssessmentCheck(
            category="technical",
            label="RS-Linie nahe 52W-Hoch",
            passed=near_high,
            detail="Neues RS-Hoch" if rs_context.get("new_high_52w") else f"{distance:+.1f}% zum RS-Hoch" if distance is not None else "Nicht verfügbar",
        )
    )
    return checks


def _compute_metrics(
    df: pd.DataFrame,
    *,
    cmf_value: float | None,
    rs_context: Mapping[str, Any],
    fundamentals_context: Mapping[str, Any],
    earnings: EarningsWarning | None,
) -> StockAssessmentMetrics:
    close = pd.to_numeric(df["Close"], errors="coerce")
    high = pd.to_numeric(df["High"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    price = _safe_float(close.iloc[-1])
    previous = _safe_float(close.iloc[-2]) if len(close) >= 2 else None
    change_pct = (price / previous - 1) * 100 if price is not None and previous else None
    atr = _atr(df, 21)
    atr_value = _safe_float(atr.iloc[-1]) if len(atr) else None
    atr_pct = (atr_value / price * 100) if atr_value is not None and price else None
    avg_volume_50 = _safe_float(volume.rolling(50, min_periods=20).mean().iloc[-1])
    volume_ratio_50d = _safe_float(volume.iloc[-1] / avg_volume_50) if avg_volume_50 else None
    avg_volume_20 = _safe_float(volume.tail(20).mean())
    dollar_volume_mio = avg_volume_20 * price / 1_000_000 if avg_volume_20 is not None and price else None
    high_52w = _safe_float(high.rolling(252, min_periods=50).max().iloc[-1])
    drawdown_52w_pct = (price / high_52w - 1) * 100 if price is not None and high_52w else None
    sma10 = close.rolling(10, min_periods=10).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    return StockAssessmentMetrics(
        last_close=price,
        change_pct=change_pct,
        atr_pct=atr_pct,
        volume_ratio_50d=volume_ratio_50d,
        dollar_volume_mio=dollar_volume_mio,
        cmf_20=cmf_value,
        drawdown_52w_pct=drawdown_52w_pct,
        distance_sma10_pct=_distance_pct(price, _safe_float(sma10.iloc[-1])),
        distance_ema21_pct=_distance_pct(price, _safe_float(ema21.iloc[-1])),
        distance_sma50_pct=_distance_pct(price, _safe_float(sma50.iloc[-1])),
        distance_sma200_pct=_distance_pct(price, _safe_float(sma200.iloc[-1])),
        rs_rating=_int_or_none(rs_context.get("rating")),
        rs_percentile=_safe_float(rs_context.get("percentile")),
        beta=_safe_float(fundamentals_context.get("beta")),
        next_earnings_calendar_days=earnings.calendar_days if earnings else None,
        next_earnings_trading_days=earnings.trading_days if earnings else None,
    )


def _component(
    score: float | None,
    status: ScoreStatus,
    *,
    raw: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    clean_score = None if score is None else float(np.clip(score, 0.0, 100.0))
    quality = "full" if status in {"available", "neutral"} else "partial" if status == "partial" else "missing"
    return {
        "score": clean_score,
        "base_weight": 0.0,
        "effective_weight": 0.0,
        "status": status,
        "data_quality": quality,
        "raw": dict(raw or {}),
    }


def _weighted_score(
    components: Mapping[str, Mapping[str, Any]],
    weights: Mapping[str, float],
) -> dict[str, Any]:
    total_weight = float(sum(weights.values()))
    scoreable = [
        key
        for key, component in components.items()
        if component.get("status") in SCOREABLE_STATUSES and _safe_float(component.get("score")) is not None
    ]
    scoreable_weight = float(sum(weights[key] for key in scoreable))
    output_components: dict[str, dict[str, Any]] = {}
    for key, component in components.items():
        item = dict(component)
        item["base_weight"] = weights[key] / total_weight
        item["effective_weight"] = weights[key] / scoreable_weight if key in scoreable and scoreable_weight else 0.0
        output_components[key] = item

    coverage_statuses = {"available", "partial", "neutral"}
    covered_weight = sum(
        weights[key]
        for key, component in components.items()
        if component.get("status") in coverage_statuses
    )
    data_coverage = covered_weight / total_weight if total_weight else 0.0
    if not scoreable_weight:
        statuses = {str(component.get("status")) for component in components.values()}
        status: ScoreStatus = "insufficient_history" if "insufficient_history" in statuses else "missing"
        score = None
    else:
        score = sum(float(components[key]["score"]) * weights[key] for key in scoreable) / scoreable_weight
        status = "available" if scoreable_weight == total_weight and all(components[key].get("status") == "available" for key in scoreable) else "partial"
    return {
        "score": score,
        "status": status,
        "available_weight": scoreable_weight / total_weight if total_weight else 0.0,
        "data_coverage": data_coverage,
        "data_quality": "full" if data_coverage == 1.0 else "partial" if data_coverage > 0 else "missing",
        "components": output_components,
    }


def _weight_group(
    configured: Mapping[str, Mapping[str, float]],
    key: str,
    default: Mapping[str, int],
) -> dict[str, float]:
    candidate = configured.get(key)
    if not isinstance(candidate, Mapping) or set(candidate) != set(default):
        return {name: float(weight) for name, weight in default.items()}
    weights = {name: float(candidate[name]) for name in default}
    if any(not np.isfinite(weight) or weight < 0 for weight in weights.values()) or sum(weights.values()) <= 0:
        return {name: float(weight) for name, weight in default.items()}
    return weights


def _technical_score_v2(
    df: pd.DataFrame,
    technical_checks: Sequence[AssessmentCheck],
    metrics: StockAssessmentMetrics,
    rs_context: Mapping[str, Any],
    cmf_value: float | None,
    *,
    weights: Mapping[str, float] = TECHNICAL_WEIGHTS,
) -> dict[str, Any]:
    check_map = {check.label: check for check in technical_checks}
    k4 = _k4_rs_leadership(rs_context)
    k13 = _k13_rs_dynamics(rs_context)

    rating = _safe_float(metrics.rs_rating)
    rating_component = _component(
        (rating - 1.0) / 98.0 * 100.0 if rating is not None else None,
        "available" if rating is not None else "missing",
        raw={"rating": rating, "mapping": "(rating - 1) / 98 * 100"},
    )

    ath_points = 0.0
    high_52w_points = 0.0
    high_available = False
    ath_check = check_map.get("Entfernung zum All-Time-High")
    high_52w_check = check_map.get("Entfernung zum 52-Wochen-Hoch")
    if ath_check and ath_check.detail != "Nicht verfügbar":
        high_available = True
        ath_points = 8.0 if ath_check.passed else 0.0
    if high_52w_check and high_52w_check.detail != "Nicht verfügbar":
        high_available = True
        high_52w_points = 4.0 if high_52w_check.passed else 0.0
    high_points = ath_points + high_52w_points
    high_position = _component(
        high_points / 12.0 * 100.0 if high_available else None,
        "available" if high_available else "missing",
        raw={"ath_points": ath_points, "high_52w_points": high_52w_points, "max_points": 12},
    )

    close = pd.to_numeric(df["Close"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    pct_change = close.pct_change(fill_method=None)
    up_volume = _safe_float(volume.where(pct_change > 0).tail(50).sum())
    down_volume = _safe_float(volume.where(pct_change < 0).tail(50).sum())
    ratio = up_volume / down_volume if up_volume is not None and down_volume not in {None, 0.0} else None
    up_down = _component(
        100.0 if ratio is not None and ratio >= 1.0 else 0.0 if ratio is not None else None,
        "available" if ratio is not None else "missing",
        raw={"up_volume": up_volume, "down_volume": down_volume, "ratio": ratio, "threshold": 1.0},
    )

    cmf_grade = _cmf_rating(cmf_value)[0]
    cmf_score = 100.0 if cmf_grade == "A" else (10.0 / 15.0 * 100.0) if cmf_grade == "B" else 0.0
    cmf = _component(
        cmf_score if cmf_value is not None else None,
        "available" if cmf_value is not None else "missing",
        raw={"cmf_20": cmf_value, "rating": cmf_grade},
    )
    result = _weighted_score(
        {
            "k4_rs_leadership": _component(k4.get("score"), k4["status"], raw=k4),
            "k13_rs_dynamics": _component(k13.get("score"), k13["status"], raw=k13),
            "rs_rating": rating_component,
            "high_position": high_position,
            "up_down_volume": up_down,
            "cmf": cmf,
        },
        weights,
    )
    result["weights"] = dict(weights)
    return result


def _k4_rs_leadership(rs_context: Mapping[str, Any]) -> dict[str, Any]:
    rs_value = _safe_float(rs_context.get("rs_line_last"))
    ema21 = _safe_float(rs_context.get("ema21"))
    sma50 = _safe_float(rs_context.get("sma50"))
    above_21 = rs_context.get("above_21") if isinstance(rs_context.get("above_21"), bool) else None
    above_50 = rs_context.get("above_50") if isinstance(rs_context.get("above_50"), bool) else None
    components: dict[str, Mapping[str, Any]] = {
        "above_21_ema": _component(
            100.0 if above_21 is True else 0.0 if above_21 is False else None,
            "available" if above_21 is not None else "missing",
            raw={"above_21_ema": above_21, "rs_line": rs_value, "rs_ema21": ema21},
        ),
        "above_50_sma": _component(
            100.0 if above_50 is True else 0.0 if above_50 is False else None,
            "available" if above_50 is not None else "missing",
            raw={"above_50_sma": above_50, "rs_line": rs_value, "rs_sma50": sma50},
        ),
    }

    history = [dict(item) for item in rs_context.get("rs_history", []) if isinstance(item, Mapping)]
    persistence_rows = history[-63:]
    above_21_values = [
        float(item["rs"]) > float(item["rs_ema21"])
        for item in persistence_rows
        if _safe_float(item.get("rs")) is not None and _safe_float(item.get("rs_ema21")) is not None
    ]
    above_50_values = [
        float(item["rs"]) > float(item["rs_sma50"])
        for item in persistence_rows
        if _safe_float(item.get("rs")) is not None and _safe_float(item.get("rs_sma50")) is not None
    ]
    if above_21_values and above_50_values:
        persistence_21 = sum(above_21_values) / len(above_21_values) * 100.0
        persistence_50 = sum(above_50_values) / len(above_50_values) * 100.0
        combined = 0.60 * persistence_21 + 0.40 * persistence_50
        persistence_score = _persistence_bucket(combined)
        persistence_status: ScoreStatus = "available" if min(len(above_21_values), len(above_50_values)) >= 63 else "partial"
    else:
        persistence_21 = persistence_50 = combined = persistence_score = None
        persistence_status = "insufficient_history" if history else "missing"
    components["persistence"] = _component(
        persistence_score,
        persistence_status,
        raw={
            "persistence_window_days": 63,
            "persistence_21_pct": persistence_21,
            "persistence_50_pct": persistence_50,
            "combined_persistence_pct": combined,
            "available_days_21": len(above_21_values),
            "available_days_50": len(above_50_values),
        },
    )

    distance_to_high = _safe_float(rs_context.get("distance_to_high_pct"))
    new_high = rs_context.get("new_high_52w") is True
    high_score = _rs_high_score(distance_to_high, new_high=new_high)
    components["rs_52w_high"] = _component(
        high_score,
        "available" if high_score is not None else "missing",
        raw={"distance_to_rs_52w_high_pct": distance_to_high, "new_rs_52w_high": new_high},
    )

    distance_21 = _distance_pct(rs_value, ema21)
    distance_50 = _distance_pct(rs_value, sma50)
    separation_21 = float(np.clip((distance_21 or 0.0) / 1.5 * 100.0, 0.0, 100.0)) if distance_21 is not None else None
    separation_50 = float(np.clip((distance_50 or 0.0) / 3.0 * 100.0, 0.0, 100.0)) if distance_50 is not None else None
    current_separation = 0.60 * separation_21 + 0.40 * separation_50 if separation_21 is not None and separation_50 is not None else None
    stability_rows = []
    for item in history[-20:]:
        item_rs = _safe_float(item.get("rs"))
        item_21 = _safe_float(item.get("rs_ema21"))
        item_50 = _safe_float(item.get("rs_sma50"))
        item_distance_21 = _distance_pct(item_rs, item_21)
        item_distance_50 = _distance_pct(item_rs, item_50)
        if item_distance_21 is None or item_distance_50 is None:
            continue
        stability_rows.append(item_distance_21 >= 0.25 and item_distance_50 >= 0.50)
    if current_separation is not None and stability_rows:
        positive_ratio = sum(stability_rows) / len(stability_rows)
        stability_score = positive_ratio * 100.0
        white_space_score = float(np.clip(0.35 * current_separation + 0.65 * stability_score, 0.0, 100.0))
        white_space_status: ScoreStatus = "available" if len(stability_rows) >= 20 else "partial"
    else:
        positive_ratio = stability_score = white_space_score = None
        white_space_status = "insufficient_history" if history else "missing"
    components["white_space"] = _component(
        white_space_score,
        white_space_status,
        raw={
            "distance_rs_to_21_pct": distance_21,
            "distance_rs_to_50_pct": distance_50,
            "current_separation": current_separation,
            "positive_separation_ratio": positive_ratio,
            "stability_score": stability_score,
            "white_space_score": white_space_score,
            "available_days": len(stability_rows),
        },
    )
    result = _weighted_score(components, K4_WEIGHTS)
    result["weights"] = dict(K4_WEIGHTS)
    return result


def _persistence_bucket(value: float) -> float:
    if value >= 90:
        return 100.0
    if value >= 75:
        return 90.0
    if value >= 60:
        return 75.0
    if value >= 40:
        return 50.0
    if value >= 20:
        return 25.0
    return 0.0


def _rs_high_score(distance: float | None, *, new_high: bool) -> float | None:
    if new_high:
        return 100.0
    if distance is None:
        return None
    if distance >= -2:
        return 95.0
    if distance >= -5:
        return 85.0
    if distance >= -10:
        return 60.0
    if distance >= -15:
        return 35.0
    return 10.0


def _k13_rs_dynamics(rs_context: Mapping[str, Any]) -> dict[str, Any]:
    rs_3m = _safe_float(rs_context.get("rs_3m_rating", rs_context.get("rs_3m_percentile")))
    rs_6m = _safe_float(rs_context.get("rs_6m_rating", rs_context.get("rs_6m_percentile")))
    rs_12m = _safe_float(rs_context.get("rs_12m_rating", rs_context.get("rs_12m_percentile")))
    if rs_3m is None or rs_6m is None or rs_12m is None:
        return {
            **_weighted_score(
                {
                    "three_vs_six": _component(None, "missing"),
                    "six_vs_twelve": _component(None, "missing"),
                    "sequence": _component(None, "missing"),
                    "acceleration": _component(None, "missing"),
                },
                K13_WEIGHTS,
            ),
            "weights": dict(K13_WEIGHTS),
            "raw": {"rs_3m": rs_3m, "rs_6m": rs_6m, "rs_12m": rs_12m},
        }
    delta_3_6 = rs_3m - rs_6m
    delta_6_12 = rs_6m - rs_12m
    acceleration = 0.60 * delta_3_6 + 0.40 * delta_6_12
    components = {
        "three_vs_six": _component(_delta_score(delta_3_6), "available", raw={"delta": delta_3_6}),
        "six_vs_twelve": _component(_delta_score(delta_6_12), "available", raw={"delta": delta_6_12}),
        "sequence": _component(
            _sequence_score(rs_3m, rs_6m, rs_12m),
            "available",
            raw={"rs_3m": rs_3m, "rs_6m": rs_6m, "rs_12m": rs_12m},
        ),
        "acceleration": _component(_delta_score(acceleration), "available", raw={"acceleration_strength": acceleration}),
    }
    result = _weighted_score(components, K13_WEIGHTS)
    result["weights"] = dict(K13_WEIGHTS)
    result["raw"] = {
        "rs_3m": rs_3m,
        "rs_6m": rs_6m,
        "rs_12m": rs_12m,
        "delta_3m_6m": delta_3_6,
        "delta_6m_12m": delta_6_12,
        "acceleration_strength": acceleration,
    }
    return result


def _delta_score(delta: float) -> float:
    if delta >= 10:
        return 100.0
    if delta >= 5:
        return 85.0
    if delta >= 2:
        return 70.0
    if delta > -2:
        return 50.0
    if delta > -5:
        return 30.0
    if delta > -10:
        return 15.0
    return 0.0


def _sequence_score(rs_3m: float, rs_6m: float, rs_12m: float) -> float:
    d36 = rs_3m - rs_6m
    d612 = rs_6m - rs_12m
    flat36 = abs(d36) < 2
    flat612 = abs(d612) < 2
    if d36 >= 2 and d612 >= 2:
        return 100.0
    if d36 >= 2 and flat612:
        return 80.0
    if flat36 and d612 >= 2:
        return 75.0
    if flat36 and flat612:
        return 50.0
    if d36 <= -2 and flat612:
        return 20.0
    if flat36 and d612 <= -2:
        return 25.0
    if d36 <= -2 and d612 <= -2:
        return 0.0
    total = rs_3m - rs_12m
    if total >= 2:
        return 60.0
    if abs(total) < 2:
        return 50.0
    return 40.0


def _fundamental_score_v2(
    fundamentals_context: Mapping[str, Any],
    *,
    core_score: float,
    core_available: bool,
    weights: Mapping[str, float] = FUNDAMENTAL_WEIGHTS,
) -> dict[str, Any]:
    k9 = _k9_eps_sales_alignment(fundamentals_context)
    core_status: ScoreStatus = "available" if core_available else "missing"
    result = _weighted_score(
        {
            "fundamental_core": _component(
                core_score if core_available else None,
                core_status,
                raw={"legacy_core_score": core_score, "thresholds_unchanged": True},
            ),
            "k9_eps_sales_alignment": _component(k9.get("score"), k9["status"], raw=k9),
        },
        weights,
    )
    result["weights"] = dict(weights)
    return result


def _k9_eps_sales_alignment(fundamentals_context: Mapping[str, Any], *, noise_pct: float = 3.0) -> dict[str, Any]:
    eps_history = fundamentals_context.get("eps_quarter_history")
    revenue_history = fundamentals_context.get("revenue_quarter_history")
    eps_rows = [dict(item) for item in eps_history if isinstance(item, Mapping)] if isinstance(eps_history, list) else []
    revenue_rows = [dict(item) for item in revenue_history if isinstance(item, Mapping)] if isinstance(revenue_history, list) else []

    revenue_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in revenue_rows:
        key = _quarter_match_key(row)
        if key is not None and key not in revenue_by_key:
            revenue_by_key[key] = row
    matches: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()
    for eps_row in eps_rows:
        key = _quarter_match_key(eps_row)
        if key is None or key in used or key not in revenue_by_key:
            continue
        sales_row = revenue_by_key[key]
        eps_growth = _quarter_growth(eps_row, kind="eps")
        sales_growth = _quarter_growth(sales_row, kind="revenue")
        if eps_growth is None or sales_growth is None:
            continue
        score, trigger, reason = _k9_quarter_score(eps_growth, sales_growth, noise_pct=noise_pct)
        matches.append(
            {
                "period": _quarter_period(eps_row, key),
                "match_method": key[0],
                "eps_growth_yoy_pct": eps_growth,
                "revenue_growth_yoy_pct": sales_growth,
                "divergence_pp": eps_growth - sales_growth,
                "score": score,
                "research_trigger": trigger,
                "research_reason": reason,
            }
        )
        used.add(key)
        if len(matches) == 3:
            break

    if len(matches) >= 2:
        weights = [50, 30, 20][: len(matches)]
        weighted = sum(item["score"] * weight for item, weight in zip(matches, weights, strict=True)) / sum(weights)
        persistent_count = sum(
            item["eps_growth_yoy_pct"] > noise_pct and item["revenue_growth_yoy_pct"] < -noise_pct
            for item in matches[:3]
        )
        if persistent_count >= 3:
            weighted = min(weighted, 20.0)
        elif persistent_count >= 2:
            weighted = min(weighted, 35.0)
        status: ScoreStatus = "available" if len(matches) >= 3 else "partial"
        return {
            "score": weighted,
            "status": status,
            "noise_pct": noise_pct,
            "matched_quarters": matches,
            "persistent_divergence": persistent_count >= 2,
            "persistent_divergence_quarters": persistent_count,
            "research_trigger": any(item["research_trigger"] for item in matches),
            "research_reasons": list(dict.fromkeys(item["research_reason"] for item in matches if item["research_reason"])),
        }
    return {
        "score": None,
        "status": "insufficient_history" if len(matches) == 1 else "missing",
        "noise_pct": noise_pct,
        "matched_quarters": matches,
        "persistent_divergence": False,
        "persistent_divergence_quarters": 0,
        "research_trigger": bool(matches and matches[0]["research_trigger"]),
        "research_reasons": [matches[0]["research_reason"]] if matches and matches[0]["research_reason"] else [],
    }


def _quarter_match_key(row: Mapping[str, Any]) -> tuple[str, str] | None:
    fiscal_year = str(row.get("fiscal_year") or row.get("fiscalYear") or "").strip()
    fiscal_period = str(row.get("fiscal_period") or row.get("fiscalPeriod") or row.get("period") or row.get("label") or "").strip()
    if fiscal_year and fiscal_period:
        return "fiscal_year_period", f"{fiscal_year}:{fiscal_period}".upper()
    for key in ("period_end_date", "period_end", "periodEndDate"):
        value = str(row.get(key) or "").strip()
        if value:
            return "period_end_date", value
    for key in ("period_key", "periodKey"):
        value = str(row.get(key) or "").strip()
        if value:
            return "period_key", value.upper()
    # Existing caches commonly persist a unique label such as "Q2 2026" as
    # fiscal_period without a separate fiscal_year.
    if fiscal_period:
        return "period_key", fiscal_period.upper()
    for key in ("report_date", "reportDate"):
        value = str(row.get(key) or "").strip()
        if value:
            return "report_date", value
    return None


def _quarter_period(row: Mapping[str, Any], key: tuple[str, str]) -> str:
    fiscal_year = str(row.get("fiscal_year") or row.get("fiscalYear") or "").strip()
    fiscal_period = str(row.get("fiscal_period") or row.get("fiscalPeriod") or row.get("period") or row.get("label") or "").strip()
    return " ".join(part for part in (fiscal_period, fiscal_year) if part) or key[1]


def _quarter_growth(row: Mapping[str, Any], *, kind: Literal["eps", "revenue"]) -> float | None:
    direct = _safe_float(row.get(f"{kind}_growth_yoy_pct", row.get("growth_pct")))
    if direct is not None:
        return direct
    current_key = "eps_current_quarter" if kind == "eps" else "revenue_current_quarter"
    previous_key = "eps_same_quarter_last_year" if kind == "eps" else "revenue_same_quarter_last_year"
    current = _safe_float(row.get(current_key, row.get("current")))
    previous = _safe_float(row.get(previous_key, row.get("previous")))
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _k9_quarter_score(eps: float, sales: float, *, noise_pct: float) -> tuple[float, bool, str]:
    eps_class = "positive" if eps > noise_pct else "negative" if eps < -noise_pct else "neutral"
    sales_class = "positive" if sales > noise_pct else "negative" if sales < -noise_pct else "neutral"
    gap = abs(eps - sales)
    if eps_class == "positive" and sales_class == "positive":
        score = 100.0 if gap <= 10 else 85.0 if gap <= 20 else 70.0 if gap <= 35 else 55.0
        return score, gap > 35, "EPS-Wachstum deutlich stärker als Umsatzwachstum" if gap > 35 and eps > sales else ""
    if eps_class == "positive" and sales_class == "neutral":
        return 60.0, gap > 35, "EPS-Wachstum deutlich stärker als Umsatzwachstum" if gap > 35 else ""
    if eps_class == "neutral" and sales_class == "positive":
        return 55.0, False, ""
    if eps_class == "neutral" and sales_class == "neutral":
        return 50.0, False, ""
    if eps_class == "positive" and sales_class == "negative":
        score = 25.0 if sales >= -10 else 10.0
        divergence = eps - sales
        score -= 10.0 if divergence > 50 else 5.0 if divergence > 35 else 0.0
        return max(10.0, score), True, "EPS wächst trotz rückläufigem Umsatz"
    if eps_class == "negative" and sales_class == "positive":
        return 30.0, True, "Umsatz wächst trotz rückläufigem EPS"
    if eps_class == "negative" and sales_class == "negative":
        return 25.0, False, ""
    if eps_class == "neutral" and sales_class == "negative":
        return 35.0, gap > 35, "Umsatzrückgang bei stabilem EPS" if gap > 35 else ""
    return 35.0, gap > 35, "EPS-Rückgang bei stabilem Umsatz" if gap > 35 else ""


def _moving_average_score_v2(
    df: pd.DataFrame,
    *,
    weights: Mapping[str, float] = MOVING_AVERAGE_WEIGHTS,
) -> dict[str, Any]:
    close = pd.to_numeric(df["Close"], errors="coerce")
    price = _safe_float(close.iloc[-1])
    series = {
        "price_above_200_sma": close.rolling(200, min_periods=200).mean(),
        "price_above_50_sma": close.rolling(50, min_periods=50).mean(),
        "price_above_21_ema": close.ewm(span=21, adjust=False).mean(),
        "price_above_10_sma": close.rolling(10, min_periods=10).mean(),
    }
    components: dict[str, Mapping[str, Any]] = {}
    for key, average_series in series.items():
        average = _safe_float(average_series.iloc[-1])
        components[key] = _component(
            100.0 if price is not None and average is not None and price > average else 0.0 if price is not None and average is not None else None,
            "available" if price is not None and average is not None else "insufficient_history",
            raw={"price": price, "average": average, "above": price > average if price is not None and average is not None else None},
        )
    ema21 = series["price_above_21_ema"]
    sma50 = series["price_above_50_sma"]
    sma200 = series["price_above_200_sma"]
    e21 = _safe_float(ema21.iloc[-1])
    s50 = _safe_float(sma50.iloc[-1])
    s200 = _safe_float(sma200.iloc[-1])
    order_available = e21 is not None and s50 is not None and s200 is not None
    components["ma_order"] = _component(
        100.0 if order_available and e21 > s50 > s200 else 0.0 if order_available else None,
        "available" if order_available else "insufficient_history",
        raw={"ema21": e21, "sma50": s50, "sma200": s200, "ordered": e21 > s50 > s200 if order_available else None},
    )

    streak_21 = _ma_streak_score(close, ema21)
    streak_50 = _ma_streak_score(close, sma50)
    if streak_21["score"] is not None and streak_50["score"] is not None:
        persistence_score = 0.40 * streak_21["score"] + 0.60 * streak_50["score"]
        persistence_status: ScoreStatus = "available"
    else:
        persistence_score = None
        persistence_status = "insufficient_history"
    components["persistence"] = _component(
        persistence_score,
        persistence_status,
        raw={
            "above_21_streak_days": streak_21["above_streak_days"],
            "below_21_streak_days": streak_21["below_streak_days"],
            "above_50_streak_days": streak_50["above_streak_days"],
            "below_50_streak_days": streak_50["below_streak_days"],
            "ema21": streak_21,
            "sma50": streak_50,
            "weights": {"ema21": 40, "sma50": 60},
        },
    )

    change_21 = _series_change_pct(ema21, periods=10)
    change_50 = _series_change_pct(sma50, periods=10)
    if change_21 is not None and change_50 is not None:
        direction_21 = _slope_direction(change_21)
        direction_50 = _slope_direction(change_50)
        slope_score = _ma_slope_score(direction_21, direction_50)
        slope_status: ScoreStatus = "available"
    else:
        direction_21 = direction_50 = None
        slope_score = None
        slope_status = "insufficient_history"
    components["slope"] = _component(
        slope_score,
        slope_status,
        raw={
            "lookback_trading_days": 10,
            "flat_tolerance_pct": 0.2,
            "ema21_change_pct": change_21,
            "sma50_change_pct": change_50,
            "ema21_direction": direction_21,
            "sma50_direction": direction_50,
        },
    )
    result = _weighted_score(components, weights)
    result["weights"] = dict(weights)
    return result


def _ma_streak_score(close: pd.Series, average: pd.Series) -> dict[str, Any]:
    available = close.notna() & average.notna()
    if not bool(available.iloc[-1]):
        return {"score": None, "above_streak_days": 0, "below_streak_days": 0}
    above = close > average
    above_streak = _trailing_true_count(above)
    below_streak = _trailing_true_count(close <= average)
    if above_streak >= 20:
        score = 100.0
    elif above_streak >= 10:
        score = 85.0
    elif above_streak >= 4:
        score = 70.0
    elif above_streak >= 1:
        score = 55.0
    elif below_streak <= 3:
        score = 45.0
    elif below_streak <= 9:
        score = 25.0
    else:
        score = 0.0
    return {"score": score, "above_streak_days": above_streak, "below_streak_days": below_streak}


def _series_change_pct(series: pd.Series, *, periods: int) -> float | None:
    if len(series) <= periods:
        return None
    current = _safe_float(series.iloc[-1])
    previous = _safe_float(series.iloc[-periods - 1])
    return _distance_pct(current, previous)


def _slope_direction(change_pct: float) -> Literal["up", "flat", "down"]:
    if abs(change_pct) < 0.2:
        return "flat"
    return "up" if change_pct > 0 else "down"


def _ma_slope_score(
    direction_21: Literal["up", "flat", "down"],
    direction_50: Literal["up", "flat", "down"],
) -> float:
    return {
        ("up", "up"): 100.0,
        ("up", "flat"): 80.0,
        ("flat", "up"): 85.0,
        ("up", "down"): 55.0,
        ("down", "up"): 60.0,
        ("flat", "flat"): 50.0,
        ("down", "flat"): 30.0,
        ("flat", "down"): 25.0,
        ("down", "down"): 10.0,
    }[(direction_21, direction_50)]


def _weekly_bars(df: pd.DataFrame) -> pd.DataFrame:
    return df[["Open", "High", "Low", "Close", "Volume"]].resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Open", "High", "Low", "Close"])


def _completed_weekly_bars(df: pd.DataFrame, *, weekly_bars: pd.DataFrame | None = None) -> pd.DataFrame:
    weekly = weekly_bars if weekly_bars is not None else _weekly_bars(df)
    if weekly.empty:
        return weekly
    last_session = pd.Timestamp(df.index[-1]).normalize()
    return weekly.loc[weekly.index.normalize() <= last_session]


def _chart_score_v2(
    chart_signals: Sequence[ChartSignal],
    weekly: pd.DataFrame,
    *,
    weights: Mapping[str, float] = CHART_WEIGHTS,
) -> dict[str, Any]:
    scored_signals = [signal for signal in chart_signals if signal.score_relevant]
    positive_count = sum(signal.category == "positive" for signal in scored_signals)
    negative_count = sum(signal.category == "negative" for signal in scored_signals)
    price_action_score = float(_chart_behavior_score_100(positive_count, negative_count))
    k35 = _k35_down_week_quality(weekly)
    k38 = _k38_hh_hl_good_close(weekly)
    result = _weighted_score(
        {
            "price_action_core": _component(
                price_action_score,
                "available",
                raw={
                    "positive_count": positive_count,
                    "negative_count": negative_count,
                    "scored_signal_keys": [signal.key or signal.label for signal in scored_signals],
                },
            ),
            "k35_down_week_quality": _component(k35.get("score"), k35["status"], raw=k35),
            "k38_hh_hl_good_close": _component(k38.get("score"), k38["status"], raw=k38),
        },
        weights,
    )
    result["weights"] = dict(weights)
    return result


def _k35_down_week_quality(weekly: pd.DataFrame) -> dict[str, Any]:
    if len(weekly) < 14:
        return {"score": None, "status": "insufficient_history", "lookback_weeks": 13, "down_weeks": []}
    frame = weekly.tail(14).copy()
    frame["previous_close"] = frame["Close"].shift(1)
    relevant = frame.iloc[1:].loc[frame.iloc[1:]["Close"] < frame.iloc[1:]["previous_close"]].tail(3)
    weeks: list[dict[str, Any]] = []
    for timestamp, row in relevant.iloc[::-1].iterrows():
        weekly_range = float(row["High"] - row["Low"])
        weekly_return = (float(row["Close"]) / float(row["previous_close"]) - 1.0) * 100.0
        if weekly_range == 0:
            weeks.append(
                {
                    "period": pd.Timestamp(timestamp).date().isoformat(),
                    "weekly_return_pct": weekly_return,
                    "closing_range_pct": None,
                    "score": None,
                    "status": "neutral",
                    "reason": "High entspricht Low",
                }
            )
            continue
        closing_range = (float(row["Close"]) - float(row["Low"])) / weekly_range * 100.0
        score = 100.0 if closing_range >= 70 else 75.0 if closing_range >= 40 else 40.0 if closing_range >= 25 else 10.0
        if weekly_return <= -4 and closing_range < 25:
            score = 0.0
        weeks.append(
            {
                "period": pd.Timestamp(timestamp).date().isoformat(),
                "weekly_return_pct": weekly_return,
                "closing_range_pct": closing_range,
                "score": score,
                "status": "available",
            }
        )
    scored = [week for week in weeks if week["score"] is not None]
    if not weeks:
        return {"score": None, "status": "neutral", "lookback_weeks": 13, "down_weeks": []}
    if not scored:
        return {"score": None, "status": "neutral", "lookback_weeks": 13, "down_weeks": weeks}
    weights = [50, 30, 20][: len(scored)]
    score = sum(week["score"] * weight for week, weight in zip(scored, weights, strict=True)) / sum(weights)
    return {
        "score": score,
        "status": "available" if len(scored) == 3 else "partial",
        "lookback_weeks": 13,
        "down_weeks": weeks,
    }


def _k38_hh_hl_good_close(weekly: pd.DataFrame) -> dict[str, Any]:
    if len(weekly) < 2:
        return {
            "score": None,
            "status": "insufficient_history",
            "hh_hl_weeks_last_8": 0,
            "strong_hh_hl_weeks_last_8": 0,
            "consecutive_hh_hl_weeks": 0,
        }
    pairs: list[dict[str, Any]] = []
    start = max(1, len(weekly) - 8)
    for index in range(start, len(weekly)):
        current = weekly.iloc[index]
        previous = weekly.iloc[index - 1]
        weekly_range = float(current["High"] - current["Low"])
        closing_range = None if weekly_range == 0 else (float(current["Close"]) - float(current["Low"])) / weekly_range * 100.0
        weekly_return = (float(current["Close"]) / float(previous["Close"]) - 1.0) * 100.0
        hh = bool(current["High"] > previous["High"])
        hl = bool(current["Low"] > previous["Low"])
        pairs.append(
            {
                "period": pd.Timestamp(weekly.index[index]).date().isoformat(),
                "higher_high": hh,
                "higher_low": hl,
                "weekly_return_pct": weekly_return,
                "closing_range_pct": closing_range,
                "strong": bool(hh and hl and weekly_return >= 2 and closing_range is not None and closing_range >= 75),
            }
        )
    hh_hl_count = sum(item["higher_high"] and item["higher_low"] for item in pairs)
    strong_count = sum(item["strong"] for item in pairs)
    consecutive = 0
    for item in reversed(pairs):
        if not (item["higher_high"] and item["higher_low"]):
            break
        consecutive += 1
    current = pairs[-1]
    if not (current["higher_high"] and current["higher_low"]):
        score = None
        status: ScoreStatus = "neutral"
    elif current["closing_range_pct"] is None:
        score = None
        status = "neutral"
    elif current["weekly_return_pct"] >= 4 and current["closing_range_pct"] >= 90:
        score, status = 100.0, "available"
    elif current["weekly_return_pct"] >= 2 and current["closing_range_pct"] >= 75:
        score, status = 90.0, "available"
    elif current["weekly_return_pct"] > 0 and current["closing_range_pct"] >= 60:
        score, status = 75.0, "available"
    else:
        score, status = 50.0, "available"
    return {
        "score": score,
        "status": status,
        **current,
        "hh_hl_weeks_last_8": hh_hl_count,
        "strong_hh_hl_weeks_last_8": strong_count,
        "consecutive_hh_hl_weeks": consecutive,
        "weeks_last_8": pairs,
    }


def _overall_score_v2(
    *,
    technical_v2: Mapping[str, Any],
    fundamental_v2: Mapping[str, Any],
    chart_v2: Mapping[str, Any],
    moving_average_v2: Mapping[str, Any],
    weights: Mapping[str, float] = OVERALL_WEIGHTS,
) -> dict[str, Any]:
    components = {
        "technical": _component(technical_v2.get("score"), technical_v2.get("status", "missing"), raw={"data_coverage": technical_v2.get("data_coverage")}),
        "fundamental": _component(fundamental_v2.get("score"), fundamental_v2.get("status", "missing"), raw={"data_coverage": fundamental_v2.get("data_coverage")}),
        "chart": _component(chart_v2.get("score"), chart_v2.get("status", "missing"), raw={"data_coverage": chart_v2.get("data_coverage")}),
        "moving_average": _component(moving_average_v2.get("score"), moving_average_v2.get("status", "missing"), raw={"data_coverage": moving_average_v2.get("data_coverage")}),
    }
    result = _weighted_score(components, weights)
    result["status"] = "available" if result["available_weight"] == 1.0 else "limited"
    result["weights"] = dict(weights)
    return result


def _eligibility_context(checks: Sequence[AssessmentCheck]) -> dict[str, Any]:
    by_label = {check.label: check for check in checks}
    rules = {}
    for key, label in (("minimum_price", "Preis >= $15"), ("minimum_liquidity", "Dollar-Volumen >= $30 Mio.")):
        check = by_label.get(label)
        rules[key] = {
            "passed": bool(check and check.passed),
            "available": bool(check and check.detail != "Nicht verfügbar"),
            "label": label,
            "detail": check.detail if check else "Nicht verfügbar",
        }
    failed = [rule["label"] for rule in rules.values() if rule["available"] and not rule["passed"]]
    return {"status": "passed" if not failed and all(rule["available"] for rule in rules.values()) else "failed" if failed else "missing", "failed_reasons": failed, "rules": rules}


def _setup_context(df: pd.DataFrame, signals: Sequence[ChartSignal]) -> dict[str, Any]:
    close = pd.to_numeric(df["Close"], errors="coerce")
    price = _safe_float(close.iloc[-1])
    averages = {
        "10-SMA": (_safe_float(close.rolling(10, min_periods=10).mean().iloc[-1]), 10.0),
        "21-EMA": (_safe_float(close.ewm(span=21, adjust=False).mean().iloc[-1]), 14.0),
        "50-SMA": (_safe_float(close.rolling(50, min_periods=50).mean().iloc[-1]), 25.0),
        "200-SMA": (_safe_float(close.rolling(200, min_periods=200).mean().iloc[-1]), 70.0),
    }
    distances = {
        label: {"distance_pct": _distance_pct(price, average), "threshold_pct": threshold}
        for label, (average, threshold) in averages.items()
    }
    active_labels = {signal.label for signal in signals}
    overextended = any(
        item["distance_pct"] is not None and abs(item["distance_pct"]) >= item["threshold_pct"]
        for item in distances.values()
    )
    return {
        "status": "overextended" if overextended else "normal",
        "overextended": overextended,
        "moving_average_distances": distances,
        "natural_reaction": "Natürliche Reaktion" in active_labels,
        "test_21_ema": "Test der 21-EMA" in active_labels,
        "test_50_sma": "Test der 50-SMA" in active_labels,
    }


def _technical_points_score(
    technical_checks: Sequence[AssessmentCheck],
    rs_rating: int | float | None,
    cmf_value: float | None,
) -> float:
    check_map = {check.label: bool(check.passed) for check in technical_checks}
    score = 0.0
    max_score = 102.0
    score += 5 if check_map.get("Preis >= $15", False) else 0
    score += 8 if check_map.get("Entfernung zum All-Time-High", False) else 0
    score += 4 if check_map.get("Entfernung zum 52-Wochen-Hoch", False) else 0
    score += 5 if check_map.get("Dollar-Volumen >= $30 Mio.", False) else 0
    score += 10 if check_map.get("Up/Down Vol. Ratio >=1.0", False) else 0

    rs_value = _safe_float(rs_rating)
    if rs_value is not None and rs_value >= 80:
        score += float(np.clip((rs_value - 80) * 0.7 + 1.0, 1.0, 15.0))

    score += 10 if check_map.get("RS-Linie über 21-EMA", False) else 0
    score += 10 if check_map.get("RS-Linie über 50-SMA", False) else 0
    score += 5 if check_map.get("RS-Linie steigt über 5 Wochen", False) else 0
    score += 10 if check_map.get("RS-Linie steigt über 13 Wochen", False) else 0
    score += 5 if check_map.get("RS-Linie nahe 52W-Hoch", False) else 0

    cmf_rating = _cmf_rating(cmf_value)[0]
    if cmf_rating == "A":
        score += 15
    elif cmf_rating == "B":
        score += 10

    return round(float(np.clip(score / max_score * 100.0, 0, 100)), 1)


def _moving_average_score(df: pd.DataFrame) -> float:
    close = pd.to_numeric(df["Close"], errors="coerce")
    price = _safe_float(close.iloc[-1])
    if price is None:
        return 0.0
    sma10 = _safe_float(close.rolling(10, min_periods=10).mean().iloc[-1])
    ema21 = _safe_float(close.ewm(span=21, adjust=False).mean().iloc[-1])
    sma50 = _safe_float(close.rolling(50, min_periods=50).mean().iloc[-1])
    sma200 = _safe_float(close.rolling(200, min_periods=200).mean().iloc[-1])
    score = 0.0
    score += 30.0 if sma200 is not None and price > sma200 else 0.0
    score += 24.0 if sma50 is not None and price > sma50 else 0.0
    score += 18.0 if ema21 is not None and price > ema21 else 0.0
    score += 8.0 if sma10 is not None and price > sma10 else 0.0
    score += 20.0 if ema21 is not None and sma50 is not None and sma200 is not None and ema21 > sma50 > sma200 else 0.0
    return round(score, 1)


def _chart_behavior_score_100(positive_count: int, negative_count: int) -> int:
    max_positive = 19
    max_negative = 18
    total_max_signals = max_positive + max_negative
    total_active = positive_count + negative_count
    ratio_component = (positive_count / total_active) if total_active > 0 else 0.5
    net_component = ((positive_count - negative_count) + max_negative) / total_max_signals
    score = int(round((ratio_component * 0.65 + net_component * 0.35) * 100))
    return max(0, min(100, score))


def _fundamental_checklist_score_100(
    checks: Sequence[AssessmentCheck],
    fundamentals_context: Mapping[str, Any],
) -> float:
    check_map = {check.label: bool(check.passed) for check in checks}
    unit = 100.0 / 9.0

    score = 0.0
    score += _eps_three_quarter_score(fundamentals_context, unit=unit)
    score += unit if check_map.get("Bonus: EPS-Beschleunigung letzte 3 Quartale", False) else 0.0
    score += _eps_three_year_score(fundamentals_context, unit=unit)
    score += unit if check_map.get("Summe EPS letzte 4 Quartale > 0", False) else 0.0
    score += _revenue_three_quarter_score(fundamentals_context, unit=unit)
    score += unit if check_map.get("Bonus: Umsatz-Beschleunigung letzte 3 Quartale", False) else 0.0
    score += _revenue_three_year_score(fundamentals_context, unit=unit)
    score += _roe_three_year_score(fundamentals_context, unit=unit)

    margin = _safe_float(fundamentals_context.get("profit_margin_pct"))
    if margin is not None and margin > 0:
        score += unit * min(margin / 25.0, 1.0)

    return float(np.clip(score, 0, 100))


def _build_verdict(
    overall: int,
    checks: Sequence[AssessmentCheck],
    metrics: StockAssessmentMetrics,
) -> tuple[str, VerdictTone, str]:
    by_label = {check.label: check for check in checks}
    if not by_label.get("Preis >= $15", AssessmentCheck("risk", "", True, "")).passed:
        return "Mindestpreis nicht erreicht", "bad", "Die Aktie erfüllt die Mindestpreis-Regel nicht."
    if not by_label.get("Dollar-Volumen >= $30 Mio.", AssessmentCheck("risk", "", True, "")).passed:
        return "Volumen nicht erreicht", "bad", "Die Liquidität ist für die Strategie zu dünn."
    if metrics.distance_sma200_pct is not None and metrics.distance_sma200_pct < 0:
        return "Unter 200 Tage", "bad", "Der Kurs liegt unter dem langfristigen Trendfilter."
    if metrics.distance_sma50_pct is not None and metrics.distance_sma50_pct > 25:
        return "Überdehnt", "warning", "Der Abstand zur 50-SMA ist groß; Rücksetzer-Risiko erhöht."
    if overall >= 75:
        return "Attraktiv", "good", "Technik, Trend und Chartverhalten sind überwiegend konstruktiv."
    if overall >= 55:
        return "Beobachten", "warning", "Das Setup ist brauchbar, aber nicht in allen Teilbereichen stark."
    return "Zu schwach", "bad", "Mehrere Kernkriterien sprechen gegen einen Einstieg."


def _build_drivers_and_warnings(
    checks: Sequence[AssessmentCheck],
    chart_signals: Sequence[ChartSignal],
    *,
    fundamentals_available: bool,
    earnings: EarningsWarning | None,
) -> tuple[list[str], list[str]]:
    driver_labels = {
        "RS-Bewertung >=80",
        "RS-Linie steigt über 13 Wochen",
        "RS-Linie nahe 52W-Hoch",
        "Entfernung zum All-Time-High",
        "Entfernung zum 52-Wochen-Hoch",
        "Kurs über 200-SMA",
        "Kurs über 50-SMA",
        "MA-Ordnung (21>50>200)",
        "CMF Rating A oder B",
        "Up/Down Vol. Ratio >=1.0",
        "EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY",
        "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY",
        "Summe EPS letzte 4 Quartale > 0",
        "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY",
        "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY",
        "ROE >=17% über letzte 3 Jahre",
        "Gewinnmarge positiv",
        "Institutionelle Unterstützung",
    }
    drivers = [f"{check.label}: {check.detail}" for check in checks if check.passed and check.label in driver_labels]
    drivers.extend(f"{signal.label}: {signal.detail}".rstrip(": ") for signal in chart_signals if signal.category == "positive")

    warnings = [
        f"{check.label}: {check.detail}"
        for check in checks
        if not check.passed and (check.severity in {"warning", "critical"} or check.label.startswith("RS-"))
    ]
    warnings.extend(f"{signal.label}: {signal.detail}".rstrip(": ") for signal in chart_signals if signal.category == "negative")
    if not fundamentals_available:
        warnings.append("Fundamentaldaten sind noch nicht im Cache; Fundamental-Score neutral mit 50/100.")
    if earnings and earnings.tone in {"warning", "bad"}:
        warnings.append(earnings.message)
    return drivers[:8], warnings[:8]


def _growth_check(
    label: str,
    value: float | None,
    *,
    minimum: float,
    detail_suffix: str,
) -> AssessmentCheck:
    return AssessmentCheck(
        category="fundamental",
        label=label,
        passed=value is not None and value >= minimum,
        detail=f"{value:+.1f}% · {detail_suffix}" if value is not None else "Nicht verfügbar",
    )


def _eps_three_quarter_growth_check(history: list[dict[str, Any]]) -> AssessmentCheck:
    latest_three = history[:3]
    values = [_safe_float(item.get("eps_growth_yoy_pct")) for item in latest_three]
    valid_values = [value for value in values if value is not None]
    below = [
        _eps_period_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is not None and value < 20.0
    ]
    invalid = [
        _eps_period_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is None
    ]
    passed = len(latest_three) >= 3 and len(valid_values) >= 3 and not below
    detail = _eps_history_detail(latest_three, values, below=below, invalid=invalid)
    severity: Literal["info", "warning", "critical"] = "warning" if below or (latest_three and invalid) else "info"
    return AssessmentCheck(
        category="fundamental",
        label="EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY",
        passed=passed,
        detail=detail,
        severity=severity,
    )


def _eps_three_quarter_score(fundamentals_context: Mapping[str, Any], *, unit: float) -> float:
    history = _normalize_eps_quarter_history(fundamentals_context.get("eps_quarter_history"))
    latest_three = history[:3]
    if len(latest_three) < 3:
        return 0.0
    values = [_safe_float(item.get("eps_growth_yoy_pct")) for item in latest_three]
    if any(value is None for value in values):
        return 0.0
    passed_count = sum(1 for value in values if value is not None and value >= 20.0)
    return unit * (passed_count / 3.0)


def _eps_three_year_growth_check(history: list[dict[str, Any]]) -> AssessmentCheck:
    latest_three = history[:3]
    values = [_safe_float(item.get("eps_growth_yoy_pct")) for item in latest_three]
    valid_values = [value for value in values if value is not None]
    below = [
        _eps_year_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is not None and value < 20.0
    ]
    invalid = [
        _eps_year_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is None
    ]
    passed = len(latest_three) >= 3 and len(valid_values) >= 3 and not below
    detail = _eps_annual_history_detail(latest_three, values, below=below, invalid=invalid)
    severity: Literal["info", "warning", "critical"] = "warning" if below or (latest_three and invalid) else "info"
    return AssessmentCheck(
        category="fundamental",
        label="EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY",
        passed=passed,
        detail=detail,
        severity=severity,
    )


def _eps_three_year_score(fundamentals_context: Mapping[str, Any], *, unit: float) -> float:
    history = _normalize_annual_eps_history(fundamentals_context.get("annual_eps_history"))
    latest_three = history[:3]
    if len(latest_three) < 3:
        return 0.0
    values = [_safe_float(item.get("eps_growth_yoy_pct")) for item in latest_three]
    if any(value is None for value in values):
        return 0.0
    passed_count = sum(1 for value in values if value is not None and value >= 20.0)
    return unit * (passed_count / 3.0)


def _revenue_three_quarter_growth_check(history: list[dict[str, Any]]) -> AssessmentCheck:
    latest_three = history[:3]
    values = [_safe_float(item.get("revenue_growth_yoy_pct")) for item in latest_three]
    valid_values = [value for value in values if value is not None]
    below = [
        _revenue_period_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is not None and value < 20.0
    ]
    invalid = [
        _revenue_period_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is None
    ]
    passed = len(latest_three) >= 3 and len(valid_values) >= 3 and not below
    detail = _revenue_history_detail(latest_three, values, below=below, invalid=invalid)
    severity: Literal["info", "warning", "critical"] = "warning" if below or (latest_three and invalid) else "info"
    return AssessmentCheck(
        category="fundamental",
        label="Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY",
        passed=passed,
        detail=detail,
        severity=severity,
    )


def _revenue_three_quarter_score(fundamentals_context: Mapping[str, Any], *, unit: float) -> float:
    history = _normalize_revenue_quarter_history(fundamentals_context.get("revenue_quarter_history"))
    latest_three = history[:3]
    if len(latest_three) < 3:
        return 0.0
    values = [_safe_float(item.get("revenue_growth_yoy_pct")) for item in latest_three]
    if any(value is None for value in values):
        return 0.0
    passed_count = sum(1 for value in values if value is not None and value >= 20.0)
    return unit * (passed_count / 3.0)


def _revenue_three_year_growth_check(history: list[dict[str, Any]]) -> AssessmentCheck:
    latest_three = history[:3]
    values = [_safe_float(item.get("revenue_growth_yoy_pct")) for item in latest_three]
    valid_values = [value for value in values if value is not None]
    below = [
        _revenue_year_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is not None and value < 20.0
    ]
    invalid = [
        _revenue_year_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is None
    ]
    passed = len(latest_three) >= 3 and len(valid_values) >= 3 and not below
    detail = _revenue_annual_history_detail(latest_three, values, below=below, invalid=invalid)
    severity: Literal["info", "warning", "critical"] = "warning" if below or (latest_three and invalid) else "info"
    return AssessmentCheck(
        category="fundamental",
        label="Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY",
        passed=passed,
        detail=detail,
        severity=severity,
    )


def _revenue_three_year_score(fundamentals_context: Mapping[str, Any], *, unit: float) -> float:
    history = _normalize_annual_revenue_history(fundamentals_context.get("annual_revenue_history"))
    latest_three = history[:3]
    if len(latest_three) < 3:
        return 0.0
    values = [_safe_float(item.get("revenue_growth_yoy_pct")) for item in latest_three]
    if any(value is None for value in values):
        return 0.0
    passed_count = sum(1 for value in values if value is not None and value >= 20.0)
    return unit * (passed_count / 3.0)


def _roe_three_year_check(history: list[dict[str, Any]], *, current_roe: float | None) -> AssessmentCheck:
    latest_three = history[:3]
    values = [_safe_float(item.get("roe_pct")) for item in latest_three]
    valid_values = [value for value in values if value is not None]
    below = [
        _roe_year_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is not None and value < 17.0
    ]
    invalid = [
        _roe_year_label(item, index)
        for index, (item, value) in enumerate(zip(latest_three, values, strict=False), start=1)
        if value is None
    ]
    passed = len(latest_three) >= 3 and len(valid_values) >= 3 and not below
    detail = _roe_history_detail(latest_three, values, below=below, invalid=invalid, current_roe=current_roe)
    severity: Literal["info", "warning", "critical"] = "warning" if below or (latest_three and invalid) else "info"
    return AssessmentCheck(
        category="fundamental",
        label="ROE >=17% über letzte 3 Jahre",
        passed=passed,
        detail=detail,
        severity=severity,
    )


def _roe_three_year_score(fundamentals_context: Mapping[str, Any], *, unit: float) -> float:
    history = _normalize_roe_history(fundamentals_context.get("roe_history"))
    latest_three = history[:3]
    if latest_three:
        values = [_safe_float(item.get("roe_pct")) for item in latest_three]
        passed_count = sum(1 for value in values if value is not None and value >= 17.0)
        base_score = unit * (passed_count / 3.0)
        additional_years = history[3:]
        bonus_count = sum(
            1
            for item in additional_years
            if (_safe_float(item.get("roe_pct")) or float("-inf")) >= 17.0
        )
        return base_score + unit * 0.25 * bonus_count
    current_roe = _safe_float(fundamentals_context.get("roe_pct"))
    return unit / 3.0 if current_roe is not None and current_roe >= 17.0 else 0.0


def _normalize_eps_quarter_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        fiscal_period = str(item.get("fiscal_period") or item.get("label") or item.get("period") or "").strip()
        current = _safe_float(item.get("eps_current_quarter", item.get("current")))
        previous = _safe_float(item.get("eps_same_quarter_last_year", item.get("previous")))
        growth = _computed_eps_growth_pct(current, previous)
        if growth is None and current is None and previous is None:
            growth = _safe_float(item.get("eps_growth_yoy_pct", item.get("growth_pct")))
        history.append(
            {
                "fiscal_period": fiscal_period,
                "eps_current_quarter": current,
                "eps_same_quarter_last_year": previous,
                "eps_growth_yoy_pct": growth,
                "flag": item.get("flag"),
            }
        )
    return history[:3]


def _normalize_revenue_quarter_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        fiscal_period = str(item.get("fiscal_period") or item.get("label") or item.get("period") or "").strip()
        current = _safe_float(item.get("revenue_current_quarter", item.get("current")))
        previous = _safe_float(item.get("revenue_same_quarter_last_year", item.get("previous")))
        growth = _computed_eps_growth_pct(current, previous)
        if growth is None and current is None and previous is None:
            growth = _safe_float(item.get("revenue_growth_yoy_pct", item.get("growth_pct")))
        history.append(
            {
                "fiscal_period": fiscal_period,
                "revenue_current_quarter": current,
                "revenue_same_quarter_last_year": previous,
                "revenue_growth_yoy_pct": growth,
                "flag": item.get("flag"),
            }
        )
    return history[:3]


def _normalize_annual_eps_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        fiscal_year = str(item.get("fiscal_year") or item.get("label") or item.get("year") or "").strip()
        current = _safe_float(item.get("eps_current_year", item.get("current")))
        previous = _safe_float(item.get("eps_previous_year", item.get("previous")))
        growth = _computed_eps_growth_pct(current, previous)
        if growth is None and current is None and previous is None:
            growth = _safe_float(item.get("eps_growth_yoy_pct", item.get("growth_pct")))
        history.append(
            {
                "fiscal_year": fiscal_year,
                "eps_current_year": current,
                "eps_previous_year": previous,
                "eps_growth_yoy_pct": growth,
                "flag": item.get("flag"),
            }
        )
    return history[:3]


def _normalize_annual_revenue_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        fiscal_year = str(item.get("fiscal_year") or item.get("label") or item.get("year") or "").strip()
        current = _safe_float(item.get("revenue_current_year", item.get("current")))
        previous = _safe_float(item.get("revenue_previous_year", item.get("previous")))
        growth = _computed_eps_growth_pct(current, previous)
        if growth is None and current is None and previous is None:
            growth = _safe_float(item.get("revenue_growth_yoy_pct", item.get("growth_pct")))
        history.append(
            {
                "fiscal_year": fiscal_year,
                "revenue_current_year": current,
                "revenue_previous_year": previous,
                "revenue_growth_yoy_pct": growth,
                "flag": item.get("flag"),
            }
        )
    return history[:3]


def _normalize_roe_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        fiscal_year = str(item.get("fiscal_year") or item.get("label") or item.get("year") or "").strip()
        history.append(
            {
                "fiscal_year": fiscal_year,
                "roe_pct": _safe_float(item.get("roe_pct", item.get("growth_pct"))),
                "net_income": _safe_float(item.get("net_income", item.get("current"))),
                "shareholders_equity": _safe_float(item.get("shareholders_equity", item.get("previous"))),
                "flag": item.get("flag"),
            }
        )
    return history[:5]


def _computed_eps_growth_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return round((current / previous - 1) * 100, 1)


def _eps_growth_accelerating(history: list[dict[str, Any]]) -> bool | None:
    values = [_safe_float(item.get("eps_growth_yoy_pct")) for item in history[:3]]
    if len(values) < 3 or any(value is None for value in values):
        return None
    numeric = [float(value) for value in values if value is not None]
    return all(numeric[index] > numeric[index + 1] for index in range(len(numeric) - 1))


def _eps_acceleration_detail(value: bool | None, history: list[dict[str, Any]]) -> str:
    if history:
        values = [
            f"{_eps_period_label(item, index)} {_format_signed_pct(_safe_float(item.get('eps_growth_yoy_pct')))}"
            for index, item in enumerate(history[:3], start=1)
        ]
        suffix = "Bonus erfüllt: beschleunigt" if value else "Bonus nicht erfüllt" if value is False else "nicht auswertbar"
        return f"{', '.join(values)} · {suffix}"
    return _bool_detail(value)


def _revenue_growth_accelerating(history: list[dict[str, Any]]) -> bool | None:
    values = [_safe_float(item.get("revenue_growth_yoy_pct")) for item in history[:3]]
    if len(values) < 3 or any(value is None for value in values):
        return None
    numeric = [float(value) for value in values if value is not None]
    return all(numeric[index] > numeric[index + 1] for index in range(len(numeric) - 1))


def _revenue_acceleration_detail(value: bool | None, history: list[dict[str, Any]]) -> str:
    if history:
        values = [
            f"{_revenue_period_label(item, index)} {_format_signed_pct(_safe_float(item.get('revenue_growth_yoy_pct')))}"
            for index, item in enumerate(history[:3], start=1)
        ]
        suffix = "Bonus erfüllt: beschleunigt" if value else "Bonus nicht erfüllt" if value is False else "nicht auswertbar"
        return f"{', '.join(values)} · {suffix}"
    return _bool_detail(value)


def _eps_history_detail(
    latest_three: list[dict[str, Any]],
    values: list[float | None],
    *,
    below: list[str],
    invalid: list[str],
) -> str:
    if len(latest_three) < 3:
        prefix = _format_eps_history_values(latest_three, values)
        if prefix:
            return f"{prefix} · nur {len(latest_three)}/3 Quartale verfügbar"
        return "Nicht verfügbar: keine EPS-Quartalshistorie gespeichert"
    prefix = _format_eps_history_values(latest_three, values)
    if invalid:
        return f"{prefix} · {', '.join(invalid)} nicht auswertbar"
    if below:
        return f"{prefix} · {', '.join(below)} unter 20%"
    return f"{prefix} · alle >=20%"


def _revenue_history_detail(
    latest_three: list[dict[str, Any]],
    values: list[float | None],
    *,
    below: list[str],
    invalid: list[str],
) -> str:
    if len(latest_three) < 3:
        prefix = _format_revenue_history_values(latest_three, values)
        if prefix:
            return f"{prefix} · nur {len(latest_three)}/3 Quartale verfügbar"
        return "Nicht verfügbar: keine Umsatz-Quartalshistorie gespeichert"
    prefix = _format_revenue_history_values(latest_three, values)
    if invalid:
        return f"{prefix} · {', '.join(invalid)} nicht auswertbar"
    if below:
        return f"{prefix} · {', '.join(below)} unter 20%"
    return f"{prefix} · alle >=20%"


def _eps_annual_history_detail(
    latest_three: list[dict[str, Any]],
    values: list[float | None],
    *,
    below: list[str],
    invalid: list[str],
) -> str:
    if len(latest_three) < 3:
        prefix = _format_annual_eps_history_values(latest_three, values)
        if prefix:
            return f"{prefix} · nur {len(latest_three)}/3 Jahre verfügbar"
        return "Nicht verfügbar: keine jährliche EPS-Historie gespeichert"
    prefix = _format_annual_eps_history_values(latest_three, values)
    if invalid:
        return f"{prefix} · {', '.join(invalid)} nicht auswertbar"
    if below:
        return f"{prefix} · {', '.join(below)} unter 20%"
    return f"{prefix} · alle >=20%"


def _revenue_annual_history_detail(
    latest_three: list[dict[str, Any]],
    values: list[float | None],
    *,
    below: list[str],
    invalid: list[str],
) -> str:
    if len(latest_three) < 3:
        prefix = _format_annual_revenue_history_values(latest_three, values)
        if prefix:
            return f"{prefix} · nur {len(latest_three)}/3 Jahre verfügbar"
        return "Nicht verfügbar: keine jährliche Umsatz-Historie gespeichert"
    prefix = _format_annual_revenue_history_values(latest_three, values)
    if invalid:
        return f"{prefix} · {', '.join(invalid)} nicht auswertbar"
    if below:
        return f"{prefix} · {', '.join(below)} unter 20%"
    return f"{prefix} · alle >=20%"


def _roe_history_detail(
    latest_three: list[dict[str, Any]],
    values: list[float | None],
    *,
    below: list[str],
    invalid: list[str],
    current_roe: float | None,
) -> str:
    if len(latest_three) < 3:
        prefix = _format_roe_history_values(latest_three, values)
        fallback = f" · aktueller ROE {current_roe:.1f}%" if current_roe is not None else ""
        if prefix:
            return f"{prefix} · nur {len(latest_three)}/3 Jahre verfügbar{fallback}"
        if current_roe is not None:
            return f"Keine ROE-Jahreshistorie gespeichert · aktueller ROE {current_roe:.1f}%"
        return "Nicht verfügbar: keine ROE-Jahreshistorie gespeichert"
    prefix = _format_roe_history_values(latest_three, values)
    if invalid:
        return f"{prefix} · {', '.join(invalid)} nicht auswertbar"
    if below:
        return f"{prefix} · {', '.join(below)} unter 17%"
    return f"{prefix} · alle >=17%"


def _format_eps_history_values(items: list[dict[str, Any]], values: list[float | None]) -> str:
    return ", ".join(
        f"{_eps_period_label(item, index)} {_format_signed_pct(value)}"
        for index, (item, value) in enumerate(zip(items, values, strict=False), start=1)
    )


def _format_revenue_history_values(items: list[dict[str, Any]], values: list[float | None]) -> str:
    return ", ".join(
        f"{_revenue_period_label(item, index)} {_format_signed_pct(value)}"
        for index, (item, value) in enumerate(zip(items, values, strict=False), start=1)
    )


def _format_annual_eps_history_values(items: list[dict[str, Any]], values: list[float | None]) -> str:
    return ", ".join(
        f"{_eps_year_label(item, index)} {_format_signed_pct(value)}"
        for index, (item, value) in enumerate(zip(items, values, strict=False), start=1)
    )


def _format_annual_revenue_history_values(items: list[dict[str, Any]], values: list[float | None]) -> str:
    return ", ".join(
        f"{_revenue_year_label(item, index)} {_format_signed_pct(value)}"
        for index, (item, value) in enumerate(zip(items, values, strict=False), start=1)
    )


def _format_roe_history_values(items: list[dict[str, Any]], values: list[float | None]) -> str:
    return ", ".join(
        f"{_roe_year_label(item, index)} {_format_pct(value)}"
        for index, (item, value) in enumerate(zip(items, values, strict=False), start=1)
    )


def _eps_period_label(item: Mapping[str, Any], index: int) -> str:
    return str(item.get("fiscal_period") or f"Q{index}").strip()


def _revenue_period_label(item: Mapping[str, Any], index: int) -> str:
    return str(item.get("fiscal_period") or f"Q{index}").strip()


def _eps_year_label(item: Mapping[str, Any], index: int) -> str:
    return str(item.get("fiscal_year") or f"Jahr {index}").strip()


def _revenue_year_label(item: Mapping[str, Any], index: int) -> str:
    return str(item.get("fiscal_year") or f"Jahr {index}").strip()


def _roe_year_label(item: Mapping[str, Any], index: int) -> str:
    return str(item.get("fiscal_year") or f"Jahr {index}").strip()


def _format_signed_pct(value: float | None) -> str:
    return f"{value:+.1f}%" if value is not None else "n/a"


def _format_pct(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "n/a"


def _merge_institutional_fields(fundamentals: dict[str, Any], institutional: Mapping[str, Any]) -> dict[str, Any]:
    if not institutional:
        return fundamentals
    merged = dict(fundamentals)
    merged["institutional_report_period"] = institutional.get("report_period") or institutional.get("period")
    merged["institutional_13f_holders"] = _int_or_none(institutional.get("holder_count"))
    merged["institutional_holders_delta"] = _int_or_none(institutional.get("holder_count_delta"))
    merged["institutional_large_holders"] = _int_or_none(institutional.get("large_holder_count"))
    merged["institutional_large_holders_delta"] = _int_or_none(institutional.get("large_holder_delta"))
    return merged


def _institutional_support_check(
    fundamentals_context: Mapping[str, Any],
    institutional_context: Mapping[str, Any],
) -> AssessmentCheck:
    trend = str(institutional_context.get("trend") or "").strip().lower()
    large_holders = _int_or_none(institutional_context.get("large_holder_count"))
    holder_count = _int_or_none(institutional_context.get("holder_count"))
    large_delta = _int_or_none(institutional_context.get("large_holder_delta"))
    holder_delta = _int_or_none(institutional_context.get("holder_count_delta"))
    period = str(institutional_context.get("report_period") or institutional_context.get("period") or "").strip()

    if institutional_context:
        negative = (large_delta is not None and large_delta < 0) or (large_holders is not None and large_holders < 5)
        passed = not negative and trend not in {"negative", "missing"}
        details = []
        if large_holders is not None:
            details.append(f"Große Institutionen: {large_holders}")
        if large_delta is not None:
            details.append(f"Delta groß: {large_delta:+d}")
        if holder_count is not None:
            details.append(f"Alle 13F-Halter: {holder_count}")
        if holder_delta is not None:
            details.append(f"Delta Halter: {holder_delta:+d}")
        if trend:
            details.append(f"Trend {trend}")
        if period:
            details.append(period)
        return AssessmentCheck(
            category="fundamental",
            label="Institutionelle Unterstützung",
            passed=passed,
            detail=" · ".join(details) if details else "13F-Kontext gespeichert",
        )

    return AssessmentCheck(
        category="fundamental",
        label="Institutionelle Unterstützung",
        passed=False,
        detail="Keine gespeicherten 13F-Trends",
    )


def _build_earnings_warning(value: Any) -> EarningsWarning | None:
    earnings_date = _parse_date(value)
    if earnings_date is None:
        return None

    today = date.today()
    calendar_days = (earnings_date - today).days
    trading_days = _business_days_between(today, earnings_date)
    if calendar_days < 0:
        return EarningsWarning(
            next_earnings_date=earnings_date.isoformat(),
            calendar_days=calendar_days,
            trading_days=trading_days,
            tone="neutral",
            message=f"Letzte gespeicherte Quartalszahlen lagen am {earnings_date.isoformat()}.",
        )
    if trading_days <= 5:
        tone: VerdictTone = "bad"
        message = (
            f"Nächste Quartalszahlen am {earnings_date.isoformat()} "
            f"({trading_days} Handelstage): kein Einstieg kurz vor Earnings ohne Gewinnpolster."
        )
    elif trading_days <= 14:
        tone = "warning"
        message = (
            f"Nächste Quartalszahlen am {earnings_date.isoformat()} "
            f"({trading_days} Handelstage): erhöhtes Einstiegsrisiko."
        )
    else:
        tone = "good"
        message = f"Nächste Quartalszahlen am {earnings_date.isoformat()} ({trading_days} Handelstage)."
    return EarningsWarning(
        next_earnings_date=earnings_date.isoformat(),
        calendar_days=calendar_days,
        trading_days=trading_days,
        tone=tone,
        message=message,
    )


def _earnings_check(earnings: EarningsWarning | None) -> AssessmentCheck | None:
    if earnings is None:
        return None
    passed = earnings.trading_days is None or earnings.trading_days > 14
    severity: Literal["info", "warning", "critical"] = "critical" if earnings.tone == "bad" else "warning"
    if earnings.tone == "good":
        severity = "info"
    return AssessmentCheck(
        category="risk",
        label="Earnings-Abstand >14 Handelstage",
        passed=passed,
        detail=earnings.message,
        severity=severity,
    )


def _business_days_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    return max(0, len(pd.bdate_range(pd.Timestamp(start), pd.Timestamp(end))) - 1)


def _has_fundamental_data(fundamentals_context: Mapping[str, Any]) -> bool:
    keys = {
        "quarterly_eps_growth_pct",
        "eps_quarter_history",
        "annual_eps_history",
        "annual_eps_growth_pct",
        "quarterly_revenue_growth_pct",
        "revenue_quarter_history",
        "annual_revenue_history",
        "annual_revenue_growth_pct",
        "roe_pct",
        "roe_history",
        "profit_margin_pct",
        "trailing_eps",
        "next_earnings_date",
        "beta",
    }
    return any(_fundamental_value_present(fundamentals_context.get(key)) for key in keys)


def _fundamental_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return bool(value)
    return True


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    clean = str(value).strip().lower()
    if clean in {"true", "1", "yes", "ja"}:
        return True
    if clean in {"false", "0", "no", "nein"}:
        return False
    return None


def _bool_detail(value: bool | None) -> str:
    if value is True:
        return "ja"
    if value is False:
        return "nein"
    return "Nicht verfügbar"


def _coerce_bars_to_frame(bars: Sequence[Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        bar_date = _point_value(bar, "date")
        close = _safe_float(_point_value(bar, "close"))
        if bar_date is None or close is None:
            continue
        # Repository bars already contain typed dates; avoid a parser invocation
        # for every historical candle when screening thousands of instruments.
        timestamp = bar_date if isinstance(bar_date, date) else pd.to_datetime(bar_date, errors="coerce")
        if pd.isna(timestamp):
            continue
        rows.append(
            {
                "Date": timestamp,
                "Open": _safe_float(_point_value(bar, "open")) or close,
                "High": _safe_float(_point_value(bar, "high")) or close,
                "Low": _safe_float(_point_value(bar, "low")) or close,
                "Close": close,
                "Volume": _safe_float(_point_value(bar, "volume")) or 0.0,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows)
    df["Date"] = pd.DatetimeIndex(df["Date"]).normalize()
    df = df.drop_duplicates("Date", keep="last").sort_values("Date")
    df = df.set_index(pd.DatetimeIndex(df.pop("Date")))
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _calc_cmf(df: pd.DataFrame, period: int = 20) -> pd.Series:
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")
    volume = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
    spread = (high - low).replace(0, np.nan)
    money_flow_multiplier = (((close - low) - (high - close)) / spread).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    money_flow_volume = money_flow_multiplier * volume
    volume_sum = volume.rolling(period, min_periods=max(5, period // 2)).sum()
    return (money_flow_volume.rolling(period, min_periods=max(5, period // 2)).sum() / volume_sum).replace([np.inf, -np.inf], np.nan)


def _cmf_rating(value: float | None) -> tuple[str, str]:
    v = _safe_float(value)
    if v is None:
        return "n/a", "Nicht verfügbar"
    if v >= 0.20:
        return "A", "starke Akkumulation"
    if v >= 0.05:
        return "B", "moderate Akkumulation"
    if v > -0.05:
        return "C", "neutral"
    if v > -0.20:
        return "D", "Distribution"
    return "E", "starke Distribution"


def _atr(df: pd.DataFrame, period: int = 21) -> pd.Series:
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")
    previous_close = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period, min_periods=max(5, period // 2)).mean()


def _close_range_position(close: pd.Series, high: pd.Series, low: pd.Series) -> pd.Series:
    daily_range = (high - low).replace(0, np.nan)
    return ((close - low) / daily_range).replace([np.inf, -np.inf], np.nan).fillna(0.5)


def _rs_chart_signals(rs_context: Mapping[str, Any]) -> list[ChartSignal]:
    signals: list[ChartSignal] = []
    rating = _safe_float(rs_context.get("rating"))
    if bool(rs_context.get("trend_5w")):
        signals.append(ChartSignal("positive", "RS-Linie steigt", "über 5 Wochen"))
    elif rs_context.get("trend_5w") is False:
        signals.append(ChartSignal("negative", "RS-Linie fällt", "über 5 Wochen"))
    if bool(rs_context.get("above_21")):
        signals.append(ChartSignal("positive", "RS-Linie über 21-EMA"))
    if bool(rs_context.get("above_50")):
        signals.append(ChartSignal("positive", "RS-Linie über 50-SMA"))
    if bool(rs_context.get("above_21")) and bool(rs_context.get("above_50")):
        signals.append(ChartSignal("positive", "RS-Linie über ihren Durchschnitten"))
    if rs_context.get("above_21") is False:
        signals.append(ChartSignal("negative", "RS-Linie unter 21-EMA"))
    if rs_context.get("above_50") is False:
        signals.append(ChartSignal("negative", "RS-Linie unter 50-SMA"))
    if bool(rs_context.get("new_high_52w")):
        signals.append(ChartSignal("positive", "RS-Linie auf neuem 52W-Hoch", "Marktführerschaft bestätigt"))
    elif bool(rs_context.get("near_high_52w")):
        signals.append(ChartSignal("neutral", "RS-Linie knapp unter Hoch", _pct_detail(rs_context.get("distance_to_high_pct"), "Distanz")))
    elif _safe_float(rs_context.get("distance_to_high_pct")) is not None and float(rs_context["distance_to_high_pct"]) <= -10:
        signals.append(ChartSignal("negative", "RS-Linie deutlich unter Hoch", _pct_detail(rs_context.get("distance_to_high_pct"), "Distanz")))
    if rating is not None and rating >= 90:
        signals.append(ChartSignal("positive", "RS-Rating im Elite-Bereich", f"RS {int(rating)}"))
    elif rating is not None and rating < 70:
        signals.append(ChartSignal("negative", "Schwaches RS-Rating", f"RS {int(rating)}"))
    return signals


def _recent_reaction_signals(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    pct: pd.Series,
    sma50_last: float | None,
    volume: pd.Series,
    volume_avg_50_last: float | None,
) -> list[ChartSignal]:
    signals: list[ChartSignal] = []
    if len(pct) >= 3:
        r1, r2, r3 = pct.iloc[-3] * 100, pct.iloc[-2] * 100, pct.iloc[-1] * 100
        if r1 < 0 and r2 < 0 and r3 < 0 and r3 < r2 < r1 and r3 <= -2.0:
            signals.append(ChartSignal("negative", "Beschleunigte Verluste", f"{r1:+.1f}% -> {r2:+.1f}% -> {r3:+.1f}%"))
    if len(close) >= 20 and sma50_last is not None:
        high_20 = high.tail(20).max()
        drawdown = _safe_float((close.iloc[-1] / high_20 - 1) * 100)
        volume_ok = volume_avg_50_last is not None and volume.iloc[-1] < volume_avg_50_last
        if drawdown is not None and -12.0 <= drawdown <= -8.0 and close.iloc[-1] > sma50_last and volume_ok:
            signals.append(ChartSignal("neutral", "Natürliche Reaktion", f"{drawdown:+.1f}% vom 20T-Hoch, Volumen unter Ø"))
    if len(close) >= 4:
        day_before_sequence_red = close.iloc[-4] < open_.iloc[-4]
        red_2 = close.iloc[-3] < open_.iloc[-3] and close.iloc[-2] < open_.iloc[-2]
        daily_range = high.iloc[-1] - low.iloc[-1]
        close_range = (close.iloc[-1] - low.iloc[-1]) / daily_range if daily_range > 0 else 0.5
        if red_2 and not day_before_sequence_red and close_range >= 0.5:
            signals.append(ChartSignal("neutral", "2,5-Tage-Korrektur", "genau 2 rote Tage, Tag 3 Schluss obere Hälfte"))
    if len(close) >= 21:
        prior_low = low.iloc[-21:-1].min()
        volume_like = True
        daily_range = high.iloc[-1] - low.iloc[-1]
        close_range = (close.iloc[-1] - low.iloc[-1]) / daily_range if daily_range > 0 else 0.5
        if low.iloc[-1] < prior_low and close.iloc[-1] > prior_low and close_range >= 0.5 and volume_like:
            signals.append(ChartSignal("positive", "Shake-out", "Tief unter Vor-20T-Tief, Schluss wieder darüber"))
    return signals


def _trailing_true_count(mask: pd.Series) -> int:
    count = 0
    for value in reversed(mask.fillna(False).astype(bool).tolist()):
        if not value:
            break
        count += 1
    return count


def _confirmed_downside_reversal_mask(
    open_: pd.Series,
    high: pd.Series,
    close: pd.Series,
    close_range: pd.Series,
) -> pd.Series:
    reversal_day = (
        (high > high.shift(1))
        & (close < open_)
        & (close < close.shift(1))
        & (close_range <= 1 / 3)
    )
    confirmation_day = (high > high.shift(1)) & (close_range >= 0.8)
    return (reversal_day.shift(1).fillna(False) & confirmation_day).fillna(False)


def _bullish_outside_day_mask(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    daily_range = (high - low).replace(0, np.nan)
    body_high = pd.concat([open_, close], axis=1).max(axis=1)
    body_low = pd.concat([open_, close], axis=1).min(axis=1)
    upper_wick_ratio = (high - body_high) / daily_range
    lower_wick_ratio = (body_low - low) / daily_range
    long_lower_short_upper = (lower_wick_ratio >= 0.35) & (upper_wick_ratio <= 0.2)
    compact_wicks = (lower_wick_ratio <= 0.15) & (upper_wick_ratio <= 0.15)
    return (
        (high > high.shift(1))
        & (low < low.shift(1))
        & (close > open_)
        & (long_lower_short_upper | compact_wicks)
    ).fillna(False)


def _bullish_engulfing_mask(open_: pd.Series, close: pd.Series, close_range: pd.Series) -> pd.Series:
    current_body_high = pd.concat([open_, close], axis=1).max(axis=1)
    current_body_low = pd.concat([open_, close], axis=1).min(axis=1)
    previous_body_high = pd.concat([open_.shift(1), close.shift(1)], axis=1).max(axis=1)
    previous_body_low = pd.concat([open_.shift(1), close.shift(1)], axis=1).min(axis=1)
    return (
        (close.shift(1) < open_.shift(1))
        & (close > open_)
        & (current_body_high >= previous_body_high)
        & (current_body_low <= previous_body_low)
        & (close_range >= 2 / 3)
    ).fillna(False)


def _support_week_signal(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    sma50: pd.Series,
    *,
    weekly_bars: pd.DataFrame | None = None,
) -> ChartSignal | None:
    weekly = weekly_bars
    if weekly is None:
        weekly = pd.DataFrame(
            {
                "Open": open_,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            }
        ).resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
    if len(weekly) < 50:
        return None

    weekly_sma50_series = weekly["Close"].rolling(50, min_periods=50).mean()
    volume_avg_10w_series = weekly["Volume"].rolling(10, min_periods=4).mean()
    daily_sma50_weekly = sma50.resample("W-FRI").last()
    for idx in reversed(range(max(0, len(weekly) - 3), len(weekly))):
        last = weekly.iloc[idx]
        prev = weekly.iloc[idx - 1] if idx > 0 else None
        weekly_range = float(last["High"] - last["Low"])
        if weekly_range <= 0:
            continue
        close_range = float((last["Close"] - last["Low"]) / weekly_range)
        volume_avg_10w = _safe_float(volume_avg_10w_series.iloc[idx])
        weekly_sma50 = _safe_float(weekly_sma50_series.iloc[idx])
        daily_sma50 = _safe_float(daily_sma50_weekly.reindex(weekly.index).iloc[idx])
        if weekly_sma50 is None or daily_sma50 is None:
            continue

        volume_ok = False
        if prev is not None and float(last["Volume"]) > float(prev["Volume"]):
            volume_ok = True
        if volume_avg_10w is not None and float(last["Volume"]) > volume_avg_10w:
            volume_ok = True

        low_touched_50w = weekly_sma50 * 0.97 <= float(last["Low"]) <= weekly_sma50 * 1.005
        close_reclaimed_50w = float(last["Close"]) > weekly_sma50
        week_down = float(last["Close"]) < float(last["Open"])
        if (
            week_down
            and close_range >= 0.5
            and volume_ok
            and low_touched_50w
            and close_reclaimed_50w
            and float(last["Close"]) > daily_sma50
        ):
            return ChartSignal(
                "positive",
                "Unterstützungswoche",
                f"50W berührt/zurückerobert, Wochen-Schluss obere Hälfte ({close_range:.0%}), Volumen bestätigt",
            )
    rolling_signal = _rolling_support_week_signal(open_, high, low, close, volume, sma50, weekly, weekly_sma50_series, volume_avg_10w_series)
    if rolling_signal is not None:
        return rolling_signal
    return None


def _rolling_support_week_signal(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    sma50: pd.Series,
    weekly: pd.DataFrame,
    weekly_sma50_series: pd.Series,
    volume_avg_10w_series: pd.Series,
) -> ChartSignal | None:
    """Detect support weeks in rolling five-trading-day windows.

    Calendar resampling can split a valid five-session support pattern across two
    weeks. The rule is still a weekly candle concept, so we check the last recent
    five-session windows with the same touch/reclaim requirements.
    """
    if len(close.dropna()) < 50 or len(weekly) < 50:
        return None
    aligned = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}).dropna()
    if len(aligned) < 5:
        return None
    recent_starts = range(max(0, len(aligned) - 12), max(0, len(aligned) - 4))
    for start in reversed(list(recent_starts)):
        window = aligned.iloc[start : start + 5]
        if len(window) < 5:
            continue
        week_open = float(window["Open"].iloc[0])
        week_high = float(window["High"].max())
        week_low = float(window["Low"].min())
        week_close = float(window["Close"].iloc[-1])
        week_volume = float(window["Volume"].sum())
        weekly_range = week_high - week_low
        if weekly_range <= 0:
            continue
        close_range = (week_close - week_low) / weekly_range
        end_date = window.index[-1]
        weekly_sma50 = _safe_float(weekly_sma50_series.asof(end_date))
        daily_sma50 = _safe_float(sma50.loc[:end_date].dropna().iloc[-1]) if not sma50.loc[:end_date].dropna().empty else None
        if weekly_sma50 is None or daily_sma50 is None:
            continue
        previous_window = aligned.iloc[max(0, start - 5) : start]
        prev_volume = float(previous_window["Volume"].sum()) if len(previous_window) == 5 else None
        volume_avg_10w = _safe_float(volume_avg_10w_series.asof(end_date))
        volume_ok = bool((prev_volume is not None and week_volume > prev_volume) or (volume_avg_10w is not None and week_volume > volume_avg_10w))
        low_touched_50w = weekly_sma50 * 0.97 <= week_low <= weekly_sma50 * 1.005
        close_reclaimed_50w = week_close > weekly_sma50
        week_down = week_close < week_open
        if (
            week_down
            and close_range >= 0.5
            and volume_ok
            and low_touched_50w
            and close_reclaimed_50w
            and week_close > daily_sma50
        ):
            return ChartSignal(
                "positive",
                "Unterstützungswoche",
                f"50W berührt/zurückerobert, Wochen-Schluss obere Hälfte ({close_range:.0%}), Volumen bestätigt",
            )
    return None


def _bearish_outside_day_mask(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    close_range: pd.Series,
) -> pd.Series:
    daily_range = (high - low).replace(0, np.nan)
    upper_wick_ratio = (high - pd.concat([open_, close], axis=1).max(axis=1)) / daily_range
    return (
        (high > high.shift(1))
        & (low < low.shift(1))
        & (close_range <= 1 / 3)
        & (upper_wick_ratio >= 0.4)
    ).fillna(False)


def _bearish_engulfing_mask(open_: pd.Series, close: pd.Series, close_range: pd.Series) -> pd.Series:
    current_body_high = pd.concat([open_, close], axis=1).max(axis=1)
    current_body_low = pd.concat([open_, close], axis=1).min(axis=1)
    previous_body_high = pd.concat([open_.shift(1), close.shift(1)], axis=1).max(axis=1)
    previous_body_low = pd.concat([open_.shift(1), close.shift(1)], axis=1).min(axis=1)
    return (
        (close < open_)
        & (current_body_high >= previous_body_high)
        & (current_body_low <= previous_body_low)
        & (close_range <= 1 / 3)
    ).fillna(False)


def _moving_average_distance_warnings(
    price: float | None,
    averages: Mapping[str, tuple[float | None, float]],
) -> list[str]:
    if price is None:
        return []
    warnings: list[str] = []
    for label, (average, threshold) in averages.items():
        distance = _distance_pct(price, average)
        if distance is None:
            continue
        if abs(distance) >= threshold:
            warnings.append(f"{label} {distance:+.1f}% (Limit ±{threshold:.0f}%)")
    return warnings


def _moving_average_distance_details(
    price: float | None,
    averages: Mapping[str, tuple[float | None, float]],
) -> list[str]:
    if price is None:
        return []
    details: list[str] = []
    for label, (average, threshold) in averages.items():
        distance = _distance_pct(price, average)
        if distance is not None:
            details.append(f"{label} {distance:+.1f}% (Limit ±{threshold:.0f}%)")
    return details


def _missing_check(
    category: AssessmentCategory,
    label: str,
    *,
    severity: Literal["info", "warning", "critical"] = "warning",
) -> AssessmentCheck:
    return AssessmentCheck(category=category, label=label, passed=False, detail="Nicht verfügbar", severity=severity)


def _round_half_up_int(value: float) -> int:
    return int(Decimal(str(float(value))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _distance_pct(price: float | None, average: float | None) -> float | None:
    if price is None or average is None or average == 0:
        return None
    return (price / average - 1) * 100


def _rs_line_detail(rs_context: Mapping[str, Any], average_key: str) -> str:
    current = _safe_float(rs_context.get("rs_line_last"))
    average = _safe_float(rs_context.get(average_key))
    if current is None or average is None:
        return "Nicht verfügbar"
    return f"{current:.2f} vs {average:.2f}"


def _pct_detail(value: Any, label: str) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "Nicht verfügbar"
    return f"{label}: {numeric:+.1f}%"


def _point_value(point: Any, key: str) -> Any:
    if isinstance(point, Mapping):
        return point.get(key)
    return getattr(point, key, None)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(numeric) or np.isinf(numeric):
        return None
    return numeric


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed.date()


def _int_or_none(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(round(numeric))
