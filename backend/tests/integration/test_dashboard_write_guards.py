"""Concurrent writes against the disposable audit database, never production."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from uuid import uuid4
from threading import Barrier
import time

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.db.models import Position, TradeJournalEntry, Transaction
from app.repositories import portfolio, trade_journal
from app.schemas import PortfolioImportRow

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")


@pytest.fixture
def storage(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(portfolio, "SessionLocal", sessions)
    monkeypatch.setattr(trade_journal, "SessionLocal", sessions)
    yield sessions, "GUARD" + uuid4().hex[:10].upper()
    engine.dispose()


def test_create_only_does_not_overwrite_a_holding_even_with_concurrent_clicks(storage):
    sessions, ticker = storage
    write = portfolio.PortfolioPositionWrite(ticker=ticker, name="Guard", shares=50, entry_price=100, current_price=None, currency="USD", buy_date=date(2025, 1, 2), pivot_tag=None, stop_pct=None, stop_price=90, broker="test", account="test", note="original", record_transaction=True, create_only=True)
    def create(_):
        try:
            portfolio.upsert_position(write)
            return "created"
        except portfolio.PositionAlreadyExists:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, range(2))) == ["conflict", "created"]
    with sessions() as db:
        rows = list(db.scalars(select(Position).where(Position.ticker == ticker)))
        assert len(rows) == 1 and rows[0].shares == 50 and rows[0].stop_price == 90
        assert len(list(db.scalars(select(Transaction).where(Transaction.ticker == ticker)))) == 1


def test_concurrent_partial_manual_sales_cannot_oversell_a_buy(storage):
    sessions, ticker = storage
    with sessions() as db:
        buy = TradeJournalEntry(ticker=ticker, entry_type="buy", status="open", trade_date=date(2025, 1, 2), price=100, shares=10, currency="EUR")
        db.add(buy)
        db.commit()
        buy_id = buy.id
    def sell(_):
        try:
            trade_journal.create_entry(dict(ticker=ticker, entry_type="sell", status="closed", trade_date=date(2025, 1, 3), price=110, shares=6, currency="EUR", linked_entry_id=buy_id))
            return "created"
        except ValueError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(sell, range(2))) == ["conflict", "created"]
    with sessions() as db:
        assert sum(row.shares for row in db.scalars(select(TradeJournalEntry).where(TradeJournalEntry.linked_entry_id == buy_id))) == 6


def _holding(ticker, **values):
    fields = dict(ticker=ticker, name="Guard", shares=10, entry_price=100, current_price=None,
                  currency="USD", buy_date=date(2025, 1, 2), pivot_tag=None, stop_pct=None,
                  stop_price=90, broker="test", account="test", note="original", record_transaction=True)
    return portfolio.PortfolioPositionWrite(**(fields | values))


def test_concurrent_portfolio_sales_preserve_inventory_and_cash(storage):
    sessions, ticker = storage
    portfolio.upsert_position(_holding(ticker))
    barrier = Barrier(2)
    def delay_read(conn, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT positions.") and "positions.ticker =" in statement:
            time.sleep(.05)
    engine = sessions.kw["bind"]
    event.listen(engine, "after_cursor_execute", delay_read)
    def sell(_):
        barrier.wait(timeout=5)
        try:
            portfolio.sell_position(portfolio.PortfolioSellWrite(ticker, 6, 110, date(2025, 1, 3), "USD", 0, 0, ""))
            return "sold"
        except portfolio.PortfolioRepositoryUnavailable:
            return "conflict"
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(sell, range(2))) == ["conflict", "sold"]
    finally:
        event.remove(engine, "after_cursor_execute", delay_read)
    with sessions() as db:
        position = db.scalar(select(Position).where(Position.ticker == ticker))
        sales = list(db.scalars(select(Transaction).where(Transaction.ticker == ticker, Transaction.transaction_type == "sell")))
        assert position.shares == 4
        assert len(sales) == 1 and sales[0].shares == 6 and sales[0].net_amount == 660


def test_sale_retry_has_one_effect_and_rejects_changed_payload(storage):
    from dataclasses import replace
    sessions, ticker = storage
    portfolio.upsert_position(_holding(ticker))
    write = portfolio.PortfolioSellWrite(ticker, 10, 110, date(2025, 1, 3), "USD", 0, 0, "", uuid4().hex)
    first = portfolio.sell_position(write)
    second = portfolio.sell_position(write)
    assert first[0] is None and second[0] is None and first[1].id == second[1].id
    with pytest.raises(ValueError, match="Buchungskennung"):
        portfolio.sell_position(replace(write, price=111))
    with sessions() as db:
        assert len(list(db.scalars(select(Transaction).where(Transaction.ticker == ticker, Transaction.transaction_type == "sell")))) == 1


def test_duplicate_and_parallel_csv_imports_keep_one_open_position(storage):
    sessions, ticker = storage
    from app.db.models import Instrument
    with sessions() as db:
        db.add(Instrument(ticker=ticker, name=ticker, currency="USD"))
        db.commit()
    rows = [PortfolioImportRow(ticker=ticker, shares=5, entry_price=100, currency="USD"),
            PortfolioImportRow(ticker=ticker, shares=7, entry_price=100, currency="USD")]
    def load(_):
        return portfolio.upsert_imported_positions(rows, source="audit", file_name="audit.csv", replace_open_positions=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(result.rows_imported == 1 for result in pool.map(load, range(2)))
    with sessions() as db:
        positions = list(db.scalars(select(Position).where(Position.ticker == ticker, Position.is_open.is_(True))))
        assert len(positions) == 1 and positions[0].shares == 7


def test_explicit_stop_mode_changes_the_effective_stop(storage):
    from dataclasses import replace
    _sessions, ticker = storage
    write = _holding(ticker)
    portfolio.upsert_position(write)
    changed = portfolio.upsert_position(replace(write, stop_mode="pct", stop_pct=15, stop_price=None))
    assert changed.stop_price == 85 and changed.stop_pct == 15
    changed = portfolio.upsert_position(replace(write, stop_mode="price", stop_price=91))
    assert changed.stop_price == 91 and changed.stop_pct is None
    changed = portfolio.upsert_position(replace(write, stop_mode="none", stop_price=None))
    assert changed.stop_price is None and changed.stop_pct is None


def test_cash_expenses_and_sale_costs_keep_their_sign(storage, monkeypatch):
    from app.repositories import analysis
    sessions, ticker = storage
    monkeypatch.setattr(analysis, "SessionLocal", sessions)
    before = portfolio.get_cash_balances().get("USD", 0)
    for kind, amount in [("deposit", 100), ("withdrawal", 20), ("fee", 10), ("tax", 5),
                         ("dividend", 3), ("interest", 2), ("other", 4)]:
        portfolio.add_cash_flow(portfolio.PortfolioCashFlowWrite(date(2025, 1, 2), amount, kind, "USD", "test", ""))
    assert portfolio.get_cash_balances()["USD"] - before == pytest.approx(74)
    portfolio.upsert_position(_holding(ticker, shares=1))
    _, sale = portfolio.sell_position(portfolio.PortfolioSellWrite(ticker, 1, 10, date(2025, 1, 3), "USD", 15, 0, ""))
    assert sale.net_amount == -5
    assert portfolio.get_cash_balances()["USD"] - before == pytest.approx(74 - 100 - 5)
    assert next(event for event in analysis.ledger()["events"] if event["id"] == sale.id)["net"] == -5


def test_buy_edit_preserves_previously_documented_sales(storage):
    sessions, ticker = storage
    with sessions() as db:
        buy = TradeJournalEntry(ticker=ticker, entry_type="buy", status="open", trade_date=date(2025, 1, 2), price=100, shares=10, currency="EUR")
        db.add(buy)
        db.commit()
        buy_id = buy.id
    trade_journal.create_entry(dict(ticker=ticker, entry_type="sell", status="closed", trade_date=date(2025, 1, 3), price=110, shares=6, currency="EUR", linked_entry_id=buy_id))
    with pytest.raises(ValueError, match="Kaufänderung"):
        trade_journal.update_entry(buy_id, {"shares": 5})
    with sessions() as db:
        assert db.get(TradeJournalEntry, buy_id).shares == 10


def test_archived_score_evidence_and_weight_preview_are_read_only(storage, monkeypatch):
    from app.db.models import DailyStockOpportunity, StockAssessmentSnapshot
    from app.services import stock_insights
    from app.services.assessment_version import calculation_identity
    from app.services.settings import DEFAULT_SETTINGS
    sessions, ticker = storage
    weights = DEFAULT_SETTINGS.assessment_score_weights.model_dump()
    monkeypatch.setattr(stock_insights, "SessionLocal", sessions)
    monkeypatch.setattr(stock_insights, "_assessment_score_weights", lambda: weights)
    identity = calculation_identity(weights)
    def components(score):
        return {key: {"score": score, "status": "available", "effective_weight": weight / 100} for key, weight in weights["overall"].items()}
    with sessions() as db:
        for day, score, passed in [(date(2025, 1, 2), 70, False), (date(2025, 1, 3), 80, True)]:
            db.add(DailyStockOpportunity(ticker=ticker, as_of=day, overall_score=score, technical_score=score, fundamental_score=score, moving_average_score=score, chart_behavior_score=score, details_json={"calculation": identity, "assessment_evidence": {"available_weight": 1, "components": components(score), "checks": [{"id": "original_stop", "label": "Criterion", "passed": passed}]}}))
        db.add(StockAssessmentSnapshot(ticker=ticker, name="Immutable", as_of=date(2025, 1, 3), overall_score=80, technical_score=80, item_json={"calculation": identity, "overall_v2": {"available_weight": 1, "components": components(80)}}))
        db.commit()
    history = stock_insights.score_history(ticker)
    assert history["status"] == "comparable" and history["score_delta"] == 10
    assert sum(item["contribution_delta"] for item in history["component_changes"]) + history["rounding_delta"] == 10
    assert history["changes"][0]["before"] is False and history["changes"][0]["after"] is True
    assert history["points"][-1]["connect_to_previous"] is True
    preview = stock_insights.weight_preview({"technical": 100, "fundamental": 0, "chart": 0, "moving_average": 0})
    assert next(row for row in preview["rows"] if row["ticker"] == ticker)["alternative_score"] == 80
    with sessions() as db:
        row = db.scalar(select(StockAssessmentSnapshot).where(StockAssessmentSnapshot.ticker == ticker))
        assert row.overall_score == 80 and row.item_json["calculation"] == identity
        old = db.get(DailyStockOpportunity, (date(2025, 1, 2), ticker))
        old.details_json = {**old.details_json, "calculation": {"configuration_hash": "old"}}
        db.commit()
    assert stock_insights.score_history(ticker)["status"] == "model_changed"
    assert stock_insights.score_history(ticker)["points"][-1]["connect_to_previous"] is False
