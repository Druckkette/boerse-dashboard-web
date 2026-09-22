from types import SimpleNamespace

from app.workers.tasks import refresh_report_data as report_task


def test_due_assessments_are_screened_together_and_failures_are_retried(monkeypatch):
    first = {"key": "assessment:A", "ticker": "A", "data_group": "assessment", "attempts": 1}
    second = {"key": "assessment:B", "ticker": "B", "data_group": "assessment", "attempts": 1}
    third = {"key": "assessment:C", "ticker": "C", "data_group": "assessment", "attempts": 1}
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
    assert result["failed"] == 2
    assert [(ticker, details["status"]) for ticker, details in finished] == [
        ("A", "current"), ("B", "error"), ("C", "error")
    ]
    assert finished[1][1]["delay"] == report_task.retry_delay(1)
    assert finished[2][1]["error"] == "No data"
