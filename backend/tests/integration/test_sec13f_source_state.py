"""13F preview removal and serialization on disposable PostgreSQL."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from datetime import date
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import AppSetting, Institutional13FTrend, Instrument, Sec13fCusipMapping
from app.repositories import sec13f


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Disposable PostgreSQL not configured")
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(sec13f, "SessionLocal", sessions)
    monkeypatch.setattr(sec13f, "engine", engine)
    keys = ["T" + uuid4().hex[:10].upper() for _ in range(2)]
    yield keys
    with sessions() as db:
        db.execute(delete(Institutional13FTrend).where(Institutional13FTrend.ticker.in_(keys)))
        db.execute(delete(Sec13fCusipMapping).where(Sec13fCusipMapping.ticker.in_(keys)))
        db.execute(delete(Instrument).where(Instrument.ticker.in_(keys)))
        db.execute(
            delete(AppSetting).where(
                AppSetting.key.in_(
                    ["sec13f_source_status", *[f"sec13f_preliminary:{key}" for key in keys]]
                )
            )
        )
        db.commit()
    engine.dispose()


def test_zero_holding_restatement_clears_only_refreshed_preview(database):
    one, two = database
    report = {
        "report_period": "2026-09-30",
        "holder_count": 1,
        "total_shares": 20,
        "total_value_usd": 1000,
    }
    status = {"baseline_report_period": "2026-06-30"}
    sec13f.save_source_status(status, {one: report, two: report}, [one, two])
    sec13f.save_source_status(status, {}, [one])
    assert sec13f.source_status_for_ticker(one) == (status, None)
    assert sec13f.source_status_for_ticker(two) == (status, report)
    sec13f.save_source_status({"baseline_report_period": "2026-09-30"}, {}, [one])
    assert sec13f.source_status_for_ticker(two)[1] is None


def test_parallel_refresh_cannot_overwrite_a_newer_snapshot(database):
    with sec13f.refresh_lock():
        with pytest.raises(RuntimeError, match="läuft bereits"):
            with sec13f.refresh_lock():
                pytest.fail("Concurrent refresh admitted")
    with sec13f.refresh_lock():
        pass


def test_cusip_repair_replaces_obsolete_aggregate_but_preserves_history_and_manager_rows(database):
    ticker = database[0]
    old, new = "D" + uuid4().hex[:8].upper(), "E" + uuid4().hex[:8].upper()
    period = date(2026, 6, 30)

    def write(cusip, report_period, shares):
        return sec13f.Institutional13FTrendWrite(
            ticker=ticker,
            cusip=cusip,
            report_period=report_period,
            filing_date=None,
            shares=shares,
            market_value_usd=shares * 100,
            shares_change_pct=None,
            holders_count=1,
            source_url="https://www.sec.gov",
            raw_json={"total_shares": shares},
        )

    sec13f.upsert_aggregate_trends([write(old, period, 999)])
    sec13f.upsert_aggregate_trends([write(old, date(2026, 3, 31), 10)])
    with sec13f.SessionLocal() as db:
        db.add(
            Institutional13FTrend(
                ticker=ticker, cusip=old, report_period=period, manager_cik="INDIVIDUAL", shares=123
            )
        )
        db.commit()
    sec13f.upsert_aggregate_trends([write(new, period, 20)])
    assert sec13f.get_latest_trend_for_ticker(ticker).shares == 20
    assert sec13f.get_latest_trends_for_tickers([ticker])[ticker].cusip == new
    with sec13f.SessionLocal() as db:
        rows = list(
            db.scalars(select(Institutional13FTrend).where(Institutional13FTrend.ticker == ticker))
        )
    assert len(rows) == 3
    assert any(row.report_period == date(2026, 3, 31) and row.shares == 10 for row in rows)
    assert any(row.manager_cik == "INDIVIDUAL" and row.shares == 123 for row in rows)
