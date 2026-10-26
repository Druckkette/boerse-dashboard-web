"""Causal, conservative chart geometry for Groos, chapter 4.2.

Prices are the provider's split-adjusted OHLC, NOT dividend-adjusted closes.
Every candidate is assessed using only observations available on detected_on.
Later bars can change its lifecycle, never its geometry or detection date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from math import isfinite
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


ALGORITHM_VERSION = "chapter-4.2-v1"
PatternKind = Literal[
    "cup_with_handle", "cup_without_handle", "double_bottom", "high_tight_flag", "box"
]
LABELS = {
    "cup_with_handle": "Cup with Handle",
    "cup_without_handle": "Cup without Handle",
    "double_bottom": "Double Bottom",
    "high_tight_flag": "High Tight Flag",
    "box": "Box",
}


class PatternParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)
    cup_min_weeks: int = Field(6, ge=6, le=30)
    base_max_weeks: int = Field(65, ge=7, le=65)
    cup_min_depth_pct: float = Field(12, ge=5, le=40)
    cup_max_depth_pct: float = Field(50, ge=12, le=50)
    cup_min_floor_fraction: float = Field(0.10, ge=0.05, le=0.6)
    cup_max_shape_error: float = Field(0.12, ge=0.05, le=0.3)
    rim_tolerance_pct: float = Field(15, ge=1, le=15)
    handle_min_days: int = Field(5, ge=5, le=15)
    handle_max_days: int = Field(25, ge=5, le=25)
    handle_min_depth_pct: float = Field(5, ge=1, le=12)
    handle_max_depth_pct: float = Field(15, ge=5, le=15)
    double_bottom_min_weeks: int = Field(7, ge=7, le=30)
    double_bottom_max_depth_pct: float = Field(50, ge=10, le=50)
    double_bottom_max_undercut_pct: float = Field(10, ge=0.1, le=20)
    flag_min_gain_pct: float = Field(90, ge=90, le=120)
    flag_max_gain_pct: float = Field(1000, ge=100, le=1000)
    flag_min_depth_pct: float = Field(10, ge=5, le=20)
    flag_max_depth_pct: float = Field(25, ge=10, le=25)
    box_min_weeks: int = Field(4, ge=4, le=12)
    box_max_depth_pct: float = Field(15, ge=3, le=15)
    volume_dry_up_ratio: float = Field(0.9, ge=0.3, le=1)
    flag_volume_ratio: float = Field(0.75, ge=0.2, le=1)
    breakout_volume_ratio: float = Field(1.4, ge=1, le=3)
    # Geometry and qualitative volume evidence are separate by default. The
    # book's illustrated IBKR/NFLX bases also contain high-volume shake-outs.
    require_volume: bool = False

    @model_validator(mode="after")
    def consistent(self):
        for lower, upper in [
            (self.cup_min_depth_pct, self.cup_max_depth_pct),
            (self.handle_min_depth_pct, self.handle_max_depth_pct),
            (self.handle_min_days, self.handle_max_days),
            (self.flag_min_depth_pct, self.flag_max_depth_pct),
            (self.flag_min_gain_pct, self.flag_max_gain_pct),
            (
                max(self.cup_min_weeks, self.double_bottom_min_weeks, self.box_min_weeks),
                self.base_max_weeks,
            ),
        ]:
            if lower > upper:
                raise ValueError("Minimum darf das zugehörige Maximum nicht überschreiten.")
        return self

    @property
    def fingerprint(self) -> str:
        return sha256(
            (ALGORITHM_VERSION + json.dumps(self.model_dump(), sort_keys=True)).encode()
        ).hexdigest()[:16]


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None


class PatternPoint(BaseModel):
    date: str
    value: float
    label: str


class Pattern(BaseModel):
    id: str
    ticker: str
    kind: PatternKind
    label: str
    start_date: str
    end_date: str
    detected_on: str
    breakout_on: str | None = None
    status: Literal["ready", "breakout", "unconfirmed_breakout", "invalidated", "expired"]
    pivot: float
    depth_pct: float
    duration_days: int
    volume_ratio: float | None
    breakout_volume_ratio: float | None = None
    parameter_hash: str
    points: list[PatternPoint]
    checks: list[str]
    warnings: list[str]


def validate_bars(bars: list[Bar]) -> list[str]:
    if len(bars) < 25:
        return ["Zu wenig abgeschlossene Handelstage (mindestens 25 erforderlich)."]
    for i, b in enumerate(bars):
        values = [b.open, b.high, b.low, b.close]
        if (
            not all(isfinite(v) and v > 0 for v in values)
            or not b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high
        ):
            return [f"Ungültige OHLC-Daten am {b.date}."]
        if b.volume is not None and (not isfinite(b.volume) or b.volume < 0):
            return [f"Ungültiges Volumen am {b.date}."]
        if i and (b.date <= bars[i - 1].date or (b.date - bars[i - 1].date).days > 10):
            return [
                "Doppelte, unsortierte oder lückenhafte Kurse; keine verlässliche Musterprüfung."
            ]
        if i and abs(b.close / bars[i - 1].close - 1) > 0.60:
            return ["Extremer Kurssprung: Splitbereinigung oder Datenquelle zuerst prüfen."]
    return []


def _ratio(bars: list[Bar], numerator: list[Bar]) -> float | None:
    if (
        not bars
        or not numerator
        or any(b.volume is None or b.volume <= 0 for b in [*bars, *numerator])
    ):
        return None
    return float(np.mean([b.volume for b in numerator]) / np.mean([b.volume for b in bars]))


def _volume_ok(ratio: float | None, p: PatternParameters, limit: float | None = None) -> bool:
    return not p.require_volume or (ratio is not None and ratio <= (limit or p.volume_dry_up_ratio))


def _anchors(bars: list[Bar]) -> list[tuple[int, int]]:
    """(left peak, first session of first negative close-to-close week).

    The first negative week must be complete before a pattern is detected;
    its preceding week supplies the left rim. Intraday/weekend bars are removed
    by the service before this pure function is called.
    """
    weeks: list[list[int]] = []
    for i, b in enumerate(bars):
        if not weeks or bars[weeks[-1][0]].date.isocalendar()[:2] != b.date.isocalendar()[:2]:
            weeks.append([])
        weeks[-1].append(i)
    anchors = []
    for previous, current in zip(weeks, weeks[1:]):
        left = max(previous, key=lambda i: bars[i].high)
        if bars[current[-1]].close < bars[previous[-1]].close and bars[left].high >= max(
            b.high for b in bars[max(0, left - 10) : left + 1]
        ):
            anchors.append((left, current[0]))
    return anchors


def detect_patterns(
    ticker: str, bars: list[Bar], p: PatternParameters | None = None
) -> list[Pattern]:
    p = p or PatternParameters()
    if validate_bars(bars):
        return []
    highs = np.array([b.high for b in bars])
    lows = np.array([b.low for b in bars])
    closes = np.array([b.close for b in bars])
    candidates: list[Pattern] = []

    def emit(
        kind: PatternKind,
        s: int,
        base: int,
        end: int,
        pivot: float,
        geometry: list[tuple[int, float, str]],
        ratio: float | None,
        checks: list[str],
        quality_warnings: list[str] | None = None,
    ):
        segment = bars[s : end + 1]
        depth = (1 - min(b.low for b in segment) / bars[s].high) * 100
        detected = end
        # Weekly anchor validation consumes its entire first red week.
        first_week_end = base
        while (
            first_week_end + 1 < len(bars)
            and bars[first_week_end + 1].date.isocalendar()[:2] == bars[base].date.isocalendar()[:2]
        ):
            first_week_end += 1
        detected = max(detected, first_week_end)
        if detected >= len(bars):
            return
        warnings = list(quality_warnings or [])
        if ratio is None:
            warnings.append(
                "Volumen nicht vollständig verfügbar; die Basis ist nur geometrisch geprüft."
            )
        elif ratio > (p.flag_volume_ratio if kind == "high_tight_flag" else p.volume_dry_up_ratio):
            warnings.append(
                "Volumen trocknet nicht ausreichend aus; die Basis ist nur geometrisch geprüft."
            )
        else:
            checks = [*checks, "Rückläufiges Volumen nachgewiesen"]
        if depth > 40:
            warnings.append("Tiefe über dem Idealwert von 40 %.")
        prior = bars[max(0, s - 60) : s]
        if not prior or bars[s].high / min(b.close for b in prior) < 1.3:
            warnings.append("Vorausgehender Anstieg von etwa 30 % nicht nachgewiesen.")
        warnings.append("RS-Linie und Marktumfeld separat prüfen.")
        pattern = Pattern(
            id=f"{ticker}:{kind}:{bars[s].date}:{bars[end].date}:{p.fingerprint}",
            ticker=ticker,
            kind=kind,
            label=LABELS[kind],
            start_date=bars[base].date.isoformat(),
            end_date=bars[end].date.isoformat(),
            detected_on=bars[detected].date.isoformat(),
            status="ready",
            pivot=round(float(pivot), 6),
            depth_pct=round(depth, 2),
            duration_days=(bars[end].date - bars[base].date).days + 1,
            volume_ratio=round(ratio, 3) if ratio is not None else None,
            parameter_hash=p.fingerprint,
            points=[
                PatternPoint(date=bars[i].date.isoformat(), value=float(v), label=label)
                for i, v, label in geometry
            ],
            checks=checks,
            warnings=warnings,
        )
        floor = min(b.low for b in segment)
        for i in range(detected, len(bars)):
            if bars[i].close < floor:
                pattern.status = "invalidated"
                break
            if bars[i].close > pivot:
                vr = _ratio(bars[max(0, i - 50) : i], [bars[i]]) if i >= 50 else None
                pattern.breakout_on = bars[i].date.isoformat()
                pattern.breakout_volume_ratio = round(vr, 3) if vr is not None else None
                pattern.status = (
                    "breakout"
                    if vr is not None and vr >= p.breakout_volume_ratio
                    else "unconfirmed_breakout"
                )
                break
            if (bars[i].date - bars[detected].date).days > 35:
                pattern.status = "expired"
                break
        candidates.append(pattern)

    for s, base in _anchors(bars):
        peak = highs[s]
        stop = min(len(bars), base + p.base_max_weeks * 5 + 10)
        emitted: set[str] = set()
        for e in range(max(base + 14, s + 20), stop):
            days = (bars[e].date - bars[base].date).days + 1
            if days > p.base_max_weeks * 7:
                break
            segment = bars[s : e + 1]
            bottom = s + int(np.argmin(lows[s : e + 1]))
            depth = (1 - lows[bottom] / peak) * 100
            if np.max(closes[s:e]) > peak * 1.015:
                break  # the original resistance was already broken
            # Flat bases: two spaced tests at each boundary, little directional drift.
            if (
                "box" not in emitted
                and closes[e] <= peak
                and days >= p.box_min_weeks * 7
                and 1 <= depth <= p.box_max_depth_pct
            ):
                span = float(highs[s : e + 1].max() - lows[s : e + 1].min())
                band = 0.22 * span
                tops = np.where(highs[s : e + 1] >= highs[s : e + 1].max() - band)[0]
                floors = np.where(lows[s : e + 1] <= lows[s : e + 1].min() + band)[0]
                drift = abs(
                    float(np.polyfit(np.arange(e - s + 1), closes[s : e + 1], 1)[0]) * (e - s)
                )
                third = max(3, len(segment) // 3)
                vr = _ratio(segment[:third], segment[-third:])
                if (
                    len(tops) > 1
                    and tops[-1] - tops[0] >= 10
                    and len(floors) > 1
                    and floors[-1] - floors[0] >= 10
                    and drift <= span * 0.35
                    and _volume_ok(vr, p)
                ):
                    ceiling = float(highs[s : e + 1].max())
                    emit(
                        "box",
                        s,
                        base,
                        e,
                        ceiling,
                        [
                            (s, ceiling, "Box-Oberkante"),
                            (e, ceiling, "Widerstand"),
                            (e, float(lows[bottom]), "Box-Unterkante"),
                            (s, float(lows[bottom]), "Unterstützung"),
                            (s, ceiling, "Box"),
                        ],
                        vr,
                        [
                            "Mindestens vier Wochen",
                            "Maximale Tiefe eingehalten",
                            "Zwei getrennte Tests beider Grenzen",
                            "Waagerechte Handelsspanne",
                        ],
                    )
                    emitted.add("box")
            if (
                days < p.cup_min_weeks * 7
                or not p.cup_min_depth_pct <= depth <= p.cup_max_depth_pct
            ):
                continue
            # The recovering rim must be near the original high and precede a breakout.
            if highs[e] < peak * (1 - p.rim_tolerance_pct / 100):
                continue
            values = closes[s : e + 1]
            smooth = np.convolve(values, np.ones(3) / 3, mode="valid")
            width = peak - lows[bottom]
            position = (bottom - s) / (e - s)
            # Candle wicks determine depth, but must not determine how long the
            # closing-price curve spends at its floor (a single shake-out wick
            # otherwise makes every genuine rounded floor disappear).
            smooth_floor = float(smooth.min())
            smooth_height = float(max(smooth[0], smooth[-1]) - smooth_floor)
            floor_fraction = float(np.mean(smooth <= smooth_floor + smooth_height * 0.22))
            x = np.linspace(-1, 1, len(smooth))
            fit = np.polyfit(x, smooth, 2)
            shape_error = float(np.sqrt(np.mean((smooth - np.polyval(fit, x)) ** 2)) / width)
            k = int(np.argmin(smooth))
            v_residual = []
            for leg in (smooth[: k + 1], smooth[k:]):
                if len(leg) > 2:
                    lx = np.arange(len(leg))
                    v_residual.extend(leg - np.polyval(np.polyfit(lx, leg, 1), lx))
            v_error = float(np.sqrt(np.mean(np.square(v_residual))) / width) if v_residual else 0
            # Reject an actual pointed V: two almost straight legs meeting at
            # one bottom. A shake-out wick in a noisy rounded cup is different.
            pointed_v = v_error < 0.06 and floor_fraction < 0.30
            if not (
                0.3 <= position <= 0.7
                and floor_fraction >= p.cup_min_floor_fraction
                and fit[0] > 0
                and shape_error <= p.cup_max_shape_error
                and not pointed_v
            ):
                continue
            third = max(3, (e - s) // 4)
            vr = _ratio(
                bars[s : s + third], bars[max(s, bottom - third // 2) : bottom + third // 2 + 1]
            )
            if not _volume_ok(vr, p):
                continue
            checks = [
                "Cup mindestens sechs Wochen",
                "Tiefe innerhalb der Grenzen",
                "Runder Boden statt V-Erholung",
                "Symmetrie: Boden im mittleren Bereich der Cup-Länge",
            ]
            # A recovered rim on its own is a setup; a later close above the left rim is the breakout.
            if "cup_without_handle" not in emitted and closes[e] >= peak * 0.97:
                emit(
                    "cup_without_handle",
                    s,
                    base,
                    e,
                    float(peak),
                    [
                        (s, peak, "Linker Rand"),
                        (bottom, lows[bottom], "Cup-Tief"),
                        (e, highs[e], "Rechter Rand"),
                    ],
                    vr,
                    checks,
                )
                emitted.add("cup_without_handle")
            if "cup_with_handle" in emitted:
                continue
            # A handle is observable only after at least five subsequent sessions.
            for h in range(e + p.handle_min_days, min(e + p.handle_max_days + 1, stop)):
                if (bars[h].date - bars[base].date).days + 1 > p.base_max_weeks * 7:
                    break
                handle = bars[e : h + 1]
                hp = float(max(b.high for b in handle))
                hl = float(min(b.low for b in handle))
                if hp > peak or hp > highs[e] * 1.005 or max(b.close for b in handle) > peak:
                    break
                hd = (1 - hl / hp) * 100
                if not p.handle_min_depth_pct <= hd <= p.handle_max_depth_pct:
                    continue
                if hl <= (peak + lows[bottom]) / 2 or (hp + hl) / 2 <= (peak + lows[bottom]) / 2:
                    continue
                low_index = e + int(np.argmin(lows[e : h + 1]))
                if low_index <= e or closes[h] <= hl + (hp - hl) * 0.35:
                    continue
                # Falling early lows plus a recovery prevent wedge-up handles.
                if bars[min(e + 2, h)].low >= bars[e].low:
                    continue
                hv = _ratio(bars[max(s, e - 10) : e], bars[e + 1 : h + 1])
                if not _volume_ok(hv, p):
                    continue
                emit(
                    "cup_with_handle",
                    s,
                    base,
                    h,
                    hp,
                    [
                        (s, peak, "Linker Rand"),
                        (bottom, lows[bottom], "Cup-Tief"),
                        (e, hp, "Handle-Hoch"),
                        (low_index, hl, "Handle-Tief"),
                        (h, closes[h], "Handle-Erholung"),
                    ],
                    hv,
                    [
                        *checks,
                        "Handle mindestens fünf Handelstage",
                        "Handle in oberer Cup-Hälfte",
                        "Midpoint-Regel erfüllt",
                        "Abwärtsdrift und Erholung",
                    ],
                    ["Volumen am Cup-Boden nicht bestätigt."]
                    if vr is None or vr > p.volume_dry_up_ratio
                    else [],
                )
                emitted.add("cup_with_handle")
                break

        # Double Bottom: confirmed local troughs, a lower second low, upper-half middle peak.
        troughs = [i for i in range(s + 5, stop - 3) if lows[i] == min(lows[i - 2 : i + 3])]
        found_db = False
        for t1, t2 in ((a, b) for i, a in enumerate(troughs) for b in troughs[i + 1 :]):
            if (
                t2 - t1 < 10
                or not lows[t1] * (1 - p.double_bottom_max_undercut_pct / 100)
                <= lows[t2]
                < lows[t1]
            ):
                continue
            mid = t1 + int(np.argmax(highs[t1 : t2 + 1]))
            mp = highs[mid]
            if lows[t1] != min(lows[s : mid + 1]) or lows[t2] != min(lows[mid : t2 + 1]):
                continue
            if (
                not (peak + lows[t2]) / 2 < mp < peak
                or (1 - lows[t2] / peak) * 100 > p.double_bottom_max_depth_pct
            ):
                continue
            if max(closes[s : t2 + 1]) > peak:
                continue
            vr = _ratio(bars[s : s + 5], [*bars[t1 - 2 : t1 + 3], *bars[t2 - 2 : t2 + 3]])
            if not _volume_ok(vr, p):
                continue
            for e in range(t2 + 3, stop):
                if min(lows[t2 + 1 : e + 1]) < lows[t2]:
                    break  # the second trough was invalidated before recovery
                if (bars[e].date - bars[base].date).days + 1 > p.base_max_weeks * 7:
                    break
                if (bars[e].date - bars[base].date).days + 1 < p.double_bottom_min_weeks * 7:
                    continue
                if closes[e] >= mp * 0.97 and closes[e] > closes[e - 3]:
                    emit(
                        "double_bottom",
                        s,
                        base,
                        e,
                        float(mp),
                        [
                            (s, peak, "Linker Peak"),
                            (t1, lows[t1], "Erstes Tief"),
                            (mid, mp, "Mittelgipfel / Pivot"),
                            (t2, lows[t2], "Tieferes zweites Tief"),
                            (e, closes[e], "Rechte Seite"),
                        ],
                        vr,
                        [
                            "Mindestens sieben Wochen",
                            "Zweites Tief unter erstem Tief",
                            "Mittelgipfel in oberer Hälfte",
                            "Erholung auf rechter Seite",
                        ],
                    )
                    found_db = True
                    break
            if found_db:
                break

        # High Tight Flag: the mast is distinct from the flag and uses 4–8 calendar weeks.
        for origin in range(max(0, s - 42), max(0, s - 18)):
            mast_days = (bars[s].date - bars[origin].date).days
            gain = (peak / bars[origin].close - 1) * 100
            if not 28 <= mast_days <= 56 or not p.flag_min_gain_pct <= gain <= p.flag_max_gain_pct:
                continue
            for e in range(base + 10, min(stop, base + 26)):
                days = (bars[e].date - bars[base].date).days + 1
                flag = bars[s : e + 1]
                d = (1 - min(b.low for b in flag) / peak) * 100
                vr = _ratio(bars[origin : s + 1], bars[base : e + 1])
                if (
                    21 <= days <= 35
                    and p.flag_min_depth_pct <= d <= p.flag_max_depth_pct
                    and max(b.high for b in flag) <= peak * 1.005
                    and closes[e] >= peak * 0.9
                    and _volume_ok(vr, p, p.flag_volume_ratio)
                ):
                    lo = s + int(np.argmin(lows[s : e + 1]))
                    emit(
                        "high_tight_flag",
                        s,
                        base,
                        e,
                        float(max(b.high for b in flag)),
                        [
                            (origin, closes[origin], "Mastbeginn"),
                            (s, peak, "Mast / Flaggenhoch"),
                            (lo, lows[lo], "Flaggentief"),
                            (e, closes[e], "Flagge"),
                        ],
                        vr,
                        [
                            "Mast in vier bis acht Wochen",
                            f"Mastgewinn {gain:.1f} %",
                            "Flagge drei bis fünf Wochen",
                            "Flaggentiefe eingehalten",
                        ],
                    )
                    emitted.add("high_tight_flag")
                    break
            if "high_tight_flag" in emitted:
                break

    # One representation per overlapping geometry; prefer the complete handled cup.
    priority = {
        "high_tight_flag": 5,
        "double_bottom": 4,
        "cup_with_handle": 3,
        "cup_without_handle": 2,
        "box": 1,
    }
    selected: list[Pattern] = []
    for candidate in sorted(
        candidates, key=lambda v: (-priority[v.kind], v.detected_on, -v.duration_days)
    ):
        start = date.fromisoformat(candidate.start_date)
        end = date.fromisoformat(candidate.end_date)
        duplicate = False
        for old in selected:
            a, b = date.fromisoformat(old.start_date), date.fromisoformat(old.end_date)
            overlap = max(0, (min(b, end) - max(a, start)).days + 1)
            if (
                overlap / max(1, max((b - a).days + 1, (end - start).days + 1)) > 0.65
                and abs((end - b).days) < 42
            ):
                duplicate = True
                break
        if not duplicate:
            selected.append(candidate)
    return sorted(selected, key=lambda v: (v.detected_on, v.kind), reverse=True)
