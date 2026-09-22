"""Lease, deduplication and restart contracts on a disposable Postgres instance."""
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.models import RefreshWorkItem
from app.repositories import refresh_work as work


@pytest.fixture
def queue(monkeypatch):
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Disposable Postgres not configured")
    assert make_url(url).database == "audit_tests"
    engine = create_engine(url)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(work, "SessionLocal", sessions)
    with sessions() as db:
        db.execute(delete(RefreshWorkItem))
        db.commit()
    yield sessions
    with sessions() as db:
        db.execute(delete(RefreshWorkItem))
        db.commit()
    engine.dispose()


def request(revision="baseline", group="statements"):
    return work.WorkRequest("TEST", group, revision, datetime.now(UTC) - timedelta(minutes=1))


def test_deduplication_and_retry_survive_replanning(queue):
    work.enqueue([request(), request()])
    item = work.claim()
    assert item and work.claim() is None
    assert work.finish(item, result={"complete": False}, status="waiting_source", delay=timedelta(hours=2))
    work.enqueue([request()])
    assert work.claim() is None
    assert work.summary()["groups"] == [{"group": "statements", "status": "waiting_source", "count": 1}]


def test_expired_lease_and_old_owner_cannot_finish(queue):
    work.enqueue([request()])
    old = work.claim()
    later = datetime.now(UTC) + timedelta(minutes=6)
    new = work.claim(now=later)
    assert new["token"] != old["token"]
    assert new["attempts"] == 2
    assert not work.heartbeat(old)
    assert not work.finish(old, result={}, status="current", delay=timedelta(days=14))
    assert work.heartbeat(new)
    assert work.finish(new, result={}, status="current", delay=timedelta(days=14))


def test_new_event_during_processing_is_not_lost(queue):
    work.enqueue([request()])
    item = work.claim()
    work.enqueue([request("revision:2026-09-14:earnings")])
    assert work.claim() is None
    assert work.finish(item, result={"complete": True}, status="current", delay=timedelta(days=14))
    next_item = work.claim()
    assert next_item["revision"] == "revision:2026-09-14:earnings"
    assert next_item["previous_result"] == {}


def test_archive_work_only_claimed_when_allowed(queue):
    work.enqueue([request(group="sec13f")])
    assert work.claim() is None
    assert work.claim(allow_sec=True)["data_group"] == "sec13f"


def test_batch_claims_use_distinct_leases_and_cannot_be_reclaimed(queue):
    due = datetime.now(UTC) - timedelta(minutes=1)
    work.enqueue([work.WorkRequest(ticker, "assessment", "baseline", due) for ticker in ("A", "B", "C")])

    first = work.claim()
    rest = work.claim_more("assessment", limit=39)

    assert first is not None
    assert {first["ticker"], *(item["ticker"] for item in rest)} == {"A", "B", "C"}
    assert work.claim() is None
    work.heartbeat_many([first, *rest])
    for item in [first, *rest]:
        assert work.finish(item, result={"complete": True}, status="current", delay=timedelta(days=1))


def test_old_universe_work_does_not_outrank_new_portfolio_work(queue):
    now = datetime.now(UTC)
    work.enqueue([
        work.WorkRequest("OLD", "beta", "baseline", now - timedelta(days=4), priority=80),
        work.WorkRequest("HELD", "statements", "baseline", now - timedelta(minutes=1), priority=10),
    ])

    assert work.claim(now=now)["ticker"] == "HELD"
    assert work.claim(now=now)["ticker"] == "OLD"


def test_report_writes_lock_one_ticker_without_blocking_others(queue, monkeypatch):
    from app.workers.tasks import refresh_report_data as report_task

    engine = queue.kw["bind"]
    monkeypatch.setattr(report_task, "engine", engine)
    with report_task._ticker_lock("A"):
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as other:
            assert not other.scalar(text("SELECT pg_try_advisory_lock(7341502, hashtext('A'))"))
            assert other.scalar(text("SELECT pg_try_advisory_lock(7341502, hashtext('B'))"))
            other.execute(text("SELECT pg_advisory_unlock(7341502, hashtext('B'))"))
