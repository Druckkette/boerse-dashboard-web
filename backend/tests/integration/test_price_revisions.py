"""Runs only against the disposable Postgres database created by CI."""
import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import Instrument, RsRating
from app.repositories import prices, stock_assessments
from app.schemas import StockScreeningFilters


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")
def test_price_and_rs_revisions_and_atomic_snapshot_publication(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests", "Never run integration writes on a user database"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine)
    ticker = "TEST_" + uuid4().hex[:12].upper()
    monkeypatch.setattr(prices, "SessionLocal", sessions)
    monkeypatch.setattr(stock_assessments, "SessionLocal", sessions)
    bar = prices.PriceBarWrite(date(2026, 9, 11), 100, 102, 99, 101, 101, 1000)
    prices.upsert_price_bars(ticker, [bar])
    first = stock_assessments.input_revisions()[ticker]
    prices.upsert_price_bars(ticker, [bar])
    assert stock_assessments.input_revisions()[ticker] == first
    assert prices.get_price_cache_metadata(ticker).cache_updated_at is not None
    with sessions() as db:
        instrument = db.scalar(select(Instrument).where(Instrument.ticker == ticker))
        instrument_id = instrument.id
        db.add(RsRating(instrument_id=instrument_id, date=bar.date, source="computed", rating=90))
        db.commit()
    second = stock_assessments.input_revisions()[ticker]
    assert second != first
    with sessions() as db:
        rating = db.scalar(select(RsRating).where(RsRating.instrument_id == instrument_id))
        rating.rating = 95
        db.commit()
    assert stock_assessments.input_revisions()[ticker] != second
    row = stock_assessments.StockAssessmentSnapshotWrite(
        ticker, "Audit", bar.date, 80, 75.0,
        {"ticker": ticker, "warnings_count": 0, "_screening": {"universe_count": 1}},
    )
    stock_assessments.replace_snapshots([row])
    original = stock_assessments.list_all_snapshots()[0]
    stock_assessments.replace_snapshots([row])
    assert stock_assessments.list_all_snapshots()[0].generated_at == original.generated_at
    assert "_screening" not in original.item_json
    result = stock_assessments.query_screening(StockScreeningFilters(complete_only=False), expected_date=bar.date)
    assert result["total_count"] == 1
    assert result["rows"][0]["ticker"] == ticker
    assert result["summary"]["universe_count"] == 1
    assert stock_assessments.query_screening(StockScreeningFilters(complete_only=True), expected_date=bar.date)["total_count"] == 0
    engine.dispose()
