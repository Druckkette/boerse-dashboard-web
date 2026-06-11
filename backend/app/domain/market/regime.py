from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MarketPhase = Literal["rot", "gelb", "gruen", "aufwaertstrend", "neutral"]
BreadthMode = Literal["schutz", "wachsam", "rueckenwind"]
Tone = Literal["good", "neutral", "warning", "bad"]


STRESS_VOLATILITY_REGIMES = {"Risk Off bestätigt", "Kurzer Volatilitätsschock", "Fragile Rally"}


@dataclass(frozen=True)
class MarketRegimeInput:
    pct_above_20sma: float | None
    pct_above_50sma: float | None
    pct_above_200sma: float | None
    mcclellan: float
    advancers: int
    decliners: int
    new_highs: int
    new_lows: int
    coverage_ratio: float
    universe_size: int
    covered_count: int
    volatility_regime: str = "Nicht berechnet"
    volatility_summary: dict | None = None


@dataclass(frozen=True)
class MarketRegimeResult:
    phase: MarketPhase
    breadth_mode: BreadthMode
    warning_count: int
    action: str
    kpis: list[dict]
    metrics: dict


def classify_market_regime(regime_input: MarketRegimeInput) -> MarketRegimeResult:
    pct_50 = regime_input.pct_above_50sma or 0
    pct_200 = regime_input.pct_above_200sma or 0
    volatility_regime = regime_input.volatility_regime or "Nicht berechnet"
    warning_count = _count_warnings(regime_input, volatility_regime=volatility_regime)
    phase, breadth_mode = _phase_and_breadth_mode(
        pct_above_50sma=pct_50,
        pct_above_200sma=pct_200,
        warning_count=warning_count,
    )
    action = _action_for_market_state(phase, breadth_mode, volatility_regime, warning_count)
    kpis = [
        _kpi_dict(
            "Breite 50-SMA",
            _format_pct(regime_input.pct_above_50sma),
            "über 50-SMA",
            _tone_for_pct(regime_input.pct_above_50sma),
        ),
        _kpi_dict(
            "Breite 200-SMA",
            _format_pct(regime_input.pct_above_200sma),
            "über 200-SMA",
            _tone_for_pct(regime_input.pct_above_200sma),
        ),
        _kpi_dict(
            "McClellan",
            f"{regime_input.mcclellan:+.1f}",
            "A/D Momentum",
            "good" if regime_input.mcclellan >= 0 else "warning",
        ),
        _kpi_dict(
            "Coverage",
            _format_pct(regime_input.coverage_ratio * 100),
            f"{regime_input.covered_count}/{regime_input.universe_size}",
            "good" if regime_input.coverage_ratio >= 0.8 else "warning",
        ),
        _kpi_dict(
            "Vol Regime",
            volatility_regime,
            "VIX/VIXY",
            _tone_for_volatility_regime(volatility_regime),
        ),
    ]
    metrics = {
        "action": action,
        "coverage_ratio": regime_input.coverage_ratio,
        "universe_size": regime_input.universe_size,
        "covered_count": regime_input.covered_count,
        "advancers": regime_input.advancers,
        "decliners": regime_input.decliners,
        "new_highs": regime_input.new_highs,
        "new_lows": regime_input.new_lows,
        "mcclellan": regime_input.mcclellan,
        "pct_above_20sma": regime_input.pct_above_20sma,
        "pct_above_50sma": regime_input.pct_above_50sma,
        "pct_above_200sma": regime_input.pct_above_200sma,
        "volatility": regime_input.volatility_summary or {},
        "kpis": kpis,
    }
    return MarketRegimeResult(
        phase=phase,
        breadth_mode=breadth_mode,
        warning_count=warning_count,
        action=action,
        kpis=kpis,
        metrics=metrics,
    )


def _count_warnings(regime_input: MarketRegimeInput, *, volatility_regime: str) -> int:
    warning_count = 0
    warning_count += int((regime_input.pct_above_50sma or 0) < 45)
    warning_count += int((regime_input.pct_above_200sma or 0) < 45)
    warning_count += int(regime_input.mcclellan < 0)
    warning_count += int(regime_input.decliners > regime_input.advancers)
    warning_count += int(regime_input.new_lows > regime_input.new_highs)
    warning_count += int(regime_input.coverage_ratio < 0.65)
    warning_count += int(volatility_regime in STRESS_VOLATILITY_REGIMES)
    return warning_count


def _phase_and_breadth_mode(
    *,
    pct_above_50sma: float,
    pct_above_200sma: float,
    warning_count: int,
) -> tuple[MarketPhase, BreadthMode]:
    if warning_count >= 4 or (pct_above_50sma < 40 and pct_above_200sma < 40):
        return "rot", "schutz"
    if warning_count >= 2 or pct_above_50sma < 50:
        return "gelb", "wachsam"
    return "gruen", "rueckenwind"


def _action_for_market_state(
    phase: str,
    breadth_mode: str,
    volatility_regime: str,
    warning_count: int,
) -> str:
    if phase == "rot":
        return "Defensiv bleiben, neue Käufe stark filtern und bestehende Risiken kritisch prüfen."
    if volatility_regime == "Risk Off bestätigt":
        return "Volatilität bestätigt Stress. Risiko reduzieren und keine aggressiven Neueinstiege."
    if breadth_mode == "schutz":
        return "Marktbreite im Schutzmodus. Positionsgrößen klein halten und Cash optional erhöhen."
    if warning_count >= 4:
        return f"{warning_count} Warnzeichen aktiv. Defensive Haltung trotz laufender Ampelphase."
    if phase == "gelb":
        return "Wachsam bleiben, Positionsgrößen kontrollieren und Breakouts nur selektiv handeln."
    if phase == "aufwaertstrend":
        return "MA-Ordnung bestätigt. Führende Aktien beobachten und Risiko schrittweise erhöhen."
    if phase == "gruen":
        return "Konstruktiv bleiben, Qualitäts-Setups bevorzugen und Stops diszipliniert nachziehen."
    return "Marktdaten prüfen und keine großen Risikoänderungen ohne frische Breitenwerte vornehmen."


def _kpi_dict(label: str, value: str, detail: str, tone: Tone) -> dict:
    return {"label": label, "value": value, "detail": detail, "tone": tone}


def _tone_for_pct(value: float | None) -> Tone:
    if value is None:
        return "neutral"
    if value >= 60:
        return "good"
    if value >= 45:
        return "neutral"
    if value >= 35:
        return "warning"
    return "bad"


def _tone_for_volatility_regime(regime: str) -> Tone:
    if regime == "Risk Off bestätigt":
        return "bad"
    if regime in {"Kurzer Volatilitätsschock", "Fragile Rally"}:
        return "warning"
    if regime == "Risk On / ruhig":
        return "good"
    return "neutral"


def _format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"
