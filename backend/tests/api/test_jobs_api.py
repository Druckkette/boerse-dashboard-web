from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
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
