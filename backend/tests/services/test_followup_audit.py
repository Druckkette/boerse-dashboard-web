from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import portfolio as repository
from app.services import portfolio_analysis


def test_optional_dates_and_valid_leap_date_keep_their_meaning():
    from app.schemas import PortfolioSellRequest
    assert PortfolioSellRequest(shares=1, price=10, date="2024-02-29").date == "2024-02-29"
    assert PortfolioSellRequest(shares=1, price=10).date is None
    assert PortfolioSellRequest(shares=1, price=10, date="").date is None


@pytest.mark.parametrize("endpoint,payload", [
    ("/positions", {"ticker": "TEST", "shares": 1, "entry_price": 100, "buy_date": "2026-02-30"}),
    ("/positions", {"ticker": "TEST", "shares": 1, "entry_price": 100, "pivot_tag": "invalid"}),
    ("/positions/TEST/sell", {"shares": 1, "price": 100, "date": "2026-02-30"}),
    ("/cash-flows", {"amount": 100, "flow_type": "deposit", "date": "invalid"}),
])
def test_invalid_booking_dates_never_reach_persistence(monkeypatch, endpoint, payload):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid date reached persistence")
    for name in ("upsert_position", "sell_position", "add_cash_flow"):
        monkeypatch.setattr(repository, name, unexpected)
    response = TestClient(create_app()).post("/api/v1/portfolio" + endpoint, json=payload)
    assert response.status_code == 422


def test_fee_and_tax_are_expenses_in_performance_attribution():
    bars = [SimpleNamespace(date=date(2026, 10, day), close=100) for day in (1, 2)]
    book = portfolio_analysis.PriceBook({"TEST": bars}, {"TEST": "USD"})
    ledger = {"events": [dict(id="buy", ticker="TEST", date=date(2026, 10, 1),
        kind="buy", shares=1, net=-100, currency="USD")], "cash_flows": [
        dict(date=date(2026, 10, 1), amount=200, currency="USD", kind="deposit"),
        dict(date=date(2026, 10, 2), amount=10, currency="USD", kind="fee"),
        dict(date=date(2026, 10, 2), amount=5, currency="USD", kind="tax"),
        dict(date=date(2026, 10, 2), amount=50, currency="USD", kind="deposit"),
    ]}
    result = portfolio_analysis.attribution(ledger, book, start=date(2026, 10, 1),
        end=date(2026, 10, 2), base="USD", positions=[SimpleNamespace(ticker="TEST", shares=1)])
    assert result["opening_cash_value"] == 100
    assert result["ending_cash_value"] == 135
    assert result["external_cash_flow"] == 50
    assert result["other_cash_result"] == -15
    assert result["result"] == -15


def test_cash_booking_invalidates_home_and_analysis(monkeypatch):
    from app.api.v1 import portfolio as api
    from app.schemas import PortfolioCashFlowResponse, PortfolioCashFlow
    invalidations = []
    monkeypatch.setattr(api, "invalidate_home_dashboard_cache", lambda: invalidations.append(True))
    monkeypatch.setattr(api, "create_portfolio_cash_flow", lambda payload: PortfolioCashFlowResponse(
        cash_flow=PortfolioCashFlow(id="test", date="2026-10-21", amount=100, flow_type="deposit"), cash_balance=100))
    response = TestClient(create_app()).post("/api/v1/portfolio/cash-flows", json={"amount": 100, "flow_type": "deposit"})
    assert response.status_code == 200 and invalidations == [True]


@pytest.mark.parametrize("endpoint,method", [
    ("transactions", "list_transactions"), ("cash-flows", "list_cash_flows"), ("imports", "list_import_history"),
])
def test_database_outage_is_not_an_empty_financial_history(monkeypatch, endpoint, method):
    def unavailable(**kwargs):
        raise repository.PortfolioRepositoryUnavailable("synthetic database outage")
    monkeypatch.setattr(repository, method, unavailable)
    response = TestClient(create_app()).get("/api/v1/portfolio/" + endpoint)
    assert response.status_code == 503
    assert "synthetic" not in response.text
