"""Source comparison and real regressions; this is not a precision benchmark."""

from datetime import date

from app.domain.chart_patterns import PatternParameters, _anchors, detect_patterns
from scripts.evaluate_published_chart_examples import bars_for, cases, matching


def case(ticker):
    return next(c for c in cases() if c["ticker"] == ticker)


def test_published_ati_cup_and_causal_replay():
    source = case("ATI")
    bars = bars_for(source)
    cup = matching(source, detect_patterns("ATI", bars))[0]
    assert cup.detected_on == "2005-11-15"
    assert cup.breakout_on == "2005-11-21"
    prefix = [b for b in bars if str(b.date) <= cup.detected_on]
    replay = matching(source, detect_patterns("ATI", prefix))[0]
    assert replay.points == cup.points
    assert replay.pivot == cup.pivot


def test_published_csco_shallow_handle_can_be_enabled_by_parameter():
    source = case("CSCO")
    bars = bars_for(source)
    assert not matching(source, detect_patterns("CSCO", bars))
    parameters = PatternParameters(handle_min_depth_pct=4)
    cup = matching(source, detect_patterns("CSCO", bars, parameters))[0]
    assert cup.points[0].date == "2023-04-03"
    assert cup.detected_on == "2023-06-29"
    assert cup.breakout_on == "2023-07-19"
    prefix = [b for b in bars if str(b.date) <= cup.detected_on]
    replay = matching(source, detect_patterns("CSCO", prefix, parameters))[0]
    assert replay.points == cup.points


def test_published_w_has_separate_troughs_and_middle_peak():
    source = case("CSCO")
    bars = bars_for(source)
    indices = {str(b.date): i for i, b in enumerate(bars)}
    for pattern in detect_patterns("CSCO", bars):
        if pattern.kind == "double_bottom":
            first, middle, second = [indices[p.date] for p in pattern.points[1:4]]
            assert middle - first >= 3
            assert second - middle >= 3


def test_published_adsk_rim_precedes_a_tight_positive_week():
    bars = bars_for(case("ADSK"))
    anchors = [(bars[left].date, bars[base].date) for left, base in _anchors(bars)]
    assert (date(2009, 6, 2), date(2009, 6, 15)) in anchors
