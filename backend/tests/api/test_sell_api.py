from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.sell.service import clear_sell_engine_state
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_sell_state() -> None:
    clear_sell_engine_state()


def test_sell_ranking_endpoint_returns_actionable_rows() -> None:
    response = client.get("/api/v1/sell/positions/ranking")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["rows"]) >= 4
    assert payload["source"] in {"live", "snapshot"}
    assert "generated_at" in payload
    first = payload["rows"][0]
    assert {
        "ticker",
        "health_score",
        "recommendation_pct",
        "pending_status",
        "last_seen_date",
        "consecutive_days",
        "snoozed_until",
        "snoozed_pct",
    } <= set(first)
    assert first["status"] in {"Halten", "Beobachten", "Verkaufen"}
    assert isinstance(first["consecutive_days"], int)


def test_sell_metrics_endpoint_returns_stable_schema() -> None:
    response = client.get("/api/v1/sell/NVDA/metrics")
    assert response.status_code == 200
    payload = response.json()

    assert payload["ticker"] == "NVDA"
    assert payload["health"]["status"] == "Halten"
    assert payload["raw_payload"]["ok"] is True
    assert "ohlc_frames" not in payload["raw_payload"]


def test_sell_evaluate_endpoint_returns_signals_and_state() -> None:
    response = client.post("/api/v1/sell/PLTR/evaluate")
    assert response.status_code == 200
    payload = response.json()

    assert payload["ticker"] == "PLTR"
    assert payload["recommendation_label"] == "KOMPLETTVERKAUF"
    assert payload["sell_now_percent"] >= 75
    assert payload["next_recommendation_state"]["last_pct"] == payload["sell_now_percent"]
    assert payload["killer_signals"] or payload["tranche_signals"]
    assert payload["emergency_features"]
    assert payload["offensive_features"]
    assert payload["defensive_features"]
    assert payload["strategy"]["strategy_key"]
    assert isinstance(payload["strategy"]["recommendations"], list)


def test_sell_diagnostics_endpoint_returns_strategy_context() -> None:
    response = client.get("/api/v1/sell/PLTR/diagnostics")
    assert response.status_code == 200
    payload = response.json()

    assert payload["ticker"] == "PLTR"
    assert isinstance(payload["price_context"], list)
    assert isinstance(payload["strategy_hub"], list)
    assert isinstance(payload["post_mortem"], list)
    assert payload["next_action"]
    assert {"strategy_key", "status", "signals"} <= set(payload["strategy_hub"][0])


def test_manual_inputs_tranches_and_snooze_are_mutable_over_api() -> None:
    manual_response = client.patch(
        "/api/v1/sell/NVDA/manual",
        json={
            "ticker": "NVDA",
            "market_environment": "Bärisch",
            "industry_group_status": "Schwach",
            "personality_changed": True,
        },
    )
    assert manual_response.status_code == 200
    assert manual_response.json()["manual"]["market_environment"] == "Bärisch"

    tranche_response = client.post(
        "/api/v1/sell/NVDA/tranches",
        json={"ticker": "NVDA", "pct": 25, "reason": "API regression tranche"},
    )
    assert tranche_response.status_code == 200
    assert tranche_response.json()["tranche_log"][0]["pct"] == 25

    snooze_response = client.post("/api/v1/sell/NVDA/snooze", json={"snoozed_pct": 100, "days": 5})
    assert snooze_response.status_code == 200
    assert snooze_response.json()["state"]["snoozed_pct"] == 100

    evaluate_response = client.post("/api/v1/sell/NVDA/evaluate")
    assert evaluate_response.status_code == 200
    assert evaluate_response.json()["tranche_log"][0]["reason"] == "API regression tranche"
    assert evaluate_response.json()["manual"]["personality_changed"] is True
