from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.repositories import jobs as job_repository
from app.schemas import WorkspaceState
from app.workers.tasks import refresh_fundamentals as refresh_fundamentals_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_refresh_fundamentals_custom_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, bool]] = []

    def fake_refresh(ticker: str, *, include_holders: bool) -> dict:
        seen.append((ticker, include_holders))
        return {
            "ticker": ticker,
            "ok": True,
            "records_seen": 1,
            "records_written": 1,
            "source": "yfinance",
            "available_fields": ["roe_pct"],
        }

    monkeypatch.setattr(refresh_fundamentals_module, "refresh_fundamentals_for_ticker", fake_refresh)
    payload = {"tickers": ["nvda", "MSFT", "nvda"], "include_holders": False}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["tickers"] == ["NVDA", "MSFT"]
    assert seen == [("NVDA", False), ("MSFT", False)]
    assert result["records_written"] == 2
    assert updated is not None
    assert updated.status == "done"


def test_refresh_fundamentals_tracked_universe_uses_positions_and_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        refresh_fundamentals_module.portfolio_repository,
        "list_open_positions",
        lambda: [SimpleNamespace(ticker="NVDA"), SimpleNamespace(ticker="MSFT")],
    )
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "get_workspace_state",
        lambda: WorkspaceState(
            source="database",
            updated_at=None,
            watchlist=["AAPL", "NVDA"],
            todos="",
            recent_tickers=["TSLA"],
        ),
    )

    def fake_refresh(ticker: str, *, include_holders: bool) -> dict:
        seen.append(ticker)
        return {"ticker": ticker, "ok": True, "records_seen": 1, "records_written": 1, "source": "yfinance"}

    monkeypatch.setattr(refresh_fundamentals_module, "refresh_fundamentals_for_ticker", fake_refresh)
    payload = {"mode": "tracked", "fundamental_limit": 3}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)

    assert result["ok"] is True
    assert result["tickers"] == ["NVDA", "MSFT", "AAPL"]
    assert seen == ["NVDA", "MSFT", "AAPL"]


def test_refresh_fundamentals_continues_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_refresh(ticker: str, *, include_holders: bool) -> dict:
        if ticker == "BAD":
            raise RuntimeError("fundamentals unavailable")
        return {"ticker": ticker, "ok": True, "records_seen": 1, "records_written": 1, "source": "yfinance"}

    monkeypatch.setattr(refresh_fundamentals_module, "refresh_fundamentals_for_ticker", fake_refresh)
    payload = {"tickers": ["AAA", "BAD", "CCC"]}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is False
    assert result["partial"] is True
    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert result["failed_tickers"] == ["BAD"]
    assert updated is not None
    assert updated.status == "done"


def test_refresh_fundamentals_marks_failed_when_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_refresh(ticker: str, *, include_holders: bool) -> dict:
        raise RuntimeError(f"{ticker} unavailable")

    monkeypatch.setattr(refresh_fundamentals_module, "refresh_fundamentals_for_ticker", fake_refresh)
    payload = {"tickers": ["AAA", "BBB"]}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is False
    assert result["success_count"] == 0
    assert result["failure_count"] == 2
    assert updated is not None
    assert updated.status == "failed"
    assert "Fundamentals" in updated.error_message
