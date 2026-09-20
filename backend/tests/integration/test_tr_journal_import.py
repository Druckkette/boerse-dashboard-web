"""Real transactional import tests against the disposable Postgres used by CI."""
import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import Position, Transaction, TradeJournalEntry
from app.domain.portfolio.trade_republic import parse_transaction_export_csv
from app.repositories import tr_import

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")


@pytest.fixture
def setup_import(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(tr_import, "SessionLocal", sessions)
    token = uuid4().hex[:10]
    ticker, isin = "T" + token.upper(), "TEST" + token.upper()
    def run(executions):
        csv = "date,datetime,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax,transaction_id\n"
        for day, kind, shares, price, fee, ident in executions:
            amount = shares * price * (-1 if kind == "BUY" else 1)
            csv += f"2025-01-{day:02d},2025-01-{day:02d}T15:00:00Z,{kind},STOCK,Test,{isin},{shares},{price},EUR,{amount},{fee},0,{token}-{ident}\n"
        return tr_import.import_transactions(transactions=parse_transaction_export_csv(csv), positions=[],
            mappings={isin: ticker}, file_name="test.csv", replace_open_positions=True)
    yield sessions, ticker, run
    engine.dispose()


def test_partial_full_sale_reentry_fees_and_duplicate_import(setup_import):
    sessions, ticker, run = setup_import
    with sessions() as db:
        other = Position(ticker=ticker, shares=77, buy_price=5, currency="EUR", broker="Other", is_open=True)
        db.add(other)
        db.commit()
        other_id = other.id
    rows = [(2, "BUY", 10, 100, -1, "b1"), (3, "BUY", 10, 120, -1, "b2"),
            (6, "SELL", 15, 150, -2, "s1")]
    first = run(rows)
    assert first.transactions_imported == 3
    with sessions() as db:
        sale = db.scalar(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker, TradeJournalEntry.entry_type == "sell"))
        assert sale.realized_pnl == pytest.approx(646.5)  # 2250 - 2 - 1001 - 600.5
        assert len(sale.portfolio_snapshot_json["allocations"]) == 2
        assert sale.currency == "EUR"
        assert sale.sell_assessment_json["status"] == "missing"
        old_group = sale.trade_group_id
        created_at = sale.created_at
        assert db.get(Position, sale.position_id).shares == 5
        assert db.get(Position, other_id).shares == 77
    assert run(rows).transactions_imported == 0
    # Partial follow-up reports must use the existing buys and preserve identity.
    run([(8, "SELL", 5, 130, -1, "s2"), (9, "BUY", 7, 90, -1, "b3")])
    with sessions() as db:
        journal = list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker)))
        assert len(journal) == 5
        sells = [e for e in journal if e.entry_type == "sell"]
        assert {e.trade_group_id for e in sells} == {old_group}
        assert next(e for e in sells if e.price == 150).created_at == created_at
        new_buy = next(e for e in journal if e.price == 90)
        assert new_buy.trade_group_id != old_group
        assert db.get(Position, sells[0].position_id).is_open is False
        assert db.get(Position, new_buy.position_id).is_open is True
        assert db.get(Position, other_id).is_open is True
        assert len(list(db.scalars(select(Transaction).where(Transaction.ticker == ticker)))) == 5


def test_concurrent_identical_imports(setup_import):
    sessions, ticker, run = setup_import
    rows = [(2, "BUY", 3, 10, -1, "b"), (3, "SELL", 1, 12, -1, "s")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run(rows), range(2)))
    with sessions() as db:
        assert len(list(db.scalars(select(Transaction).where(Transaction.ticker == ticker)))) == 2
        assert len(list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker)))) == 2


def test_prepended_history_reuses_position_and_preserves_notes(setup_import):
    sessions, ticker, run = setup_import
    run([(3, "BUY", 2, 100, 0, "b2")])
    with sessions() as db:
        entry = db.scalar(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker))
        old_position = entry.position_id
        entry.basis_text = "Meine ursprüngliche Begründung"
        db.commit()
    run([(2, "BUY", 3, 90, 0, "b1"), (3, "BUY", 2, 100, 0, "b2")])
    with sessions() as db:
        entries = list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker)))
        assert {e.position_id for e in entries} == {old_position}
        assert any(e.basis_text == "Meine ursprüngliche Begründung" for e in entries)
        assert db.get(Position, old_position).shares == 5


def test_transfer_only_position_is_preserved_and_can_close(setup_import):
    sessions, ticker, run = setup_import
    run([(2, "TRANSFER_IN", 3, 100, 0, "in")])
    with sessions() as db:
        position = db.scalar(select(Position).where(Position.ticker == ticker))
        assert position.shares == 3 and position.is_open
        assert not list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker)))
    run([(3, "TRANSFER_OUT", 3, 100, 0, "out")])
    with sessions() as db:
        position = db.scalar(select(Position).where(Position.ticker == ticker))
        assert position.shares == 0 and not position.is_open


def test_stop_dispatch_is_serialized_and_persistent(setup_import, monkeypatch):
    sessions, ticker, _ = setup_import
    from app.services import stop_alerts
    from datetime import UTC, datetime, timedelta
    monkeypatch.setattr(stop_alerts, "SessionLocal", sessions)
    now = datetime.now(UTC)
    item = {"identity": ticker, "ticker": ticker, "name": "Test", "price": 90,
            "stop": 100, "currency": "EUR", "quote_at": now.isoformat()}
    calls = []
    def send(alerts):
        calls.append(alerts)
        return {"sent_alert_ids": [a["alert_id"] for a in alerts]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: stop_alerts.deliver_stop_alerts([item], send, now=now), range(2)))
    assert len(calls) == 1
    later = now + timedelta(days=3)
    item["quote_at"] = later.isoformat()
    stop_alerts.deliver_stop_alerts([item], send, now=later)
    assert len(calls) == 1


def test_editing_imported_journal_notes_preserves_execution_and_fifo(setup_import, monkeypatch):
    sessions, ticker, run = setup_import
    from app.repositories import trade_journal as journal_repository
    from app.services.trade_journal import update_trade_journal_entry
    from app.schemas import TradeJournalEntryRequest
    monkeypatch.setattr(journal_repository, "SessionLocal", sessions)
    run([(2, "BUY", 3, 100, -1, "b"), (3, "SELL", 1, 120, -1, "s")])
    with sessions() as db:
        sale = db.scalar(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker,
            TradeJournalEntry.entry_type == "sell"))
        ident, pnl, snapshot = sale.id, sale.realized_pnl, sale.portfolio_snapshot_json
    result = update_trade_journal_entry(ident, TradeJournalEntryRequest(ticker=ticker, entry_type="sell",
        price=999, shares=999, basis_text="Nachträgliche Notiz"))
    assert result.entry.price == 120 and result.entry.shares == 1
    assert result.entry.realized_pnl == pnl
    assert result.entry.portfolio_snapshot == snapshot
    assert result.entry.basis_text == "Nachträgliche Notiz"


def test_legacy_converted_position_updates_average_without_changing_stop_currency(setup_import):
    sessions, ticker, run = setup_import
    run([(2, "BUY", 2, 100, 0, "b1")])
    with sessions() as db:
        position = db.scalar(select(Position).where(Position.ticker == ticker))
        position.currency, position.buy_price, position.stop_price = "USD", 110, 90
        db.commit()
    run([(3, "BUY", 2, 200, 0, "b2")])
    with sessions() as db:
        position = db.scalar(select(Position).where(Position.ticker == ticker))
        assert position.shares == 4
        assert position.buy_price == pytest.approx(165)
        assert position.currency == "USD" and position.stop_price == 90


def test_existing_assessment_version_is_rebuilt_once(setup_import, monkeypatch):
    sessions, ticker, run = setup_import
    from app.services import historical_sell
    rows = [(2, "BUY", 3, 100, 0, "b"), (3, "SELL", 1, 120, 0, "s")]
    run(rows)
    with sessions() as db:
        sale = db.scalar(select(TradeJournalEntry).where(TradeJournalEntry.ticker == ticker,
            TradeJournalEntry.entry_type == "sell"))
        sale.sell_assessment_json = {"status": "available", "assessment_version": 1}
        db.commit()
    real = historical_sell.assess_historical_sale
    calls = []
    def assess(db, event):
        if event["ticker"] != ticker:
            return real(db, event)
        calls.append(event["id"])
        return {"status": "available", "assessment_version": historical_sell.ASSESSMENT_VERSION}
    monkeypatch.setattr(historical_sell, "assess_historical_sale", assess)
    run(rows)
    run(rows)
    assert len(calls) == 1
