"""Verify the preview call chain against real private rows on disposable Postgres."""
import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import Position, SellManualInput, SellRecommendationState
from app.domain.sell.schemas import SellPreviewRequest
from app.domain.sell import service
from app.repositories import settings
from tests.helpers.sell_fixture_data import fixture_price_bars


@pytest.mark.parametrize("ticker", ["NVDA", "TEST"])
def test_preview_cannot_write_or_inherit_real_portfolio_and_sell_state(monkeypatch, ticker):
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Disposable Postgres not configured")
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine)
    marker = uuid4().hex
    with sessions() as db:
        db.add(Position(id=marker, ticker="NVDA", shares=9213, buy_price=654321,
                        buy_date=date(2026, 1, 2), stop_price=333333, note="private-sentinel"))
        manual = SellManualInput(id=marker, ticker="NVDA", pivot=444444,
                                setup_json={"use_global_sell_setup": False, "private": "sentinel"})
        state = SellRecommendationState(id=marker, ticker="NVDA", last_pct=99, consecutive_days=45)
        # Integration tests may share a disposable database but never private storage.
        db.execute(delete(SellManualInput).where(SellManualInput.ticker == "NVDA"))
        db.execute(delete(SellRecommendationState).where(SellRecommendationState.ticker == "NVDA"))
        db.add_all([manual, state])
        db.commit()
    monkeypatch.setattr(service.portfolio_repository, "SessionLocal", sessions)
    monkeypatch.setattr(service.sell_state_repository, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "SessionLocal", sessions)
    monkeypatch.setattr(service.prices_repository, "list_price_bars", fixture_price_bars)
    def snapshot():
        with engine.connect() as conn:
            tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
            return {table: sorted(map(repr, conn.execute(text(f'SELECT * FROM "{table}"')).all())) for table in tables}
    before = snapshot()
    try:
        result = service.preview_manual_sell_decision(SellPreviewRequest(
            ticker=ticker, buy_price=31.25, buy_date=date(2026, 2, 2), currency="USD"))
        assert result.metrics.raw_payload.buy_price == 31.25
        assert result.metrics.raw_payload.shares == 1
        assert result.evaluation.tranche_log == []
        assert result.evaluation.manual.pivot != 444444
        assert "private-sentinel" not in result.model_dump_json()
        def numbers(value):
            if isinstance(value, dict):
                return [number for item in value.values() for number in numbers(item)]
            if isinstance(value, list):
                return [number for item in value for number in numbers(item)]
            return [value] if isinstance(value, (int, float)) else []
        assert 654321 not in numbers(result.model_dump(mode="json"))
        assert snapshot() == before
    finally:
        with sessions() as db:
            db.execute(delete(Position).where(Position.id == marker))
            db.execute(delete(SellManualInput).where(SellManualInput.id == marker))
            db.execute(delete(SellRecommendationState).where(SellRecommendationState.id == marker))
            db.commit()
        engine.dispose()
