from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.repositories import portfolio as portfolio_repository
from app.services import portfolio as portfolio_service


@dataclass(frozen=True)
class PriceRow:
    date: date
    close: float


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
