from datetime import UTC, datetime

from app.schemas import Job
from app.services import jobs


def test_job_list_summary_truncates_large_results(monkeypatch) -> None:
    job = Job(
        job_id="job_refresh_prices_test",
        job_type="yahoo_symbol_diagnostics",
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


def test_job_list_summary_omits_payload_and_nested_result_details(monkeypatch) -> None:
    job = Job(
        job_id="job_refresh_prices_test",
        job_type="refresh_prices",
        status="done",
        progress=100,
        current_step="Abgeschlossen",
        requested_by="test",
        payload={"tickers": [f"T{index}" for index in range(500)]},
        created_at=datetime.now(UTC),
        requested_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
        result={
            "ok": True,
            "records_written": 500,
            "freshness": {"metadata": {"ticker_dates": {"AAPL": "2026-07-31"}}},
            "failed_tickers": ["BAD1", "BAD2"],
        },
    )
    monkeypatch.setattr(jobs.job_repository, "list_jobs", lambda limit=50: [job])

    result = jobs.list_jobs()[0]

    assert result.payload == {}
    assert result.result["ok"] is True
    assert result.result["records_written"] == 500
    assert result.result["failed_tickers"] == ["BAD1", "BAD2"]
    assert result.result["freshness_available"] is True
