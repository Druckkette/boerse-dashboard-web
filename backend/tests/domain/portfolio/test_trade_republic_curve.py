from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from app.repositories import portfolio as portfolio_repository
from app.services import portfolio as portfolio_service
from app.services.fx import FxRate


@dataclass(frozen=True)
class PriceRow:
    date: date
    close: float


@pytest.fixture(autouse=True)
def fixed_fx_rate(monkeypatch) -> None:
    monkeypatch.setattr(
        portfolio_service,
        "get_eur_usd_rate",
        lambda: FxRate(pair="EUR/USD", rate=1.0, as_of=date(2026, 1, 1), source="test"),
    )


def test_trade_republic_curve_uses_saved_transactions(monkeypatch) -> None:
    transactions = [
        portfolio_repository.TradeRepublicStoredTransactionRow(
            ticker="",
            date=date(2025, 1, 1),
            transaction_type="customer_inbound",
            shares=0,
            price=None,
            net_amount=10000,
            currency="EUR",
            raw_json={"source": "trade_republic_transactions"},
        ),
        portfolio_repository.TradeRepublicStoredTransactionRow(
            ticker="NVDA",
            date=date(2025, 1, 2),
            transaction_type="buy",
            shares=10,
            price=100,
            net_amount=-1000,
            currency="USD",
            raw_json={"source": "trade_republic_transactions", "isin": "US67066G1040"},
        ),
    ]

    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: transactions)
    monkeypatch.setattr(
        portfolio_service.prices_repository,
        "list_price_bars",
        lambda ticker, start_date=None: {
            "NVDA": [
                PriceRow(date=date(2025, 1, 2), close=100),
                PriceRow(date=date(2025, 1, 3), close=110),
            ],
            "^GSPC": [
                PriceRow(date=date(2025, 1, 2), close=5000),
                PriceRow(date=date(2025, 1, 3), close=5050),
            ],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500)

    assert curve.source == "trade_republic_transactions"
    assert curve.points
    assert curve.points[-1].depot_value >= 10100
    assert curve.points[-1].portfolio_index > 100
    assert curve.points[-1].sp500_index is not None
    assert curve.points[-1].sp500_index > 100


def test_trade_republic_curve_keeps_dividends_as_performance_and_neutralizes_deposits(monkeypatch) -> None:
    transactions = [
        _tr_row(date(2025, 1, 2), "customer_inbound", 0, None, 1000),
        _tr_row(date(2025, 1, 2), "buy", 10, 100, -1000, ticker="NVDA", isin="US67066G1040"),
        _tr_row(date(2025, 1, 3), "dividend", 0, None, 6, ticker="NVDA", isin="US67066G1040"),
        _tr_row(date(2025, 1, 6), "customer_inbound", 0, None, 100),
    ]

    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: transactions)
    monkeypatch.setattr(
        portfolio_service.prices_repository,
        "list_price_bars",
        lambda ticker, start_date=None: {
            "NVDA": [
                PriceRow(date=date(2025, 1, 2), close=100),
                PriceRow(date=date(2025, 1, 3), close=100),
                PriceRow(date=date(2025, 1, 6), close=100),
            ],
            "^GSPC": [
                PriceRow(date=date(2025, 1, 2), close=5000),
                PriceRow(date=date(2025, 1, 3), close=5000),
                PriceRow(date=date(2025, 1, 6), close=5000),
            ],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500)
    by_date = {point.date: point for point in curve.points}

    assert by_date["2025-01-03"].cash == 6
    assert by_date["2025-01-03"].portfolio_index == pytest.approx(100.6)
    assert by_date["2025-01-06"].cash == 106
    assert by_date["2025-01-06"].portfolio_index == pytest.approx(100.6)


def test_trade_republic_curve_values_derivatives_from_trade_prices_without_ticker(monkeypatch) -> None:
    transactions = [
        _tr_row(date(2025, 2, 3), "customer_inbound", 0, None, 100),
        _tr_row(
            date(2025, 2, 3),
            "buy",
            5,
            20,
            -100,
            isin="DE000DERIV01",
            asset_class="DERIVATIVE",
            name="Long Factor",
        ),
        _tr_row(
            date(2025, 2, 4),
            "warrant_exercise",
            0,
            None,
            110,
            isin="DE000DERIV01",
            asset_class="DERIVATIVE",
            name="Long Factor",
        ),
    ]

    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: transactions)
    monkeypatch.setattr(
        portfolio_service.prices_repository,
        "list_price_bars",
        lambda ticker, start_date=None: {
            "^GSPC": [
                PriceRow(date=date(2025, 2, 3), close=5000),
                PriceRow(date=date(2025, 2, 4), close=5000),
            ],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500)
    by_date = {point.date: point for point in curve.points}

    assert by_date["2025-02-03"].positions_value == 100
    assert by_date["2025-02-04"].positions_value == 0
    assert by_date["2025-02-04"].cash == 110
    assert by_date["2025-02-04"].portfolio_index == pytest.approx(110)
    assert "DE000DERIV01" in curve.message


def test_portfolio_curve_falls_back_to_missing_response_when_tr_curve_fails(monkeypatch) -> None:
    def broken_transactions():
        raise RuntimeError("malformed stored TR transaction")

    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", broken_transactions)
    monkeypatch.setattr(portfolio_repository, "list_open_positions", lambda: [])
    monkeypatch.setattr(portfolio_repository, "get_cash_balance", lambda: 0.0)

    curve = portfolio_service.get_portfolio_curve(days=370)

    assert curve.source == "missing"
    assert curve.data_status == "missing"
    assert curve.points == []
    assert "TR-Kurve" in curve.message


def _tr_row(
    day: date,
    transaction_type: str,
    shares: float,
    price: float | None,
    net_amount: float,
    *,
    ticker: str = "",
    isin: str = "",
    asset_class: str = "STOCK",
    name: str = "",
) -> portfolio_repository.TradeRepublicStoredTransactionRow:
    return portfolio_repository.TradeRepublicStoredTransactionRow(
        ticker=ticker,
        date=day,
        transaction_type=transaction_type,
        shares=shares,
        price=price,
        net_amount=net_amount,
        currency="EUR",
        raw_json={
            "source": "trade_republic_transactions",
            "isin": isin,
            "asset_class": asset_class,
            "name": name,
            "event_ts": f"{day.isoformat()}T10:00:00Z",
        },
        isin=isin,
        asset_class=asset_class,
        name=name,
    )
