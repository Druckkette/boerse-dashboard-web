from contextlib import nullcontext
from types import SimpleNamespace

from app.workers.tasks import refresh_report_data as report_task


def test_due_assessments_are_screened_together_and_failures_are_retried(monkeypatch):
    first = {"key": "assessment:A", "ticker": "A", "data_group": "assessment", "attempts": 1, "priority": 20}
    second = {"key": "assessment:B", "ticker": "B", "data_group": "assessment", "attempts": 1, "priority": 20}
    third = {"key": "assessment:C", "ticker": "C", "data_group": "assessment", "attempts": 1, "priority": 20}
    claimed = iter([first, None])
    calls = []
    finished = []

    monkeypatch.setattr(report_task.refresh_work, "claim", lambda **kwargs: next(claimed))
    monkeypatch.setattr(report_task.refresh_work, "claim_more", lambda *args, **kwargs: [second, third])
    monkeypatch.setattr(report_task.refresh_work, "finish", lambda item, **kwargs: finished.append((item["ticker"], kwargs)))
    monkeypatch.setattr(report_task.jobs, "create_job", lambda *args, **kwargs: SimpleNamespace(job_id="report-job"))
    monkeypatch.setattr(report_task.jobs, "mark_running", lambda *args, **kwargs: None)
    monkeypatch.setattr(report_task.jobs, "update_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(report_task.jobs, "mark_done", lambda *args, **kwargs: None)

    from app.services import stock_screening

    def screen(*, source_job_id, only_tickers):
        calls.append((source_job_id, only_tickers))
        return {"missing_tickers": ["B"], "errors": [{"ticker": "C", "error": "No data"}]}

    monkeypatch.setattr(stock_screening, "screen_universe", screen)

    result = report_task._run_package()

    assert calls == [("report-job", ["A", "B", "C"])]
    assert result["processed"] == 3
    assert result["failed"] == 1
    assert result["waiting_source"] == 1
    assert [(ticker, details["status"]) for ticker, details in finished] == [
        ("A", "current"), ("B", "waiting_source"), ("C", "error")
    ]
    assert finished[1][1]["delay"] == report_task.source_retry_delay(second)
    assert finished[2][1]["error"] == "No data"


def test_missing_source_retries_do_not_churn_low_priority_universe_items():
    assert report_task.source_retry_delay({"attempts": 1, "priority": 20}) == report_task.retry_delay(1)
    assert report_task.source_retry_delay({"attempts": 1, "priority": 80}).days == 1
    assert report_task.source_retry_delay({"attempts": 4, "priority": 80}).days == 14


def test_missing_beta_finishes_as_waiting_source(monkeypatch):
    item = {
        "key": "beta:TEST", "ticker": "TEST", "data_group": "beta", "priority": 80,
        "attempts": 1, "payload": {}, "previous_result": {},
    }
    finished = []
    monkeypatch.setattr(report_task, "_ticker_lock", lambda ticker: nullcontext())
    monkeypatch.setattr(
        report_task,
        "refresh_report_group",
        lambda ticker, group, payload: {"complete": False, "changed": False, "reason": "Provider liefert kein Beta."},
    )
    monkeypatch.setattr(report_task.refresh_work, "finish", lambda item, **kwargs: finished.append(kwargs))

    totals = {"failed": 0, "waiting_source": 0, "changed": 0}
    report_task._run_item(item, "report-job", totals)

    assert totals["failed"] == 0
    assert totals["waiting_source"] == 1
    assert finished[0]["status"] == "waiting_source"
    assert finished[0]["delay"].days == 1
