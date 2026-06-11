from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

import numpy as np
import pandas as pd


AssessmentCategory = Literal["fundamental", "technical", "trend", "risk"]
SignalCategory = Literal["positive", "negative", "neutral"]
VerdictTone = Literal["good", "neutral", "warning", "bad"]


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
    checks: list[AssessmentCheck] = field(default_factory=list)
    chart_signals: list[ChartSignal] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compute_stock_assessment(
    ticker: str,
    bars: Sequence[Any],
    *,
    rs_context: Mapping[str, Any] | None = None,
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
    checks, cmf_value = evaluate_technicals(df, rs_context=rs)
    chart_signals = evaluate_chart_signs(df, rs_context=rs)
    metrics = _compute_metrics(df, cmf_value=cmf_value, rs_context=rs)
    technical_score = _technical_points_score(checks, metrics.rs_rating, cmf_value)
    fundamental_score = 50.0
    ma_score = _moving_average_score(df)
    positive_count = sum(1 for signal in chart_signals if signal.category == "positive")
    negative_count = sum(1 for signal in chart_signals if signal.category == "negative")
    chart_score = _chart_behavior_score_100(positive_count, negative_count)
    overall = _round_half_up_int(np.mean([technical_score, fundamental_score, chart_score, ma_score]))
    verdict_label, verdict_tone, verdict_text = _build_verdict(overall, checks, metrics)
    drivers, warnings = _build_drivers_and_warnings(checks, chart_signals, fundamentals_available=False)

    return StockAssessmentResult(
        ticker=clean,
        as_of=df.index[-1].date().isoformat(),
        source="database",
        data_status="fresh",
        message="Bewertung aus gecachten Price-Bars und gespeichertem RS-Kontext.",
        verdict_label=verdict_label,
        verdict_tone=verdict_tone,
        verdict_text=verdict_text,
        fundamentals_available=False,
        scores=StockAssessmentScores(
            overall=overall,
            technical=technical_score,
            fundamental=fundamental_score,
            moving_averages=ma_score,
            chart_behavior=chart_score,
        ),
        metrics=metrics,
        checks=checks,
        chart_signals=chart_signals,
        drivers=drivers,
        warnings=warnings,
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
            category="risk",
            label="Preis >= $15",
            passed=price is not None and price >= 15,
            detail=f"${price:,.2f}" if price is not None else "Nicht verfügbar",
            severity="critical",
        )
    )

    high_52w = high.rolling(252, min_periods=20).max().iloc[-1]
    if price is not None and pd.notna(high_52w) and float(high_52w) > 0:
        distance = (price / float(high_52w) - 1) * 100
        checks.append(
            AssessmentCheck(
                category="technical",
                label="Nahe am 52W-Hoch",
                passed=distance > -10,
                detail=f"{distance:+.1f}% vom Hoch (${float(high_52w):,.2f})",
            )
        )
    else:
        checks.append(_missing_check("technical", "Nahe am 52W-Hoch"))

    avg_volume_20 = volume.tail(20).mean()
    dollar_volume_mio = avg_volume_20 * price / 1_000_000 if price and pd.notna(avg_volume_20) else np.nan
    if pd.notna(dollar_volume_mio):
        checks.append(
            AssessmentCheck(
                category="risk",
                label="Dollar-Volumen >= $30 Mio.",
                passed=float(dollar_volume_mio) >= 30,
                detail=f"${float(dollar_volume_mio):,.0f} Mio./Tag",
                severity="critical",
            )
        )
    else:
        checks.append(_missing_check("risk", "Dollar-Volumen >= $30 Mio.", severity="critical"))

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

    ema21 = close.ewm(span=21).mean()
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


def evaluate_chart_signs(
    df: pd.DataFrame,
    *,
    rs_context: Mapping[str, Any] | None = None,
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
    ema21 = close.ewm(span=21).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    signals: list[ChartSignal] = []

    high_volume_up = int(((close.tail(20) > close.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    high_volume_down = int(((close.tail(20) < close.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    if high_volume_up > high_volume_down:
        signals.append(ChartSignal("positive", "Mehr Gewinn- als Verlusttage mit hohem Vol.", f"{high_volume_up} vs {high_volume_down} (20T)"))
    elif high_volume_down > high_volume_up:
        signals.append(ChartSignal("negative", "Mehr Verlust- als Gewinntage mit hohem Vol.", f"{high_volume_down} vs {high_volume_up} (20T)"))

    above_21 = int((close.tail(10) > ema21.tail(10)).sum())
    above_50 = int((close.tail(10) > sma50.tail(10)).sum())
    if above_21 >= 8 and above_50 >= 8:
        signals.append(ChartSignal("positive", "Leben über den Durchschnitten", f"{above_21}/10 über 21-EMA, {above_50}/10 über 50-SMA"))
    elif above_21 <= 2 or above_50 <= 2:
        signals.append(ChartSignal("negative", "Leben unter den Durchschnitten", f"{above_21}/10 über 21-EMA, {above_50}/10 über 50-SMA"))

    e21 = _safe_float(ema21.iloc[-1])
    s50 = _safe_float(sma50.iloc[-1])
    s200 = _safe_float(sma200.iloc[-1])
    if e21 is not None and s50 is not None and s200 is not None:
        if e21 > s50 > s200:
            signals.append(ChartSignal("positive", "Durchschnitte in richtiger Ordnung", "21>50>200"))
        elif e21 < s50 < s200:
            signals.append(ChartSignal("negative", "Durchschnitte in falscher Ordnung", "21<50<200"))

    if len(ema21) >= 10 and s50 is not None:
        ema_up = _safe_float(ema21.iloc[-1]) is not None and _safe_float(ema21.iloc[-10]) is not None and ema21.iloc[-1] > ema21.iloc[-10]
        sma_up = pd.notna(sma50.iloc[-10]) and sma50.iloc[-1] > sma50.iloc[-10]
        if ema_up and sma_up:
            signals.append(ChartSignal("positive", "Nach oben zeigende Durchschnittslinien"))
        elif not ema_up and sma_up is False:
            signals.append(ChartSignal("negative", "Nach unten zeigende Durchschnittslinien"))

    up_gaps = int(((open_.tail(20) > high.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    down_gaps = int(((open_.tail(20) < low.shift(1).tail(20)) & (volume.tail(20) > vol_avg_50.tail(20))).sum())
    if up_gaps > 0:
        signals.append(ChartSignal("positive", "Positive Kurslücken", f"{up_gaps} in 20T"))
    if down_gaps > 0:
        signals.append(ChartSignal("negative", "Negative Kurslücken bei hohem Vol.", f"{down_gaps} in 20T"))

    drops = pct.tail(20) < -0.005
    low_volume_drops = int((drops & (volume.tail(20) < vol_avg_50.tail(20) * 0.8)).sum())
    high_volume_drops = int((drops & (volume.tail(20) > vol_avg_50.tail(20) * 1.2)).sum())
    if low_volume_drops >= 3:
        signals.append(ChartSignal("positive", "Preisrückgänge bei niedrigem Vol.", f"{low_volume_drops} Tage"))
    if high_volume_drops >= 3:
        signals.append(ChartSignal("negative", "Preisrückgänge bei hohem Vol.", f"{high_volume_drops} Tage"))

    high_volume_rises = int(((pct.tail(20) > 0.005) & (volume.tail(20) > vol_avg_50.tail(20) * 1.2)).sum())
    if high_volume_rises >= 3:
        signals.append(ChartSignal("positive", "Preissteigerungen bei hohem Vol.", f"{high_volume_rises} in 20T"))

    close_range = _close_range_position(close, high, low)
    stall_days = int(((pct.tail(10) >= 0) & (pct.tail(10) < 0.005) & (volume.tail(10) >= volume.shift(1).tail(10) * 0.95) & (close_range.tail(10) < 0.5)).sum())
    if stall_days >= 2:
        signals.append(ChartSignal("negative", "Stau-Tage", f"{stall_days} in 10T"))

    upside_reversals = int(((open_.tail(10) < close.shift(1).tail(10)) & (close.tail(10) > open_.tail(10)) & (close_range.tail(10) > 0.7)).sum())
    downside_reversals = int(((open_.tail(10) > close.shift(1).tail(10)) & (close.tail(10) < open_.tail(10)) & (close_range.tail(10) < 0.3)).sum())
    if upside_reversals >= 2:
        signals.append(ChartSignal("positive", "Upside Reversals", f"{upside_reversals} in 10T"))
    if downside_reversals >= 2:
        signals.append(ChartSignal("negative", "Downside Reversals", f"{downside_reversals} in 10T"))

    signals.extend(_rs_chart_signals(rs))

    avg_close_range = _safe_float(close_range.tail(5).mean())
    if avg_close_range is not None and avg_close_range > 0.6:
        signals.append(ChartSignal("positive", "Schlussposition obere 40%", f"Ø {avg_close_range:.0%}"))
    elif avg_close_range is not None and avg_close_range < 0.25:
        signals.append(ChartSignal("negative", "Tiefe Schlussposition", f"Ø {avg_close_range:.0%}"))

    current_close = _safe_float(close.iloc[-1])
    if current_close is not None and s50 is not None and s50 > 0:
        distance_50 = (current_close / s50 - 1) * 100
        if distance_50 > 15:
            signals.append(ChartSignal("negative", "Großer Abstand zu Durchschnitten", f"{distance_50:+.1f}% zur 50-SMA"))

    weekly_close = close.resample("W-FRI").last().dropna()
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

    signals.extend(_recent_reaction_signals(close, high, low, open_, pct, s50))
    return signals


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
    ema21 = close.ewm(span=21).mean()
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
    )


def _technical_points_score(
    technical_checks: Sequence[AssessmentCheck],
    rs_rating: int | float | None,
    cmf_value: float | None,
) -> float:
    check_map = {check.label: bool(check.passed) for check in technical_checks}
    score = 0.0
    max_score = 95.0
    score += 5 if check_map.get("Preis >= $15", False) else 0
    score += 5 if check_map.get("Nahe am 52W-Hoch", False) else 0
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
    ema21 = _safe_float(close.ewm(span=21).mean().iloc[-1])
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
) -> tuple[list[str], list[str]]:
    driver_labels = {
        "RS-Bewertung >=80",
        "RS-Linie steigt über 13 Wochen",
        "RS-Linie nahe 52W-Hoch",
        "Kurs über 200-SMA",
        "Kurs über 50-SMA",
        "MA-Ordnung (21>50>200)",
        "CMF Rating A oder B",
        "Up/Down Vol. Ratio >=1.0",
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
    return drivers[:8], warnings[:8]


def _coerce_bars_to_frame(bars: Sequence[Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        bar_date = _point_value(bar, "date")
        close = _safe_float(_point_value(bar, "close"))
        if bar_date is None or close is None:
            continue
        timestamp = pd.to_datetime(bar_date, errors="coerce")
        if pd.isna(timestamp):
            continue
        rows.append(
            {
                "Date": pd.Timestamp(timestamp).normalize(),
                "Open": _safe_float(_point_value(bar, "open")) or close,
                "High": _safe_float(_point_value(bar, "high")) or close,
                "Low": _safe_float(_point_value(bar, "low")) or close,
                "Close": close,
                "Volume": _safe_float(_point_value(bar, "volume")) or 0.0,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows).drop_duplicates("Date", keep="last").sort_values("Date")
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
    if bool(rs_context.get("above_21")) and bool(rs_context.get("above_50")):
        signals.append(ChartSignal("positive", "RS-Linie über ihren Durchschnitten"))
    elif rs_context.get("above_50") is False:
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
) -> list[ChartSignal]:
    signals: list[ChartSignal] = []
    if len(pct) >= 3:
        r1, r2, r3 = pct.iloc[-3] * 100, pct.iloc[-2] * 100, pct.iloc[-1] * 100
        if r1 < 0 and r2 < 0 and r3 < 0 and r3 < r2 < r1 and r3 <= -2.0:
            signals.append(ChartSignal("negative", "Beschleunigte Verluste", f"{r1:+.1f}% -> {r2:+.1f}% -> {r3:+.1f}%"))
    if len(close) >= 20 and sma50_last is not None:
        high_20 = high.tail(20).max()
        drawdown = _safe_float((close.iloc[-1] / high_20 - 1) * 100)
        if drawdown is not None and -12.0 <= drawdown <= -8.0 and close.iloc[-1] > sma50_last:
            signals.append(ChartSignal("neutral", "Natürliche Reaktion", f"{drawdown:+.1f}% vom 20T-Hoch"))
    if len(close) >= 3:
        red_2 = close.iloc[-3] < open_.iloc[-3] and close.iloc[-2] < open_.iloc[-2]
        daily_range = high.iloc[-1] - low.iloc[-1]
        close_range = (close.iloc[-1] - low.iloc[-1]) / daily_range if daily_range > 0 else 0.5
        if red_2 and close_range >= 0.5:
            signals.append(ChartSignal("neutral", "2,5-Tage-Korrektur", "2 rote Tage, Tag 3 Schluss obere Hälfte"))
    if len(close) >= 21:
        prior_low = low.iloc[-21:-1].min()
        volume_like = True
        daily_range = high.iloc[-1] - low.iloc[-1]
        close_range = (close.iloc[-1] - low.iloc[-1]) / daily_range if daily_range > 0 else 0.5
        if low.iloc[-1] < prior_low and close.iloc[-1] > prior_low and close_range >= 0.5 and volume_like:
            signals.append(ChartSignal("positive", "Shake-out", "Tief unter Vor-20T-Tief, Schluss wieder darüber"))
    return signals


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


def _int_or_none(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(round(numeric))
