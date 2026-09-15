"""Lease, deduplication and restart contracts on a disposable Postgres instance."""
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, delete
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
