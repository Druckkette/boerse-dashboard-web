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
    def run(executions, *, mapped=True):
        csv = "date,datetime,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax,transaction_id\n"
        for day, kind, shares, price, fee, ident in executions:
            amount = shares * price * (-1 if kind == "BUY" else 1)
            csv += f"2025-01-{day:02d},2025-01-{day:02d}T15:00:00Z,{kind},STOCK,Test,{isin},{shares},{price},EUR,{amount},{fee},0,{token}-{ident}\n"
        return tr_import.import_transactions(transactions=parse_transaction_export_csv(csv), positions=[],
            mappings={isin: ticker} if mapped else {}, file_name="test.csv", replace_open_positions=True)
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


def test_unmapped_isin_keeps_broker_executions_and_fifo_without_fabricated_position(setup_import, monkeypatch):
    sessions, ticker, run = setup_import
    rows = [(2, "BUY", 3, 100, -1, "b"), (3, "SELL", 3, 120, -1, "s")]
    result = run(rows, mapped=False)
    with sessions() as db:
        txs = list(db.scalars(select(Transaction).where(Transaction.import_id == result.import_id)))
        ids = [tx.id for tx in txs]
        entries = list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.source_transaction_id.in_(ids))))
        assert len(entries) == 2
        sale = next(row for row in entries if row.entry_type == "sell")
        assert sale.ticker == txs[0].raw_json["isin"]
        assert sale.realized_pnl == pytest.approx(58)
        assert sale.sell_assessment_json["reason_code"] == "ticker_mapping_missing"
        assert all(row.position_id is None for row in entries)
        sale.basis_text = "Originalnotiz bewahren"
        identity = sale.id
        db.commit()
    run(rows, mapped=False)
    # Supplying the symbol later updates the same projections, with no double counting.
    run(rows)
    with sessions() as db:
        entries = list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.source_transaction_id.in_(ids))))
        assert len(entries) == 2 and {entry.ticker for entry in entries} == {ticker}
        assert db.get(TradeJournalEntry, identity).basis_text == "Originalnotiz bewahren"
        assert all(row.position_id is not None for row in entries)


def test_missing_symbol_backfill_is_idempotent_and_preserves_execution_and_position(setup_import, monkeypatch):
    sessions, _, run = setup_import
    from app.services import backfill_trade_journal as service
    monkeypatch.setattr(service, "SessionLocal", sessions)
    result = run([(2, "BUY", 3, 100, -1, "b"), (3, "SELL", 3, 120, -1, "s")], mapped=False)
    with sessions() as db:
        txs = list(db.scalars(select(Transaction).where(Transaction.import_id == result.import_id)))
        ids = [tx.id for tx in txs]
        before = [(t.id, t.ticker, t.position_id, t.price, t.shares, t.raw_json) for t in txs]
        entries = list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.source_transaction_id.in_(ids))))
        for entry in entries:
            db.delete(entry)
        db.commit()
    first = service.backfill_missing_symbols()
    assert first["journal_entries_added"] >= 2
    assert service.backfill_missing_symbols()["journal_entries_added"] == 0
    with sessions() as db:
        txs = list(db.scalars(select(Transaction).where(Transaction.import_id == result.import_id)))
        assert [(t.id, t.ticker, t.position_id, t.price, t.shares, t.raw_json) for t in txs] == before
        assert len(list(db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.source_transaction_id.in_(ids))))) == 2


def test_industry_score_projection_preserves_order_and_values_without_full_payload(setup_import, monkeypatch):
    from datetime import date
    from app.db.models import StockAssessmentSnapshot
    from app.repositories import stock_assessments as repository
    sessions, prefix, _ = setup_import
    monkeypatch.setattr(repository, "SessionLocal", sessions)
    tickers = [prefix + suffix for suffix in ["A", "B", "C"]]
    values = dict(rs_rating=91, fundamental_score=80, moving_average_score=70,
        chart_behavior_score=60, verdict_label="Qualifiziert")
    with sessions() as db:
        for ticker, available, overall, technical in [(tickers[0], True, 80, 70),
                (tickers[1], True, 80, 90), (tickers[2], False, 99, 99)]:
            db.add(StockAssessmentSnapshot(ticker=ticker, as_of=date(2026, 10, 15),
                overall_score=overall, technical_score=technical,
                item_json={**values, "overall_status": "available" if available else "missing",
                    "full_assessment_detail": "x" * 1_000_000}))
        db.commit()
    full = repository.list_all_snapshots(tickers)
    compact = repository.list_ranking_context(tickers)
    assert [row.ticker for row in compact] == [row.ticker for row in full] == [tickers[1], tickers[0], tickers[2]]
    assert all(row.item_json == values for row in compact)
    assert [(r.overall_score, r.technical_score) for r in compact] == [(r.overall_score, r.technical_score) for r in full]
    assert all("full_assessment_detail" in row.item_json for row in full)


def test_discovered_mapping_is_saved_atomically_and_reused_on_next_import(setup_import, monkeypatch):
    from app.db.models import IsinMapping
    from app.repositories import portfolio as repository
    from app.services import portfolio as service, tr_import_mapping
    from app.schemas import TradeRepublicTransactionImportRequest
    from app.services.fx import FxRate
    from datetime import date

    sessions, ticker, run = setup_import
    # Start with fully documented executions whose Yahoo symbol was unknown.
    run([(2, "BUY", 3, 100, 0, "buy")], mapped=False)
    with sessions() as db:
        execution = db.scalar(select(Transaction).where(Transaction.external_id == f"tr:{ticker[1:].lower()}-buy"))
        isin = execution.raw_json["isin"]
        execution_id = execution.id
    monkeypatch.setattr(repository, "SessionLocal", sessions)
    # Isolate this synthetic broker account from other integration fixtures.
    original_merge = tr_import.merged_rows
    monkeypatch.setattr(tr_import, "merged_rows", lambda rows: [row for row in original_merge(rows) if row.isin == isin])
    monkeypatch.setattr(service, "get_eur_usd_rate", lambda: FxRate(pair="EUR/USD", rate=1, as_of=date(2026, 1, 1), source="test"))
    lookups = []
    def search(value, asset_class):
        lookups.append(value)
        return {"ticker": ticker, "candidates": [], "message": "Automatically found"}
    monkeypatch.setattr(tr_import_mapping, "search_isin", search)
    content = f"date,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax,transaction_id\n2025-01-03,DIVIDEND,STOCK,Test,{isin},0,0,EUR,5,0,0,{ticker[1:].lower()}-div\n"
    first = service.import_trade_republic_transaction_export(TradeRepublicTransactionImportRequest(content=content, dry_run=True))
    assert first.mappings[0].source == "automatic"
    with sessions() as db:
        assert db.scalar(select(IsinMapping).where(IsinMapping.isin == isin)) is None
        assert db.get(Transaction, execution_id).ticker == ""
    saved = service.import_trade_republic_transaction_export(TradeRepublicTransactionImportRequest(content=content, dry_run=False))
    assert saved.ok
    with sessions() as db:
        assert db.scalar(select(IsinMapping).where(IsinMapping.isin == isin)).ticker == ticker
        assert db.get(Transaction, execution_id).ticker == ticker
        assert db.get(Transaction, execution_id).shares == 3
    lookups.clear()
    repeated = service.import_trade_republic_transaction_export(TradeRepublicTransactionImportRequest(content=content, dry_run=True))
    assert repeated.ok and repeated.mappings[0].source == "saved"
    assert lookups == []
