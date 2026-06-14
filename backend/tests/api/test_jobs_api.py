from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import jobs as job_repository
from app.repositories.jobs import clear_memory_jobs


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    clear_memory_jobs()


def test_jobs_can_be_started_and_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.jobs as job_service

    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: SimpleNamespace(id="celery-test-id"),
    )

    response = client.post("/api/v1/jobs", json={"type": "refresh_prices", "payload": {"mode": "test"}})
    assert response.status_code == 202
    job = response.json()["job"]
    assert job["job_type"] == "refresh_prices"
    assert job["status"] == "queued"
    assert job["celery_task_id"] == "celery-test-id"

    list_response = client.get("/api/v1/jobs")
    assert list_response.status_code == 200
    assert list_response.json()["jobs"][0]["job_id"] == job["job_id"]


def test_smart_refresh_job_can_be_started(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.jobs as job_service

    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: SimpleNamespace(id="celery-smart-id"),
    )

    response = client.post(
        "/api/v1/jobs",
        json={"type": "smart_refresh_market_data", "payload": {"mode": "smart"}},
    )

    assert response.status_code == 202
    job = response.json()["job"]
    assert job["job_type"] == "smart_refresh_market_data"
    assert job["celery_task_id"] == "celery-smart-id"


def test_jobs_cancel_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.jobs as job_service

    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: SimpleNamespace(id="celery-cancel-id"),
    )
    revoked: list[str] = []
    monkeypatch.setattr(
        job_service.celery_app.control,
        "revoke",
        lambda task_id, terminate=False: revoked.append(task_id),
    )

    job = client.post("/api/v1/jobs", json={"type": "refresh_breadth", "payload": {}}).json()["job"]
    response = client.post(f"/api/v1/jobs/{job['job_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert response.json()["job"]["status"] == "cancelled"
    assert revoked == ["celery-cancel-id"]


def test_parallel_heavy_jobs_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.jobs as job_service

    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: SimpleNamespace(id="celery-running-id"),
    )

    first = client.post("/api/v1/jobs", json={"type": "refresh_prices", "payload": {}})
    second = client.post("/api/v1/jobs", json={"type": "refresh_sec13f", "payload": {}})

    assert first.status_code == 202
    assert second.status_code == 409


def test_active_jobs_remain_visible_when_older_than_recent_limit() -> None:
    active = job_repository.create_job("refresh_relative_strength", {"mode": "test"}, requested_by="test")
    old_started_at = datetime.now(UTC) - timedelta(days=2)
    job_repository.update_job(
        active.job_id,
        status="running",
        progress=42,
        current_step="RS Refresh läuft im Worker",
        created_at=old_started_at,
        requested_at=old_started_at,
        started_at=old_started_at,
    )

    for index in range(5):
        job = job_repository.create_job("refresh_prices", {"index": index}, requested_by="test")
        job_repository.mark_done(job.job_id, result={"index": index})

    response = client.get("/api/v1/jobs?limit=3")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert jobs[0]["job_id"] == active.job_id
    assert jobs[0]["status"] == "running"
    assert len(jobs) == 4
