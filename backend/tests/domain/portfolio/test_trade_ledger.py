from app.domain.portfolio.trade_ledger import allocate_trades
from app.repositories.tr_import import match_executions
from app.domain.portfolio.trade_republic import parse_transaction_export_csv
from types import SimpleNamespace


def row(id, kind, shares, price):
    return {"id": id, "type": kind, "shares": shares, "price": price, "fees": 0, "tax": 0,
            "timestamp": id, "date": "2025-01-01", "ticker": "TEST", "isin": "ISIN", "currency": "EUR", "asset_class": "STOCK"}


def test_fractional_fifo_and_reentry():
    result = allocate_trades([row("1", "buy", 1.5, 100), row("2", "sell", .5, 120),
                              row("3", "sell", 1, 130), row("4", "buy", 2, 90)])
    assert result[1]["pnl"] == 10
    assert result[2]["pnl"] == 30
    assert result[2]["remaining"] == 0
    assert result[0]["group"] != result[3]["group"]


def test_oversell_and_missing_history_never_invents_cost_basis():
    result = allocate_trades([row("1", "buy", 2, 100), row("2", "sell", 3, 110)])
    assert result[1]["unallocated"] == 1
    assert result[1]["pnl"] is None
    assert allocate_trades([row("1", "sell", 3, 110)])[0]["pnl"] is None


def test_report_order_independent_matching_without_broker_id():
    header = "date,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax\n"
    buy = "2025-01-02,BUY,STOCK,Test,ISIN,2,100,EUR,-200,-1,0\n"
    cash = "2025-01-01,deposit,CASH,Cash,,0,0,EUR,1000,0,0\n"
    original = parse_transaction_export_csv(header + buy)[0]
    stored = SimpleNamespace(id="stored-buy", external_id=original.external_id, raw_json=original.raw,
        date=original.date.date(), transaction_type="buy", ticker="TEST", shares=2, price=100,
        currency="EUR", gross_amount=-200, fees=-1, tax=0)
    incoming = parse_transaction_export_csv(header + cash + buy)
    assert match_executions(incoming, [stored])[1] == "stored-buy"
