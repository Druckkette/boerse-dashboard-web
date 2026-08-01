from __future__ import annotations

from datetime import date, timedelta
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


def test_refresh_fundamentals_all_universe_uses_resolved_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "resolve_universe_tickers",
        lambda **kwargs: ["AAA", "BBB", "CCC"][: int(kwargs.get("limit") or 3)],
    )
    monkeypatch.setattr(refresh_fundamentals_module, "_tracked_fundamental_tickers", lambda **kwargs: [])

    def fake_refresh(ticker: str, *, include_holders: bool) -> dict:
        seen.append(ticker)
        return {"ticker": ticker, "ok": True, "records_seen": 1, "records_written": 1, "source": "yfinance"}

    monkeypatch.setattr(refresh_fundamentals_module, "refresh_fundamentals_for_ticker", fake_refresh)
    payload = {"mode": "scheduled", "fundamental_universe": "all", "fundamental_limit": 2}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)

    assert result["ok"] is True
    assert result["tickers"] == ["AAA", "BBB"]
    assert seen == ["AAA", "BBB"]


def test_refresh_fundamentals_prioritizes_tracked_tickers_in_full_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "resolve_universe_tickers",
        lambda **kwargs: [] if kwargs.get("fallback") == [] else ["AAA", "BBB", "CCC"],
    )
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "_tracked_fundamental_tickers",
        lambda **kwargs: ["PORTFOLIO"],
    )

    tickers = refresh_fundamentals_module.resolve_fundamental_tickers(
        {"fundamental_universe": "all", "fundamental_limit": 3}
    )

    assert tickers == ["PORTFOLIO", "AAA", "BBB"]


def test_refresh_fundamentals_incremental_skips_current_snapshots(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "resolve_universe_tickers",
        lambda **kwargs: ["AAA", "BBB"],
    )
    monkeypatch.setattr(
        refresh_fundamentals_module.fundamentals_repository,
        "latest_fundamental_refresh_states",
        lambda tickers: {
            "AAA": refresh_fundamentals_module.fundamentals_repository.FundamentalRefreshState(
                ticker="AAA",
                latest_date=date.today(),
                complete=True,
                missing_history_keys=[],
            )
        },
    )

    def fake_refresh(ticker: str, *, include_holders: bool) -> dict:
        seen.append(ticker)
        return {"ticker": ticker, "ok": True, "records_seen": 1, "records_written": 1, "source": "yfinance"}

    monkeypatch.setattr(refresh_fundamentals_module, "refresh_fundamentals_for_ticker", fake_refresh)
    payload = {"fundamental_universe": "all", "incremental": True}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)

    assert result["ok"] is True
    assert result["skipped_count"] == 1
    assert result["success_count"] == 1
    assert seen == ["BBB"]


def test_refresh_fundamentals_incremental_repairs_incomplete_current_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "resolve_universe_tickers",
        lambda **kwargs: ["AAA"],
    )
    monkeypatch.setattr(
        refresh_fundamentals_module.fundamentals_repository,
        "latest_fundamental_refresh_states",
        lambda tickers: {
            "AAA": refresh_fundamentals_module.fundamentals_repository.FundamentalRefreshState(
                ticker="AAA",
                latest_date=date.today(),
                complete=False,
                missing_history_keys=["eps_quarter_history", "annual_revenue_history"],
            )
        },
    )

    def fake_refresh(ticker: str, *, include_holders: bool) -> dict:
        seen.append(ticker)
        return {"ticker": ticker, "ok": True, "records_seen": 1, "records_written": 1, "source": "yfinance+fmp"}

    monkeypatch.setattr(refresh_fundamentals_module, "refresh_fundamentals_for_ticker", fake_refresh)
    payload = {"fundamental_universe": "all", "incremental": True}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)

    assert result["ok"] is True
    assert result["skipped_count"] == 0
    assert result["success_count"] == 1
    assert seen == ["AAA"]


def test_refresh_fundamentals_incremental_marks_all_current_snapshots_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "resolve_universe_tickers",
        lambda **kwargs: ["AAA"],
    )
    monkeypatch.setattr(
        refresh_fundamentals_module.fundamentals_repository,
        "latest_fundamental_refresh_states",
        lambda tickers: {
            "AAA": refresh_fundamentals_module.fundamentals_repository.FundamentalRefreshState(
                ticker="AAA",
                latest_date=date.today(),
                complete=True,
                missing_history_keys=[],
            )
        },
    )
    monkeypatch.setattr(
        refresh_fundamentals_module,
        "refresh_fundamentals_for_ticker",
        lambda *args, **kwargs: pytest.fail("complete current snapshot should be skipped"),
    )
    payload = {"fundamental_universe": "all", "incremental": True}
    job = job_repository.create_job("refresh_fundamentals", payload)

    result = refresh_fundamentals_module.refresh_fundamentals.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["skipped_count"] == 1
    assert result["success_count"] == 0
    assert updated is not None
    assert updated.status == "done"


def test_incremental_fundamentals_prioritize_missing_and_oldest_snapshots() -> None:
    state = refresh_fundamentals_module.fundamentals_repository.FundamentalRefreshState
    selected, skipped, deferred = refresh_fundamentals_module._select_fundamental_work(
        ["RECENT", "OLDER", "MISSING", "OLD"],
        latest_states={
            "RECENT": state(
                ticker="RECENT",
                latest_date=date.today() - timedelta(days=2),
                complete=True,
                missing_history_keys=[],
            ),
            "OLDER": state(
                ticker="OLDER",
                latest_date=date.today() - timedelta(days=20),
                complete=True,
                missing_history_keys=[],
            ),
            "OLD": state(
                ticker="OLD",
                latest_date=date.today() - timedelta(days=30),
                complete=True,
                missing_history_keys=[],
            ),
        },
        incremental=True,
        max_refresh_count=2,
        freshness_days=14,
    )

    assert selected == ["MISSING", "OLD"]
    assert skipped == 1
    assert deferred == 1


def test_incremental_fundamentals_force_due_earnings_to_front() -> None:
    state = refresh_fundamentals_module.fundamentals_repository.FundamentalRefreshState
    today = date.today()
    selected, skipped, deferred = refresh_fundamentals_module._select_fundamental_work(
        ["CURRENT", "DUE", "OLD"],
        latest_states={
            "CURRENT": state(
                ticker="CURRENT",
                latest_date=today,
                complete=True,
                missing_history_keys=[],
            ),
            "DUE": state(
                ticker="DUE",
                latest_date=today,
                complete=True,
                missing_history_keys=[],
            ),
            "OLD": state(
                ticker="OLD",
                latest_date=today - timedelta(days=30),
                complete=True,
                missing_history_keys=[],
            ),
        },
        incremental=True,
        max_refresh_count=1,
        freshness_days=14,
        priority_tickers=["DUE"],
    )

    assert selected == ["DUE"]
    assert skipped == 1
    assert deferred == 1


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
