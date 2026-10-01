"""Historical scores must not see future prices or overwritten fundamental snapshots."""
import os
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.models import FundamentalSnapshot, Instrument, PriceBar, StockAssessmentHistory, TradeJournalEntry
from app.services import trade_journal_backfill as service
from app.repositories import trade_journal as repository

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")


def test_chart_repository_bounds_and_duplicate_source_order(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    with Session(engine) as db:
        ticker = "JC" + uuid4().hex[:12].upper()
        instrument = Instrument(ticker=ticker, name="Chart bounds", currency="USD")
        other = Instrument(ticker=ticker + "X", name="Other", currency="USD")
        db.add_all([instrument, other])
        db.flush()
        day = date(2026, 9, 22)
        db.add_all([
            PriceBar(instrument_id=instrument.id, date=day - timedelta(days=2), close=10, source="test"),
            PriceBar(instrument_id=instrument.id, date=day, close=20, source="old",
                     fetched_at=datetime(2026, 9, 22, tzinfo=UTC)),
            PriceBar(instrument_id=instrument.id, date=day, close=21, source="new",
                     fetched_at=datetime(2026, 9, 23, tzinfo=UTC)),
            PriceBar(instrument_id=instrument.id, date=day + timedelta(days=1), close=999, source="test"),
            PriceBar(instrument_id=other.id, date=day, close=999, source="test"),
        ])
        db.flush()
        monkeypatch.setattr(repository, "SessionLocal", lambda: db)
        rows = repository.historical_price_bars(ticker, start_date=day - timedelta(days=1), end_date=day)
        assert [row.close for row in rows] == [21, 20]
        assert all(row.date == day for row in rows)
    engine.dispose()


def test_historical_cutoffs_overwritten_fundamentals_and_idempotence(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    monkeypatch.setattr(service, "_assessment_score_weights", lambda: {})
    monkeypatch.setattr(service, "_bars_for_ticker", lambda *args: [])
    with Session(engine) as db:
        ticker = "J" + uuid4().hex[:12].upper()
        instrument = Instrument(ticker=ticker, name="Historical test", currency="USD")
        db.add(instrument)
        db.flush()
        day = date(2025, 1, 10)
        cutoff = datetime(2025, 1, 10, 23, 59, tzinfo=UTC)
        bars = [PriceBar(instrument_id=instrument.id, date=stamp.date(), open=100+i/10,
                         high=101+i/10, low=99+i/10, close=100+i/10, volume=100000,
                         source="test") for i, stamp in enumerate(pd.bdate_range(end=day, periods=260))]
        db.add_all(bars)
        fundamental = FundamentalSnapshot(instrument_id=instrument.id, ticker=ticker,
            as_of=day - timedelta(days=3), source="test", quarterly_eps_growth_pct=30,
            created_at=cutoff - timedelta(days=2), updated_at=cutoff - timedelta(days=1))
        db.add(fundamental)
        entry = TradeJournalEntry(ticker=ticker, entry_type="buy", status="open",
            trade_date=day + timedelta(days=3), price=125, shares=10, currency="USD")
        db.add(entry)
        db.flush()
        baseline = service._stock_context(db, entry, day, cutoff)
        assert baseline["payload"]["fundamentals"]["id"] == fundamental.id
        assert baseline["payload"]["assessment"]["technical_v2"]["score"] is not None
        # Old archives must not hide a more recent reconstruction. Future prices/archive
        # values must not change it, even when they are the newest records in the DB.
        db.add(StockAssessmentHistory(ticker=ticker, session_date=day - timedelta(days=1),
            information_cutoff=cutoff - timedelta(days=1), data_fingerprint=uuid4().hex,
            payload_json={"scores": {"overall": 100}}))
        db.add(StockAssessmentHistory(ticker=ticker, session_date=day + timedelta(days=1),
            information_cutoff=cutoff + timedelta(days=1), data_fingerprint=uuid4().hex,
            payload_json={"scores": {"overall": 0}}))
        db.add(PriceBar(instrument_id=instrument.id, date=day + timedelta(days=3),
                       open=99999, high=99999, low=99999, close=99999, source="test"))
        db.flush()
        after_future = service._stock_context(db, entry, day, cutoff)
        assert after_future["payload"]["assessment"] == baseline["payload"]["assessment"]
        assert after_future["payload"]["metrics"]["last_close"] == bars[-1].close
        # A historically dated snapshot updated later is no longer evidence of its old values.
        fundamental.updated_at = cutoff + timedelta(days=2)
        fundamental.quarterly_eps_growth_pct = 999
        db.flush()
        overwritten = service._stock_context(db, entry, day, cutoff)
        assert "fundamentals_missing" in overwritten["reason_codes"]
        assert overwritten["payload"]["assessment"]["overall_v2"]["score"] is None
        assert overwritten["payload"]["assessment"]["technical_v2"] == baseline["payload"]["assessment"]["technical_v2"]
        assert service._store_context(db, entry.id, "stock", overwritten) is True
        assert service._store_context(db, entry.id, "stock", overwritten) is False
        db.rollback()
    engine.dispose()
