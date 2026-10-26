"""Source cases used after the first v3 evaluation, now calibration regressions."""

from app.domain.chart_patterns import detect_patterns
from scripts.evaluate_chart_holdout_v3 import bars_for, cases, matching


def test_mktx_broad_uneven_floor_remains_a_cup_with_handle():
    source = next(c for c in cases() if c["ticker"] == "MKTX")
    bars = bars_for(source)
    found = matching(source, detect_patterns("MKTX", bars))
    assert found
    for cup in found:
        prefix = [b for b in bars if str(b.date) <= cup.detected_on]
        replay = next(p for p in detect_patterns("MKTX", prefix) if p.id == cup.id)
        assert replay.points == cup.points
        assert replay.pivot == cup.pivot


def test_66_percent_roku_whole_base_is_excluded_even_if_source_labels_it_cup():
    source = next(c for c in cases() if c["ticker"] == "ROKU")
    bars = bars_for(source)
    assert not matching(source, detect_patterns("ROKU", bars))
