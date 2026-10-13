from types import SimpleNamespace

import pytest

from app.domain.market.regime import market_recommendation
from app.services.market import _overview_action


@pytest.mark.parametrize("phase", ["rot", "gruen", "aufwaertstrend", "gelb_startschuss", "gelb_rally_unter_druck", "gelb_trend_unter_druck", "neutral"])
@pytest.mark.parametrize("context", [(0,"rueckenwind","Ruhig","on"), (14,"schutz","Risk Off bestätigt","under_pressure"), (8,"wachsam","Fragile Rally","off")])
def test_context_neither_downgrades_nor_promotes_the_trend_phase(phase, context):
    assert market_recommendation(phase, *context) == market_recommendation(phase, 0, "rueckenwind", "Ruhig", "off")


@pytest.mark.parametrize("powertrend", ["on", "under_pressure", "off"])
@pytest.mark.parametrize("phase, vol", [("rot", "Ruhig"), ("rot", "Risk Off bestätigt"), ("rot", "Stress")])
def test_powertrend_cannot_override_hard_risk(phase, vol, powertrend):
    assert market_recommendation(phase, 0, "rueckenwind", vol, powertrend)[:2] == ("Defensiv", "bad")


@pytest.mark.parametrize("breadth, vol, powertrend", [
    ("schutz", "Ruhig", "on"),
    ("rueckenwind", "Kurzer Volatilitätsschock", "on"),
    ("rueckenwind", "Fragile Rally", "on"),
    ("rueckenwind", "Ruhig", "under_pressure"),
])
def test_context_remains_informational(breadth, vol, powertrend):
    assert market_recommendation("gruen", 0, breadth, vol, powertrend)[:2] == ("Frühe Bestätigung", "good")


@pytest.mark.parametrize("phase", ["neutral", "gelb_startschuss", "gelb_rally_unter_druck", "gelb_trend_unter_druck"])
def test_powertrend_cannot_promote_unconfirmed_or_broken_trend(phase):
    assert market_recommendation(phase, 0, "rueckenwind", "Ruhig", "on")[0] != "Offensiv"


def test_overview_replaces_old_defensive_text_even_when_phase_unchanged():
    snapshot = SimpleNamespace(ampel_phase="gruen", warning_count=5,
                               breadth_mode="rueckenwind", volatility_regime="Ruhig")
    trend = SimpleNamespace(logic="ibd", powertrend_state="on")
    action = _overview_action(phase="gruen", snapshot=snapshot,
                              metrics={"action": "Defensiv bleiben"}, trend_ampel=trend)
    assert "Ampel grün" in action
    assert "Defensiv bleiben" not in action
