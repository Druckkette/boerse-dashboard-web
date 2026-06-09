from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_market_overview_contract() -> None:
    response = client.get("/api/v1/market/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["phase_label"]
    assert isinstance(payload["kpis"], list)


def test_stock_price_history_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/prices?range=3m")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["range"] == "3m"
    assert payload["points"]
    assert {"date", "close"}.issubset(payload["points"][0])


def test_sell_metrics_contract() -> None:
    response = client.get("/api/v1/sell/PLTR/metrics")
    assert response.status_code == 200
    assert response.json()["ticker"] == "PLTR"
