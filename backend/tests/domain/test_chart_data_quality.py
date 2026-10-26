"""Adversarial continuity checks for partial chart histories."""

from dataclasses import replace
from datetime import timedelta

import pytest

from app.domain.chart_data_quality import prepare_segments
from app.domain.chart_patterns import detect_patterns, validate_bars
from tests.domain.test_chart_patterns import fixture, series


def test_clean_reference_and_missing_history():
    bars = fixture()
    quality = prepare_segments(bars)
    assert quality.segments == [bars]
    assert not quality.partial and not quality.issues
    assert prepare_segments([]).issues[0]["code"] == "missing_history"
    assert not prepare_segments(series([100] * 24)).analysed
    assert prepare_segments(series([100] * 25)).analysed


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("open", 0, "invalid_ohlc"),
        ("high", float("nan"), "invalid_ohlc"),
        ("low", 1000, "invalid_ohlc"),
        ("close", float("inf"), "invalid_ohlc"),
        ("volume", -1, "invalid_volume"),
        ("volume", float("nan"), "invalid_volume"),
    ],
)
def test_bad_bar_splits_without_connecting_its_neighbours(field, value, code):
    bars = series([100] * 101)
    bars[50] = replace(bars[50], **{field: value})
    quality = prepare_segments(bars)
    assert [len(s) for s in quality.segments] == [50, 50]
    assert quality.partial and quality.boundary_count == 1
    assert quality.excluded_bar_count == 1
    assert quality.issues[0]["code"] == code
    assert all(not validate_bars(s) for s in quality.segments)


def test_duplicates_are_all_removed_and_order_is_deterministic():
    bars = series([100] * 101)
    for duplicate in [bars[50], replace(bars[50], close=100.1)]:
        q = prepare_segments(list(reversed(bars + [duplicate])))
        assert [len(s) for s in q.segments] == [50, 50]
        assert q.excluded_bar_count == 2
        assert q.issues[0]["code"] == "duplicate_date"


def test_gap_and_jump_preserve_both_sides_as_separate_sections():
    bars = series([100] * 50 + [200] * 50)
    q = prepare_segments(bars)
    assert [len(s) for s in q.segments] == [50, 50]
    assert q.excluded_bar_count == 0 and q.boundary_count == 1
    assert q.issues[0]["code"] == "extreme_jump"
    assert "kein Nachweis" in q.issues[0]["reason"]
    shifted = bars[:50] + [replace(b, date=b.date + timedelta(days=28)) for b in bars[50:]]
    q = prepare_segments(shifted)
    assert {i["code"] for i in q.issues} == {"gap", "extreme_jump"}
    assert q.boundary_count == 1


def test_exact_sixty_percent_is_not_a_suspected_jump():
    q = prepare_segments(series([100] * 25 + [160] * 25))
    assert not q.issues
    assert not validate_bars(q.segments[0])


def test_short_sections_never_become_one_artificial_long_section():
    bars = series([100] * 20 + [200] * 20 + [400] * 20)
    q = prepare_segments(bars)
    assert not q.analysed and q.short_segment_count == 3
    assert q.short_segment_bar_count == 60


def test_cup_cannot_cross_a_corrupt_bottom_but_clean_cup_is_retained():
    bars = fixture()
    assert any(p.kind == "cup_with_handle" for p in detect_patterns("TEST", bars))
    bad_index = 92
    bars[bad_index] = replace(bars[bad_index], high=float("nan"))
    q = prepare_segments(bars)
    found = [p for s in q.segments for p in detect_patterns("TEST", s)]
    assert not any(p.start_date < bars[bad_index].date.isoformat() < p.end_date for p in found)
    assert not any(p.kind == "cup_with_handle" for p in found)


def test_later_error_does_not_change_historical_pattern_geometry():
    bars = fixture()
    bad_day = bars[-1].date + timedelta(days=3)
    broken = replace(bars[-1], date=bad_day, high=0)
    q = prepare_segments(bars + [broken])
    assert [p.model_dump() for p in detect_patterns("TEST", q.segments[0])] == [
        p.model_dump() for p in detect_patterns("TEST", bars)
    ]


def test_missing_volume_is_usable_and_all_issues_are_retained():
    q = prepare_segments([replace(b, volume=None) for b in series([100] * 50)])
    assert q.analysed and not q.issues
    bars = series([100] * 101)
    bars[20] = replace(bars[20], high=0, volume=-1)
    bars[60] = replace(bars[60], low=1000)
    q = prepare_segments(bars)
    assert len([i for i in q.issues if i["code"] == "invalid_ohlc"]) == 2
    assert len([i for i in q.issues if i["code"] == "invalid_volume"]) == 1
    assert q.excluded_bar_count == 2
