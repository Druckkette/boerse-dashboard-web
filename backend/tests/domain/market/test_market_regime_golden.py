from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.market.regime import MarketRegimeInput, classify_market_regime


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "market"


@pytest.mark.parametrize("fixture_path", sorted(FIXTURE_DIR.glob("*.json")), ids=lambda path: path.stem)
def test_market_regime_golden_master(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    result = classify_market_regime(MarketRegimeInput(**fixture["input"]))
    expected = fixture["expected"]

    assert result.phase == expected["phase"]
    assert result.breadth_mode == expected["breadth_mode"]
    assert result.warning_count == expected["warning_count"]
    assert expected["action_contains"] in result.action
    assert [item["label"] for item in result.kpis] == expected["kpi_labels"]
    assert result.metrics["action"] == result.action
    assert result.metrics["volatility"] == fixture["input"]["volatility_summary"]


def test_missing_breadth_is_neutral_instead_of_a_synthetic_bearish_signal() -> None:
    result = classify_market_regime(
        MarketRegimeInput(
            pct_above_20sma=None,
            pct_above_50sma=None,
            pct_above_200sma=None,
            mcclellan=0.0,
            advancers=0,
            decliners=0,
            new_highs=0,
            new_lows=0,
            coverage_ratio=0.0,
            universe_size=5000,
            covered_count=0,
        )
    )

    assert result.phase == "neutral"
    assert result.warning_count == 1
