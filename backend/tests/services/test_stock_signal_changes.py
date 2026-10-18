from dataclasses import replace

import pytest

from app.domain.stocks.assessment import (
    AssessmentCheck,
    ChartSignal,
    ChartSignalState,
    compute_stock_assessment,
)
from app.services.stocks import _assessment_changes


def assessment(**kwargs):
    return replace(compute_stock_assessment("TSLA", []), **kwargs)


def test_tsla_lost_strength_and_sma50_crossing_are_all_deteriorations():
    previous = assessment(
        checks=[AssessmentCheck("trend", "Kurs über 50-SMA", True, "362.44 vs 358.76")],
        chart_signals=[
            ChartSignal("positive", "Leben über den Durchschnitten", "28T über 50-SMA"),
            ChartSignal("positive", "Positive Kurslücken", "1 in 10T, Schluss obere Hälfte"),
        ],
    )
    current = assessment(
        checks=[AssessmentCheck("trend", "Kurs über 50-SMA", False, "354.72 vs 359.46")],
    )
    changes = _assessment_changes(current, previous)
    assert len(changes) == 3
    assert all(change.effect == "deterioration" for change in changes)
    assert changes[0].source == "rule"
    assert changes[0].detail == "Vorher: 362.44 vs 358.76 · Aktuell: 354.72 vs 359.46"
    assert all(change.source == "chart_signal" for change in changes[1:])
    assert changes[1].detail.startswith("Vorher: 28T über 50-SMA · Aktuell:")


@pytest.mark.parametrize("category,appears,effect", [
    ("positive", True, "improvement"),
    ("positive", False, "deterioration"),
    ("negative", True, "deterioration"),
    ("negative", False, "improvement"),
    ("neutral", True, "neutral"),
    ("neutral", False, "neutral"),
])
def test_chart_signal_direction(category, appears, effect):
    active = assessment(chart_signals=[ChartSignal(category, "Signal", "Details")])
    inactive = assessment()
    current, previous = (active, inactive) if appears else (inactive, active)
    changes = _assessment_changes(current, previous)
    assert len(changes) == 1
    assert changes[0].kind == ("new" if appears else "resolved")
    assert changes[0].effect == effect
    assert changes[0].source == "chart_signal"


@pytest.mark.parametrize("passed,effect", [(True, "improvement"), (False, "deterioration")])
def test_rule_direction(passed, effect):
    current = assessment(checks=[AssessmentCheck("risk", "Abstand 50-SMA (<25%)", passed, "neu")])
    previous = assessment(checks=[AssessmentCheck("risk", "Abstand 50-SMA (<25%)", not passed, "alt")])
    changes = _assessment_changes(current, previous)
    assert len(changes) == 1
    assert changes[0].effect == effect
    assert changes[0].source == "rule"


@pytest.mark.parametrize("category", ["positive", "negative", "neutral"])
def test_missing_signal_data_is_not_a_confirmed_disappearance(category):
    previous = assessment(chart_signals=[ChartSignal(category, "Signal", "alt")])
    current = assessment(chart_signal_states={"Signal": ChartSignalState(False, False, "Daten fehlen")})
    assert _assessment_changes(current, previous) == []


def test_unchanged_signals_and_rules_do_not_create_events():
    result = assessment(
        checks=[AssessmentCheck("trend", "Kurs über 50-SMA", True, "362.44 vs 358.76")],
        chart_signals=[ChartSignal("positive", "Positive Kurslücken")],
    )
    assert _assessment_changes(result, result) == []
