from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import pushover_test as pushover_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_pushover_test_skips_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pushover_module,
        "get_settings",
        lambda: SimpleNamespace(pushover_user_key="", pushover_app_token="", pushover_dry_run=False),
    )
    job = job_repository.create_job("pushover_test", {"source": "test"})

    result = pushover_module.pushover_test.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["configured"] is False
    assert result["sent"] is False
    assert updated is not None
    assert updated.status == "skipped"


def test_pushover_test_dry_run_with_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pushover_module,
        "get_settings",
        lambda: SimpleNamespace(
            pushover_user_key="user",
            pushover_app_token="token",
            pushover_dry_run=True,
        ),
    )
    job = job_repository.create_job("pushover_test", {"source": "test"})

    result = pushover_module.pushover_test.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["sent"] is False
    assert updated is not None
    assert updated.status == "done"
