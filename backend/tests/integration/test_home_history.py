"""Private home reads persisted data; integration writes only to CI's audit DB."""
import os
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import DailyStockOpportunity, EarningsEvent, Instrument, PriceBar, SellRankingSnapshot
from app.domain.sell.schemas import SellPositionRankingItem
from app.repositories import earnings, sell_state
from app.repositories.stock_assessments import StockAssessmentSnapshotWrite
from app.services import daily_opportunities as daily

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")


@pytest.fixture
def database(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine)
    for module in (daily, earnings, sell_state):
        monkeypatch.setattr(module, "SessionLocal", sessions)
    prefix = "HOME_" + uuid4().hex[:8].upper()
    yield sessions, prefix
    with sessions() as db:
        for model in (DailyStockOpportunity, EarningsEvent, SellRankingSnapshot):
            db.execute(delete(model).where(model.ticker.like(prefix + "%")))
        ids = select(Instrument.id).where(Instrument.ticker.like(prefix + "%"))
        db.execute(delete(PriceBar).where(PriceBar.instrument_id.in_(ids)))
        db.execute(delete(Instrument).where(Instrument.ticker.like(prefix + "%")))
        db.commit()
    engine.dispose()


def assessment(ticker, day, score, rs):
    return StockAssessmentSnapshotWrite(ticker, ticker, day, score, 80, {
        "ticker": ticker, "as_of": day.isoformat(), "overall_score": score, "technical_score": 80,
        "rs_rating": rs, "overall_status": "available", "fundamental_score": 75,
        "moving_average_score": 80, "last_close": 100, "dollar_volume_mio": 80,
        "fundamentals_available": True, "rs_line_available": True, "checks": [],
    })


def test_weak_tracked_history_survives_quality_filter_and_reads_negative_changes(database, monkeypatch):
    sessions, prefix = database
    ticker = prefix + "_WEAK"
    day = date(2026, 9, 21)
    clock = {"day": day}
    monkeypatch.setattr(daily, "expected_us_market_session", lambda: SimpleNamespace(date=clock["day"]))
    monkeypatch.setattr(daily, "completed_us_market_session", lambda: SimpleNamespace(date=clock["day"]))
    monkeypatch.setattr(daily, "price_is_current", lambda *a: True)
    monkeypatch.setattr(daily, "daily_bar_is_final", lambda *a: True)
    monkeypatch.setattr(daily, "get_workspace_state", lambda: SimpleNamespace(watchlist=[ticker]))
    monkeypatch.setattr(daily.portfolio, "list_open_positions", lambda: [])
    monkeypatch.setattr(daily.stock_assessments, "list_all_snapshots", lambda *a: [])
    with sessions() as db:
        instrument = Instrument(ticker=ticker)
        db.add(instrument)
        db.flush()
        for offset in range(2):
            db.add(PriceBar(instrument_id=instrument.id, date=day + timedelta(days=offset), close=100, source="test", fetched_at=datetime(2026, 9, 23, tzinfo=UTC)))
        db.commit()
    daily.refresh_top_daily([assessment(ticker, day, 40, 60)])
    clock["day"] = day + timedelta(days=1)
    daily.refresh_top_daily([assessment(ticker, clock["day"], 32, 52)])
    result = daily.get_home_changes(priority_tickers=[ticker])
    assert result["previous_as_of"] == day.isoformat()
    assert result["rows"][0]["details"] == ["Score 40 → 32", "RS 60 → 52"]
    assert result["rows"][0]["rank"] is None
    # Missing the preceding trading session must not compare to an older row.
    clock["day"] = date(2026, 9, 24)
    with sessions() as db:
        instrument_id = db.scalar(select(Instrument.id).where(Instrument.ticker == ticker))
        db.add(PriceBar(instrument_id=instrument_id, date=clock["day"], close=100, source="test"))
        db.commit()
    daily.refresh_top_daily([assessment(ticker, clock["day"], 20, 40)])
    assert daily.get_home_changes(priority_tickers=[ticker])["rows"] == []


def test_calendar_is_batched_sorted_and_preserves_time_source_and_conflict(database):
    sessions, prefix = database
    today = date(2026, 9, 28)
    first, second = prefix + "A", prefix + "B"
    earnings.upsert_earnings_events([
        earnings.EarningsEventWrite(second, today + timedelta(days=3), time="amc", source="fmp"),
        earnings.EarningsEventWrite(first, today, time="bmo", source="nasdaq"),
        earnings.EarningsEventWrite(first, today + timedelta(days=1), source="fmp"),
        earnings.EarningsEventWrite(prefix + "OLD", today - timedelta(days=1)),
    ])
    rows = earnings.upcoming_earnings_events([first, second, prefix + "OLD"], start_date=today, end_date=today + timedelta(days=29))
    assert [row["ticker"] for row in rows] == [first, second]
    assert rows[0]["source"] == "nasdaq" and rows[0]["time"] == "bmo"
    assert rows[0]["date_conflict"] is True
    assert rows[0]["fetched_at"]


def test_sell_snapshot_returns_each_positions_own_generation_time(database):
    sessions, prefix = database
    first = datetime(2026, 9, 25, 21, tzinfo=UTC)
    second = datetime(2026, 9, 28, 21, tzinfo=UTC)
    def row(ticker):
        return SellPositionRankingItem(ticker=ticker, name=ticker, pnl_pct=0, health_score=40,
                                       recommendation_pct=50, status="Verkaufen", reason="Signal", pending_status="scharf")
    sell_state.upsert_ranking_snapshot([row(prefix + "OLD")], generated_at=first)
    sell_state.upsert_ranking_snapshot([row(prefix + "NEW")], generated_at=second)
    rows, generated_at, _ = sell_state.list_ranking_snapshot()
    times = {row.ticker: row.generated_at for row in rows}
    assert times[prefix + "OLD"] == first
    assert times[prefix + "NEW"] == second
    assert generated_at >= second
