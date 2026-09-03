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

    send_calls: list[dict] = []
    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: send_calls.append({"args": args, "kwargs": kwargs})
        or SimpleNamespace(id="celery-test-id"),
    )

    response = client.post("/api/v1/jobs", json={"type": "refresh_prices", "payload": {"mode": "test"}})
    assert response.status_code == 202
    job = response.json()["job"]
    assert job["job_type"] == "refresh_prices"
    assert job["status"] == "queued"
    assert job["celery_task_id"] == "celery-test-id"
    assert send_calls[0]["kwargs"]["expires"] == 30 * 60

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
    revoked: list[tuple[str, bool, str | None]] = []
    monkeypatch.setattr(
        job_service.celery_app.control,
        "revoke",
        lambda task_id, terminate=False, signal=None: revoked.append((task_id, terminate, signal)),
    )

    job = client.post("/api/v1/jobs", json={"type": "refresh_breadth", "payload": {}}).json()["job"]
    response = client.post(f"/api/v1/jobs/{job['job_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert response.json()["job"]["status"] == "cancelled"
    assert revoked == [("celery-cancel-id", True, "SIGTERM")]


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


def test_position_monitor_uses_dedicated_queue_and_bypasses_heavy_job(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.jobs as job_service

    send_calls: list[dict] = []
    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: send_calls.append({"args": args, "kwargs": kwargs})
        or SimpleNamespace(id=f"celery-{len(send_calls)}"),
    )

    heavy = client.post("/api/v1/jobs", json={"type": "refresh_prices", "payload": {}})
    monitor = client.post("/api/v1/jobs", json={"type": "position_atr_monitor", "payload": {}})

    assert heavy.status_code == 202
    assert monitor.status_code == 202
    assert send_calls[0]["kwargs"]["queue"] == "default"
    assert send_calls[1]["kwargs"]["queue"] == "monitor"


def test_single_stock_refresh_uses_interactive_queue_and_bypasses_heavy_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.jobs as job_service

    send_calls: list[dict] = []
    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: send_calls.append({"args": args, "kwargs": kwargs})
        or SimpleNamespace(id=f"celery-{len(send_calls)}"),
    )

    heavy = client.post("/api/v1/jobs", json={"type": "refresh_prices", "payload": {}})
    detail = client.post(
        "/api/v1/jobs",
        json={"type": "refresh_stock_detail", "payload": {"ticker": "TWLO"}},
    )

    assert heavy.status_code == 202
    assert detail.status_code == 202
    assert send_calls[1]["kwargs"]["queue"] == "interactive"


def test_interactive_stock_refresh_rejects_multiple_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.jobs as job_service

    monkeypatch.setattr(
        job_service.celery_app,
        "send_task",
        lambda *args, **kwargs: SimpleNamespace(id="should-not-run"),
    )

    response = client.post(
        "/api/v1/jobs",
        json={"type": "refresh_stock_detail", "payload": {"tickers": ["TWLO", "NVDA"]}},
    )

    assert response.status_code == 409


def test_scheduled_monitor_history_does_not_hide_user_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_repository, "_with_db", lambda callback, fallback: fallback())
    scheduled = job_repository.create_job(
        "position_atr_monitor",
        {"source": "scheduler"},
        requested_by="scheduler",
    )
    job_repository.mark_done(scheduled.job_id)
    manual = job_repository.create_job("refresh_prices", {"mode": "manual"}, requested_by="api")
    job_repository.mark_done(manual.job_id)

    jobs = job_repository.list_jobs(limit=3)

    assert [job.job_id for job in jobs] == [manual.job_id]


def test_active_scheduled_monitor_remains_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_repository, "_with_db", lambda callback, fallback: fallback())
    scheduled = job_repository.create_job(
        "position_atr_monitor",
        {"source": "scheduler"},
        requested_by="scheduler",
    )
    job_repository.mark_running(scheduled.job_id)

    jobs = job_repository.list_jobs(limit=3)

    assert [job.job_id for job in jobs] == [scheduled.job_id]


def test_stale_running_jobs_are_reconciled_and_no_longer_block(monkeypatch: pytest.MonkeyPatch) -> None:
    active = job_repository.create_job("refresh_relative_strength", {"mode": "test"}, requested_by="test")
    old_started_at = datetime.now(UTC) - timedelta(days=2)
    monkeypatch.setattr(job_repository, "_utcnow", lambda: old_started_at)
    job_repository.update_job(
        active.job_id,
        status="running",
        progress=42,
        current_step="RS Refresh läuft im Worker",
        created_at=old_started_at,
        requested_at=old_started_at,
        started_at=old_started_at,
    )
    monkeypatch.setattr(job_repository, "_utcnow", lambda: datetime.now(UTC))

    for index in range(5):
        job = job_repository.create_job("refresh_prices", {"index": index}, requested_by="test")
        job_repository.mark_done(job.job_id, result={"index": index})

    response = client.get("/api/v1/jobs?limit=3")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    stale = job_repository.get_job(active.job_id)
    assert stale is not None
    assert stale.status == "failed"
    assert stale.current_step == "Verwaisten Job beendet"
    assert len(jobs) == 3
    assert job_repository.active_job_exists() is False
