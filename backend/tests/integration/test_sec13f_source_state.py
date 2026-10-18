"""13F preview removal and serialization on disposable PostgreSQL."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import AppSetting
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
