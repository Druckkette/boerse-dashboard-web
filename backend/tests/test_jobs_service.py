from datetime import UTC, datetime

from app.schemas import Job
from app.services import jobs


def test_job_list_summary_truncates_large_results(monkeypatch) -> None:
    job = Job(
        job_id="job_refresh_prices_test",
        job_type="refresh_prices",
        status="done",
        progress=100,
        current_step="Abgeschlossen",
        requested_by="test",
        payload={},
        created_at=datetime.now(UTC),
        requested_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
        result={"items": [{"ticker": f"T{index}"} for index in range(100)]},
    )
    monkeypatch.setattr(jobs.job_repository, "list_jobs", lambda limit=50: [job])

    result = jobs.list_jobs()

    assert len(result[0].result["items"]) == jobs.JOB_LIST_MAX_RESULT_ITEMS
    assert "_summary" in result[0].result
    assert len(job.result["items"]) == 100


def test_job_list_summary_replaces_unneeded_lists_with_counts(monkeypatch) -> None:
    job = Job(
        job_id="job_smart_refresh_test",
        job_type="smart_refresh_market_data",
        status="done",
        progress=100,
        current_step="Abgeschlossen",
        requested_by="test",
        payload={},
        created_at=datetime.now(UTC),
        requested_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
        result={"actions": [{"ticker": f"T{index}"} for index in range(500)]},
    )
    monkeypatch.setattr(jobs.job_repository, "list_jobs", lambda limit=50: [job])

    result = jobs.list_jobs()

    assert result[0].result["actions_count"] == 500
    assert "actions" not in result[0].result
    assert "_summary" in result[0].result
