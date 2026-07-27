from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_pushover_delivery_log_contract(monkeypatch) -> None:
    from app.api.v1 import insights as insights_api

    monkeypatch.setattr(
        insights_api.settings_repository,
        "read_pushover_delivery_log",
        lambda: [
            {
                "timestamp": "2026-07-24T12:30:00Z",
                "ticker": "NVDA",
                "status": "sent",
                "detail": "Pushover hat den Alarm bestätigt.",
                "distance_atr": 1.8,
                "threshold_atr": 1.5,
                "reference_label": "Vortagesschluss",
            }
        ],
    )

    response = client.get("/api/v1/insights/notifications")

    assert response.status_code == 200
    assert response.json()["entries"][0]["ticker"] == "NVDA"
    assert response.json()["entries"][0]["status"] == "sent"
