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
    assert payload["source"] in {"database", "synthetic_fixture", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert payload["phase_label"]
    assert payload["trend_ampel"] is None or {"ticker", "phase", "phase_label", "as_of"}.issubset(
        payload["trend_ampel"]
    )
    assert isinstance(payload["kpis"], list)


def test_market_breadth_contract() -> None:
    response = client.get("/api/v1/market/breadth")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "synthetic_fixture", "missing"}
    assert payload["data_status"] in {"fresh", "stale", "missing", "fallback"}
    assert isinstance(payload["coverage_ratio"], int | float)
    assert isinstance(payload["points"], list)
    if payload["points"]:
        assert {"date", "advancers", "decliners", "pct_above_50sma"}.issubset(payload["points"][0])


def test_market_volatility_contract() -> None:
    response = client.get("/api/v1/market/volatility")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert payload["regime"]
    assert isinstance(payload["status_cards"], list)
    assert isinstance(payload["points"], list)


def test_stock_price_history_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/prices?range=3m")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "NVDA"
    assert payload["range"] == "3m"
    assert payload["points"]
    assert {"date", "close"}.issubset(payload["points"][0])


def test_rs_ranking_contract() -> None:
    response = client.get("/api/v1/stocks/ratings/rs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert isinstance(payload["rows"], list)
    if payload["rows"]:
        assert {"ticker", "rating", "percentile", "date"}.issubset(payload["rows"][0])


def test_stock_rs_detail_contract() -> None:
    response = client.get("/api/v1/stocks/NVDA/rs")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] in {"database", "missing"}
    assert isinstance(payload["found"], bool)


def test_portfolio_import_dry_run_contract() -> None:
    response = client.post(
        "/api/v1/portfolio/imports/positions",
        json={
            "file_name": "positions.csv",
            "content": "Ticker,Shares,Entry_Price\nNVDA,12,91.2\n",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["positions"][0]["ticker"] == "NVDA"


def test_sell_metrics_contract() -> None:
    response = client.get("/api/v1/sell/PLTR/metrics")
    assert response.status_code == 200
    assert response.json()["ticker"] == "PLTR"
