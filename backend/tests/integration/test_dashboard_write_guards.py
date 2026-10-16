"""Concurrent writes against the disposable audit database, never production."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.db.models import Position, TradeJournalEntry, Transaction
from app.repositories import portfolio, trade_journal

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
