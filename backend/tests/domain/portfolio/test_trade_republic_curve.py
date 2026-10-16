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
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars_for_tickers", lambda tickers, start_date=None: {ticker: portfolio_service.prices_repository.list_price_bars(ticker, start_date=start_date) for ticker in tickers})
    monkeypatch.setattr(
        portfolio_service,
        "get_eur_usd_rate",
        lambda: FxRate(pair="EUR/USD", rate=1.0, as_of=date(2026, 1, 1), source="test"),
    )


def test_historical_fx_revalues_cash_and_neutralizes_new_euro_deposits(monkeypatch) -> None:
    transactions = [
        _tr_row(date(2025, 1, 2), "customer_inbound", 0, None, 1000),
        _tr_row(date(2025, 1, 3), "customer_inbound", 0, None, 100),
    ]
    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: transactions)
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker, start_date=None: {
        "EURUSD=X": [PriceRow(date(2025, 1, 2), 1.0), PriceRow(date(2025, 1, 3), 1.2)],
        "^GSPC": [PriceRow(date(2025, 1, 2), 5000), PriceRow(date(2025, 1, 3), 5000)],
    }.get(ticker, []))
    result = portfolio_service.get_portfolio_curve(days=2500, model="execution_history")
    points = {point.date: point for point in result.points}
    assert points["2025-01-02"].cash == 1000
    assert points["2025-01-03"].cash == 1320
    assert points["2025-01-03"].portfolio_index == 120


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
            "EURUSD=X": [PriceRow(date(2025, 1, 1), 1), PriceRow(date(2025, 1, 2), 1), PriceRow(date(2025, 1, 3), 1), PriceRow(date(2025, 1, 6), 1), PriceRow(date(2025, 2, 3), 1), PriceRow(date(2025, 2, 4), 1)],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500, model="execution_history")

    assert curve.source == "trade_republic_transactions"
    assert curve.points
    assert next(point for point in curve.points if point.date == "2025-01-03").depot_value >= 10100
    assert curve.points[-1].depot_value is None
    assert next(point for point in curve.points if point.date == "2025-01-03").portfolio_index > 100
    assert next(point for point in curve.points if point.date == "2025-01-03").sp500_index is not None
    assert next(point for point in curve.points if point.date == "2025-01-03").sp500_index > 100


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
            "EURUSD=X": [PriceRow(date(2025, 1, 1), 1), PriceRow(date(2025, 1, 2), 1), PriceRow(date(2025, 1, 3), 1), PriceRow(date(2025, 1, 6), 1), PriceRow(date(2025, 2, 3), 1), PriceRow(date(2025, 2, 4), 1)],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500, model="execution_history")
    by_date = {point.date: point for point in curve.points}

    assert by_date["2025-01-03"].cash == 6
    assert by_date["2025-01-03"].portfolio_index == pytest.approx(100.6)
    assert by_date["2025-01-06"].cash == 106
    assert by_date["2025-01-06"].portfolio_index == pytest.approx(100.6)


def test_trade_republic_curve_neutralizes_security_transfers(monkeypatch) -> None:
    transactions = [
        _tr_row(date(2025, 1, 2), "customer_inbound", 0, None, 1000),
        _tr_row(date(2025, 1, 2), "buy", 10, 100, -1000, ticker="NVDA", isin="US67066G1040"),
        _tr_row(date(2025, 1, 3), "transfer_in", 10, 100, 0, ticker="NVDA", isin="US67066G1040"),
    ]

    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: transactions)
    monkeypatch.setattr(
        portfolio_service.prices_repository,
        "list_price_bars",
        lambda ticker, start_date=None: {
            "NVDA": [
                PriceRow(date=date(2025, 1, 2), close=100),
                PriceRow(date=date(2025, 1, 3), close=100),
            ],
            "^GSPC": [
                PriceRow(date=date(2025, 1, 2), close=5000),
                PriceRow(date=date(2025, 1, 3), close=5000),
            ],
            "EURUSD=X": [PriceRow(date(2025, 1, 1), 1), PriceRow(date(2025, 1, 2), 1), PriceRow(date(2025, 1, 3), 1), PriceRow(date(2025, 1, 6), 1), PriceRow(date(2025, 2, 3), 1), PriceRow(date(2025, 2, 4), 1)],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500, model="execution_history")
    by_date = {point.date: point for point in curve.points}

    assert by_date["2025-01-03"].depot_value == 2000
    assert by_date["2025-01-03"].portfolio_index == pytest.approx(100)


def test_trade_republic_curve_keeps_missing_derivative_valuations_open(monkeypatch) -> None:
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
            "EURUSD=X": [PriceRow(date(2025, 1, 1), 1), PriceRow(date(2025, 1, 2), 1), PriceRow(date(2025, 1, 3), 1), PriceRow(date(2025, 1, 6), 1), PriceRow(date(2025, 2, 3), 1), PriceRow(date(2025, 2, 4), 1)],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500, model="execution_history")
    by_date = {point.date: point for point in curve.points}

    assert by_date["2025-02-03"].positions_value is None
    assert not by_date["2025-02-03"].valuation_complete
    assert by_date["2025-02-04"].positions_value == 0
    assert by_date["2025-02-04"].cash == 110
    assert by_date["2025-02-04"].portfolio_index == 100
    assert curve.base_date == "2025-02-04"
    assert "Kursdaten fehlen für 1 Instrumente" in curve.message


def test_trade_republic_curve_deduplicates_cached_price_dates(monkeypatch) -> None:
    transactions = [
        _tr_row(date(2025, 1, 2), "customer_inbound", 0, None, 1000),
        _tr_row(date(2025, 1, 2), "buy", 10, 100, -1000, ticker="NVDA", isin="US67066G1040"),
    ]

    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: transactions)
    monkeypatch.setattr(
        portfolio_service.prices_repository,
        "list_price_bars",
        lambda ticker, start_date=None: {
            "NVDA": [
                PriceRow(date=date(2025, 1, 2), close=100),
                PriceRow(date=date(2025, 1, 2), close=101),
                PriceRow(date=date(2025, 1, 3), close=110),
            ],
            "^GSPC": [
                PriceRow(date=date(2025, 1, 2), close=5000),
                PriceRow(date=date(2025, 1, 2), close=5010),
                PriceRow(date=date(2025, 1, 3), close=5050),
            ],
            "EURUSD=X": [PriceRow(date(2025, 1, 1), 1), PriceRow(date(2025, 1, 2), 1), PriceRow(date(2025, 1, 3), 1), PriceRow(date(2025, 1, 6), 1), PriceRow(date(2025, 2, 3), 1), PriceRow(date(2025, 2, 4), 1)],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500, model="execution_history")

    assert curve.source == "trade_republic_transactions"
    assert curve.points
    assert next(point for point in curve.points if point.date == "2025-01-03").portfolio_index > 100
    assert next(point for point in curve.points if point.date == "2025-01-03").sp500_index is not None


def test_trade_republic_curve_deduplicates_trade_price_fallback_dates(monkeypatch) -> None:
    transactions = [
        _tr_row(date(2025, 2, 3), "customer_inbound", 0, None, 300),
        _tr_row(
            date(2025, 2, 3),
            "buy",
            5,
            20,
            -100,
            isin="DE000DERIV02",
            asset_class="DERIVATIVE",
            name="Factor Long",
        ),
        _tr_row(
            date(2025, 2, 3),
            "buy",
            5,
            22,
            -110,
            isin="DE000DERIV02",
            asset_class="DERIVATIVE",
            name="Factor Long",
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
            "EURUSD=X": [PriceRow(date(2025, 1, 1), 1), PriceRow(date(2025, 1, 2), 1), PriceRow(date(2025, 1, 3), 1), PriceRow(date(2025, 1, 6), 1), PriceRow(date(2025, 2, 3), 1), PriceRow(date(2025, 2, 4), 1)],
        }.get(ticker, []),
    )

    curve = portfolio_service.get_portfolio_curve(days=2500, model="execution_history")

    assert curve.source == "trade_republic_transactions"
    assert curve.points
    assert "Kursdaten fehlen für 1 Instrumente" in curve.message


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


def test_auto_curve_never_substitutes_current_holdings_for_the_tr_ledger(monkeypatch):
    from types import SimpleNamespace
    from app.schemas import PortfolioCurvePoint, PortfolioCurveResponse
    empty_history = PortfolioCurveResponse(model="execution_history", as_of="2025-01-03",
        source="trade_republic_transactions", data_status="limited", points=[
            PortfolioCurvePoint(date="2025-01-02", portfolio_index=None, depot_value=None, positions_value=None, cash=None, valuation_complete=False, missing_instruments=["ISIN"]),
            PortfolioCurvePoint(date="2025-01-03", portfolio_index=None, depot_value=None, positions_value=None, cash=None, valuation_complete=False, missing_instruments=["ISIN"]),
        ])
    monkeypatch.setattr(portfolio_service, "_get_trade_republic_curve", lambda **kw: empty_history)
    monkeypatch.setattr(portfolio_repository, "list_open_positions", lambda: [SimpleNamespace(ticker="NVDA", shares=2, broker="Test")])
    monkeypatch.setattr(portfolio_repository, "get_cash_balance", lambda: 0)
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker, **kw: [PriceRow(date(2025, 1, 2), 100), PriceRow(date(2025, 1, 3), 110)])
    curve = portfolio_service.get_portfolio_curve(start_date=date(2025, 1, 2))
    assert curve is empty_history
    curve = portfolio_service.get_portfolio_curve(start_date=date(2025, 1, 2), model="current_holdings")
    assert curve.model == "current_holdings", curve.message
    assert [p.portfolio_index for p in curve.points] == [100, 110]
    assert [p.sp500_index for p in curve.points] == [100, 110]
    assert "keine historische Depotperformance" in curve.message
    assert portfolio_service.get_portfolio_curve(model="execution_history") is empty_history


def test_missing_stock_symbol_also_prevents_fabricated_total_valuation(monkeypatch):
    rows = [_tr_row(date(2025, 1, 2), "customer_inbound", 0, None, 100),
        _tr_row(date(2025, 1, 2), "buy", 1, 100, -100, isin="UNKNOWN-STOCK")]
    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: rows)
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker, **kw: [PriceRow(date(2025, 1, 2), 1)] if ticker == "EURUSD=X" else [])
    curve = portfolio_service.get_portfolio_curve(start_date=date(2025, 1, 2), model="execution_history")
    assert curve.points[0].portfolio_index is None
    assert "UNKNOWN-STOCK" in curve.points[0].missing_instruments


def test_tr_curve_reconstructs_january_basis_and_only_adds_later_purchase_on_execution(monkeypatch):
    transactions = [
        _tr_row(date(2025, 12, 30), "customer_inbound", 0, None, 1000),
        _tr_row(date(2025, 12, 30), "buy", 2, 100, -200, ticker="NVDA", isin="NVDA-ISIN"),
        _tr_row(date(2026, 6, 12), "buy", 3, 50, -150, ticker="SPCX", isin="SPCX-ISIN"),
    ]
    monkeypatch.setattr(portfolio_repository, "list_trade_republic_transactions", lambda: transactions)
    monkeypatch.setattr(portfolio_repository, "list_open_positions", lambda: pytest.fail("Current holdings must never determine historical NAV"))
    fx = [PriceRow(day.date(), 1) for day in portfolio_service.pd.date_range('2025-12-22', '2026-10-16', freq='B')]
    prices = {
        "NVDA": [PriceRow(date(2025, 12, 31), 100), PriceRow(date(2026, 1, 2), 110), PriceRow(date(2026, 6, 11), 110), PriceRow(date(2026, 6, 12), 110)],
        "SPCX": [PriceRow(date(2026, 6, 12), 60)],
        "EURUSD=X": fx,
        "^GSPC": [PriceRow(date(2025, 12, 31), 5000), PriceRow(date(2026, 1, 2), 5050)],
    }
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker, **kw: prices.get(ticker, []))
    curve = portfolio_service.get_portfolio_curve(start_date=date(2026, 1, 1))
    points = {p.date: p for p in curve.points}
    assert curve.model == 'execution_history'
    assert curve.base_date == '2026-01-01'
    assert points['2026-01-01'].portfolio_index == points['2026-01-01'].sp500_index == 100
    assert points['2026-01-01'].cash == points['2026-06-11'].cash == 800
    assert points['2026-01-01'].positions_value == 200
    assert points['2026-01-02'].portfolio_index == 102
    assert points['2026-01-02'].sp500_index == 101
    assert points['2026-06-12'].cash == 650
    assert points['2026-06-12'].positions_value == 400
    assert points['2026-06-12'].portfolio_index == 105


@pytest.mark.parametrize('deposit_during_gap', [False, True])
def test_return_can_resume_after_quote_gap_only_without_intermediate_external_flows(monkeypatch, deposit_during_gap):
    transactions = [_tr_row(date(2026, 1, 1), 'customer_inbound', 0, None, 100),
                    _tr_row(date(2026, 1, 1), 'buy', 1, 100, -100, ticker='NVDA')]
    if deposit_during_gap:
        transactions.append(_tr_row(date(2026, 1, 7), 'customer_inbound', 0, None, 10))
    monkeypatch.setattr(portfolio_repository, 'list_trade_republic_transactions', lambda: transactions)
    fx = [PriceRow(day.date(), 1) for day in portfolio_service.pd.date_range('2026-01-01', '2026-01-15', freq='B')]
    monkeypatch.setattr(portfolio_service.prices_repository, 'list_price_bars', lambda ticker, **kw: fx if ticker == 'EURUSD=X' else [PriceRow(date(2026, 1, 1), 100), PriceRow(date(2026, 1, 8), 120)])
    curve = portfolio_service.get_portfolio_curve(start_date=date(2026, 1, 1), model='execution_history')
    points = {p.date: p for p in curve.points}
    assert points['2026-01-06'].portfolio_index is None
    assert points['2026-01-07'].portfolio_index is None
    assert points['2026-01-08'].portfolio_index == (None if deposit_during_gap else 120)


def test_derivative_uses_own_issuer_bid_and_daily_quote_currency(monkeypatch):
    from types import SimpleNamespace
    transactions = [_tr_row(date(2025, 12, 30), 'customer_inbound', 0, None, 100),
                    _tr_row(date(2025, 12, 30), 'buy', 2, 20, -40, isin='DE000PRODUCT', asset_class='DERIVATIVE')]
    monkeypatch.setattr(portfolio_repository, 'list_trade_republic_transactions', lambda: transactions)
    prices = {'DE000PRODUCT': [SimpleNamespace(date=date(2025, 12, 31), close=25, source='vontobel:EUR:bid')],
              'EURUSD=X': [PriceRow(date(2025, 12, 31), 1.2), PriceRow(date(2026, 1, 2), 1.3)],
              '^GSPC': [PriceRow(date(2025, 12, 31), 5000)]}
    monkeypatch.setattr(portfolio_service.prices_repository, 'list_price_bars', lambda ticker, **kw: prices.get(ticker, []))
    curve = portfolio_service.get_portfolio_curve(start_date=date(2026, 1, 1), model='execution_history')
    assert curve.base_date == '2026-01-01'
    assert curve.points[0].depot_value == 132  # (60 actual cash + 2 * 25 issuer bid) * 1.2
    assert curve.points[0].positions_value == 60
    assert curve.points[1].portfolio_index == pytest.approx(1.3 / 1.2 * 100, abs=.01)
