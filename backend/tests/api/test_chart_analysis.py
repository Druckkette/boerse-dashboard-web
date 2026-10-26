from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.v1.chart_analysis import router
from app.domain.chart_patterns import ALGORITHM_VERSION, PatternParameters
from app.repositories.settings import SettingsRepositoryUnavailable
from app.services import chart_analysis as service
from tests.helpers.chart_pattern_data import historical_bars, historical_cases


@pytest.fixture
def client(monkeypatch):
    store = {}
    monkeypatch.setattr(
        service.repository, "_read_json_setting", lambda key: deepcopy(store.get(key, {}))
    )
    monkeypatch.setattr(
        service.repository,
        "_write_json_setting",
        lambda key, value, **kw: store.update({key: deepcopy(value)}) or value,
    )
    bars = historical_bars(historical_cases()[0])
    monkeypatch.setattr(
        service, "list_price_bars", lambda *a, **kw: [SimpleNamespace(**b.__dict__) for b in bars]
    )
    monkeypatch.setattr(
        service,
        "completed_ticker_market_session",
        lambda ticker: SimpleNamespace(date=date(2025, 7, 15)),
    )
    app = FastAPI()
    app.include_router(router, prefix="/chart-analysis")
    with TestClient(app) as result:
        yield result, store


def test_config_validation_and_saved_rules_invalidate_old_scan(client):
    http, store = client
    initial = http.get("/chart-analysis/config").json()
    store[service.RESULT_KEY] = {"parameter_hash": initial["parameter_hash"], "algorithm_version": ALGORITHM_VERSION, "patterns": []}
    assert not http.get("/chart-analysis/results").json()["obsolete"]
    values = {**initial["parameters"], "cup_max_depth_pct": 40}
    assert http.put("/chart-analysis/config", json=values).status_code == 200
    assert http.get("/chart-analysis/config").json()["parameters"]["cup_max_depth_pct"] == 40
    assert http.get("/chart-analysis/results").json()["obsolete"]
    assert (
        http.put("/chart-analysis/config", json={**values, "cup_max_depth_pct": 51}).status_code
        == 422
    )
    assert http.get("/chart-analysis/config").json()["parameters"]["cup_max_depth_pct"] == 40


def test_historical_as_of_excludes_later_data_and_future_dates(client):
    http, _ = client
    before = http.get("/chart-analysis/ibkr?as_of=2025-05-01").json()
    assert all(p["date"] <= "2025-05-01" for p in before["points"])
    assert not any(
        p["kind"] == "cup_with_handle" and p["start_date"] >= "2025-02-01"
        for p in before["patterns"]
    )
    now = http.get("/chart-analysis/ibkr?as_of=2099-12-31").json()
    assert now["as_of"] == "2025-07-15"
    assert any(p["kind"] == "cup_with_handle" for p in now["patterns"])


def test_results_filter_and_pagination(client):
    http, store = client
    chart = http.get("/chart-analysis/IBKR").json()
    store[service.RESULT_KEY] = {
        "parameter_hash": PatternParameters().fingerprint,
        "patterns": chart["patterns"],
    }
    result = http.get("/chart-analysis/results?kind=cup_with_handle&search=ibkr&limit=1").json()
    assert result["total"] == 1
    assert result["rows"][0]["kind"] == "cup_with_handle"
    assert http.get("/chart-analysis/results?kind=invalid").status_code == 422
    assert http.get("/chart-analysis/results?limit=501").status_code == 422


def test_database_failure_is_explicit_503(client, monkeypatch):
    http, _ = client

    def unavailable(key):
        raise SettingsRepositoryUnavailable("test")

    monkeypatch.setattr(service.repository, "_read_json_setting", unavailable)
    assert http.get("/chart-analysis/config").status_code == 503
    assert http.get("/chart-analysis/IBKR").status_code == 503


def test_nonfinite_quotes_return_diagnostics_and_json_null(client, monkeypatch):
    http, _ = client
    bars = historical_bars(historical_cases()[0])
    rows = [SimpleNamespace(**b.__dict__) for b in bars]
    rows[0].high = float("nan")
    monkeypatch.setattr(service, "list_price_bars", lambda *a, **kw: rows)
    result = http.get("/chart-analysis/IBKR")
    assert result.status_code == 200
    assert result.json()["points"][0]["high"] is None
    assert result.json()["diagnostics"]
    assert result.json()["quality"]["partial"]
    assert result.json()["quality"]["excluded_bar_count"] == 1
    assert all(p["start_date"] > rows[0].date.isoformat() for p in result.json()["patterns"])
