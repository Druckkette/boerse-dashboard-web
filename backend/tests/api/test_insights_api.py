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


def test_delivery_log_explains_held_notifications_and_preserves_message(monkeypatch):
    from app.api.v1 import insights as api
    monkeypatch.setattr(api.settings_repository, "read_pushover_delivery_log", lambda: [{
        "timestamp": "2026-10-29T12:00:00Z", "ticker": "NOW", "status": "queued",
        "detail": "Folgemeldungen werden gesammelt.", "kind": "stock_signal",
        "message": "ServiceNow ist unter die 50-Tage-Linie gefallen.",
        "title": "ServiceNow: Trend verschlechtert", "priority": 0,
    }])
    response = client.get("/api/v1/insights/notifications")
    assert response.status_code == 200
    item = response.json()["entries"][0]
    assert item["status"] == "queued" and item["kind"] == "stock_signal"
    assert item["message"].startswith("ServiceNow")


def test_atr_rearm_is_explicit_and_normalizes_ticker(monkeypatch):
    from app.api.v1 import insights as api
    calls = []
    def rearm(ticker):
        calls.append(ticker)
        return {"ok": True, "ticker": ticker, "count": 1}
    monkeypatch.setattr(api.settings_repository, "request_atr_rearm", rearm)
    assert client.get("/api/v1/insights/notifications").status_code == 200
    assert calls == []
    response = client.post("/api/v1/insights/notifications/atr/now/rearm")
    assert response.status_code == 200 and response.json()["ticker"] == "NOW"
    assert calls == ["NOW"]


def test_notification_rearm_rejects_invalid_ticker():
    assert client.post("/api/v1/insights/notifications/atr/invalid%20symbol/rearm").status_code == 422
