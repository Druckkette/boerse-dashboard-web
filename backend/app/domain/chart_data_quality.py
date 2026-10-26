"""Separate cached prices into trustworthy, contiguous chart-analysis sections.

No price is repaired, rounded or inferred. A large movement is a boundary for
analysis, not evidence that the provider's observation is incorrect.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import groupby
from math import isfinite

from app.domain.chart_patterns import Bar


MIN_SEGMENT_BARS = 25
MAX_GAP_DAYS = 10
MAX_CHANGE_FRACTION = 0.60


@dataclass(frozen=True)
class QualityResult:
    segments: list[list[Bar]]
    issues: list[dict]
    excluded_bar_count: int
    boundary_count: int
    short_segment_count: int
    short_segment_bar_count: int

    @property
    def analysed(self) -> bool:
        return bool(self.segments)

    @property
    def partial(self) -> bool:
        return self.analysed and bool(
            self.excluded_bar_count or self.boundary_count or self.short_segment_count
        )

    @property
    def analysed_bar_count(self) -> int:
        return sum(len(segment) for segment in self.segments)


def _valid_price(value) -> bool:
    try:
        return isfinite(value) and value > 0
    except (TypeError, ValueError):
        return False


def _valid_ohlc(bar: Bar) -> bool:
    return all(_valid_price(value) for value in (bar.open, bar.high, bar.low, bar.close)) and (
        bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
    )


def _valid_volume(value) -> bool:
    if value is None:
        return True
    try:
        return isfinite(value) and value >= 0
    except (TypeError, ValueError):
        return False


def _signature(bar: Bar) -> tuple:
    # NaN must compare consistently when describing otherwise identical
    # duplicate observations. These values are never used to repair prices.
    values = []
    for value in (bar.open, bar.high, bar.low, bar.close, bar.volume):
        if value is None:
            values.append(None)
            continue
        try:
            values.append(value if isfinite(value) else str(value))
        except (TypeError, ValueError):
            values.append(repr(value))
    return tuple(values)


def prepare_segments(bars: Sequence[Bar], *, incomplete_dates: Collection[date] = ()) -> QualityResult:
    """Return every clean section with at least 25 observations, in date order.

    All rows sharing a date are excluded, even if identical. Invalid rows end
    the current section; gaps and extreme changes retain both observations on
    separate sides. ``boundary_count`` counts cuts between nonempty clean
    sections, including sections later omitted for being too short. Excluded
    raw rows and clean short-section rows are counted separately.
    """
    if not bars:
        return QualityResult(
            segments=[],
            issues=[
                {
                    "code": "missing_history",
                    "date": None,
                    "reason": "Keine abgeschlossenen Kursdaten im Prüfzeitraum vorhanden.",
                }
            ],
            excluded_bar_count=0,
            boundary_count=0,
            short_segment_count=0,
            short_segment_bar_count=0,
        )

    sections: list[list[Bar]] = []
    current: list[Bar] = []
    issues: list[dict] = []
    excluded = 0

    def finish_section() -> None:
        nonlocal current
        if current:
            sections.append(current)
            current = []

    for day, observations in groupby(sorted(bars, key=lambda bar: bar.date), lambda bar: bar.date):
        group = list(observations)
        day_text = day.isoformat()
        duplicate = len(group) > 1
        invalid_ohlc = sum(not _valid_ohlc(bar) for bar in group)
        invalid_volume = sum(not _valid_volume(bar.volume) for bar in group)
        incomplete = day in incomplete_dates
        if incomplete:
            issues.append(
                {
                    "code": "incomplete_session",
                    "date": day_text,
                    "reason": f"Der Tageskurs vom {day_text} wurde vor Börsenschluss geladen "
                    "oder sein Ladezeitpunkt fehlt. Ein Neuabruf nach Börsenschluss "
                    "ist für die Musteranalyse erforderlich.",
                }
            )
        if duplicate:
            conflicting = len({_signature(bar) for bar in group}) > 1
            issues.append(
                {
                    "code": "duplicate_date",
                    "date": day_text,
                    "reason": f"Mehrere {'widersprüchliche' if conflicting else 'gleiche'} Kurseinträge "
                    f"am {day_text}; sämtliche Einträge dieses Datums ausgeschlossen.",
                    "bar_count": len(group),
                    "conflicting": conflicting,
                }
            )
        if invalid_ohlc:
            issues.append(
                {
                    "code": "invalid_ohlc",
                    "date": day_text,
                    "reason": f"Ungültige OHLC-Daten am {day_text}: Preise fehlen, sind nicht endlich "
                    "oder positiv, oder Eröffnung/Schlusskurs liegen außerhalb der Tagesspanne.",
                    "bar_count": invalid_ohlc,
                }
            )
        if invalid_volume:
            issues.append(
                {
                    "code": "invalid_volume",
                    "date": day_text,
                    "reason": f"Ungültiges Volumen am {day_text}: negativer oder nicht endlicher Wert.",
                    "bar_count": invalid_volume,
                }
            )
        if duplicate or invalid_ohlc or invalid_volume or incomplete:
            excluded += len(group)
            finish_section()
            continue

        bar = group[0]
        if current:
            previous = current[-1]
            gap_days = (day - previous.date).days
            # Difference versus the previous close avoids classifying an exact
            # 100 -> 160 movement as >60% through division round-off.
            extreme = abs(bar.close - previous.close) > previous.close * MAX_CHANGE_FRACTION
            if gap_days > MAX_GAP_DAYS:
                issues.append(
                    {
                        "code": "gap",
                        "date": day_text,
                        "previous_date": previous.date.isoformat(),
                        "gap_days": gap_days,
                        "reason": f"Kurslücke von {gap_days} Kalendertagen bis {day_text}; "
                        "die Abschnitte werden getrennt geprüft.",
                    }
                )
            if extreme:
                change_pct = (bar.close / previous.close - 1) * 100
                issues.append(
                    {
                        "code": "extreme_jump",
                        "date": day_text,
                        "previous_date": previous.date.isoformat(),
                        "change_pct": round(change_pct, 6) if isfinite(change_pct) else None,
                        "reason": f"Kursänderung über 60 % bis {day_text}; die Abschnitte werden "
                        "getrennt geprüft. Ursache nicht verifiziert; kein Nachweis eines Datenfehlers.",
                    }
                )
            if gap_days > MAX_GAP_DAYS or extreme:
                finish_section()
        current.append(bar)
    finish_section()

    segments = []
    short_count = short_bars = 0
    for section in sections:
        if len(section) >= MIN_SEGMENT_BARS:
            segments.append(section)
        else:
            short_count += 1
            short_bars += len(section)
            issues.append(
                {
                    "code": "insufficient_history",
                    "date": section[-1].date.isoformat(),
                    "from_date": section[0].date.isoformat(),
                    "to_date": section[-1].date.isoformat(),
                    "bar_count": len(section),
                    "minimum_bar_count": MIN_SEGMENT_BARS,
                    "reason": f"Abschnitt vom {section[0].date} bis {section[-1].date} enthält "
                    f"nur {len(section)} abgeschlossene Handelstage; mindestens 25 erforderlich.",
                }
            )
    return QualityResult(
        segments=segments,
        issues=sorted(issues, key=lambda issue: (issue["date"] or "", issue["code"])),
        excluded_bar_count=excluded,
        boundary_count=max(0, len(sections) - 1),
        short_segment_count=short_count,
        short_segment_bar_count=short_bars,
    )
