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
