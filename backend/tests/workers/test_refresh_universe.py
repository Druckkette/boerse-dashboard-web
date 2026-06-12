from __future__ import annotations

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import refresh_universe as refresh_universe_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_refresh_universe_updates_job(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_refresh() -> dict:
        return {
            "ok": True,
            "job_type": "refresh_universe",
            "key": "us_common_stocks",
            "member_count": 2,
            "records_seen": 2,
            "records_written": 2,
        }

    monkeypatch.setattr(refresh_universe_module, "refresh_us_common_stock_universe", fake_refresh)
    job = job_repository.create_job("refresh_universe", {"mode": "test"})

    result = refresh_universe_module.refresh_universe.run(job.job_id, {"mode": "test"})
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["member_count"] == 2
    assert updated is not None
    assert updated.status == "done"
