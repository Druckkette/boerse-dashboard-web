from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import jobs as job_repository
from app.schemas import (
    DataDiagnosticIssue,
    DataDiagnosticsResponse,
    FreshnessResponse,
    ServiceFreshness,
    UniverseStatusResponse,
)
from app.workers.tasks import smart_refresh_market_data as smart_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_smart_plan_is_empty_when_everything_is_current() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
        ),
        universe_status=_universe(),
        payload={"universe": "us_common_stocks"},
    )

    assert plan == []


def test_smart_plan_refreshes_only_missing_position_prices_and_monitor() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(
            missing_price_tickers=["NVDA", "MSFT"],
            open_positions_count=2,
        ),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
        ),
        universe_status=_universe(),
        payload={"universe": "us_common_stocks"},
    )

    assert [action.key for action in plan] == ["refresh_missing_position_prices", "position_monitor"]
    assert plan[0].payload["tickers"] == ["NVDA", "MSFT"]
    assert plan[0].payload["range"] == "1y"


def test_smart_plan_refreshes_market_dependencies_after_stale_prices() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(open_positions_count=1),
        freshness=_freshness(
            prices="stale",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
        ),
        universe_status=_universe(),
        payload={"universe": "us_common_stocks", "range": "6m"},
    )

    assert [action.key for action in plan] == [
        "refresh_market_prices",
        "refresh_breadth",
        "refresh_relative_strength",
        "position_monitor",
    ]


def test_smart_refresh_task_marks_done_without_unnecessary_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smart_module, "get_data_diagnostics", lambda: _diagnostics())
    monkeypatch.setattr(
        smart_module,
        "get_freshness",
        lambda: _freshness(prices="fresh", breadth="fresh", rs="fresh", sell_ranking="fresh"),
    )
    monkeypatch.setattr(smart_module, "get_universe_status", lambda key: _universe(key=key))
    job = job_repository.create_job("smart_refresh_market_data", {"mode": "smart"})

    result = smart_module.smart_refresh_market_data.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["actions"] == []
    assert updated is not None
    assert updated.status == "done"
    assert "aktuell" in updated.message


def test_smart_refresh_task_runs_only_planned_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        smart_module,
        "get_data_diagnostics",
        lambda: _diagnostics(missing_price_tickers=["NVDA"], open_positions_count=1),
    )
    monkeypatch.setattr(
        smart_module,
        "get_freshness",
        lambda: _freshness(prices="fresh", breadth="fresh", rs="fresh", sell_ranking="fresh"),
    )
    monkeypatch.setattr(smart_module, "get_universe_status", lambda key: _universe(key=key))
    monkeypatch.setattr(
        smart_module,
        "refresh_price_cache_for_ticker",
        lambda ticker, *, range_key, yahoo_symbol=None: calls.append(f"price:{ticker}:{range_key}") or {
            "ticker": ticker,
            "records_seen": 10,
            "records_written": 10,
        },
    )
    monkeypatch.setattr(
        smart_module,
        "monitor_open_positions",
        lambda tickers=None: calls.append("monitor") or {"ok": True, "updated_count": 1},
    )
    monkeypatch.setattr(
        smart_module,
        "refresh_market_breadth",
        lambda *args, **kwargs: calls.append("breadth") or {"ok": True},
    )
    monkeypatch.setattr(
        smart_module,
        "refresh_relative_strength_ratings",
        lambda *args, **kwargs: calls.append("rs") or {"ok": True},
    )

    job = job_repository.create_job("smart_refresh_market_data", {"mode": "smart"})
    result = smart_module.smart_refresh_market_data.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert calls == ["price:NVDA:1y", "monitor"]
    assert updated is not None
    assert updated.status == "done"


def _diagnostics(
    *,
    missing_price_tickers: list[str] | None = None,
    stale_price_tickers: list[str] | None = None,
    open_positions_count: int = 0,
) -> DataDiagnosticsResponse:
    issues: list[DataDiagnosticIssue] = []
    if missing_price_tickers:
        issues.append(
            DataDiagnosticIssue(
                key="missing_price_cache",
                label="Kursdaten fehlen",
                severity="critical",
                detail=f"{len(missing_price_tickers)} offene Positionen haben noch keinen Price-Cache.",
                tickers=missing_price_tickers,
                action_label="Fehlende Kurse laden",
                job_type="refresh_prices",
                job_payload={"mode": "manual", "range": "1y", "tickers": missing_price_tickers},
            )
        )
    if stale_price_tickers:
        issues.append(
            DataDiagnosticIssue(
                key="stale_price_cache",
                label="Kursdaten veraltet",
                severity="warning",
                detail=f"{len(stale_price_tickers)} offene Positionen sind älter als 7 Tage.",
                tickers=stale_price_tickers,
                action_label="Veraltete Kurse aktualisieren",
                job_type="refresh_prices",
                job_payload={"mode": "manual", "range": "6m", "tickers": stale_price_tickers},
            )
        )
    if not issues:
        issues.append(
            DataDiagnosticIssue(
                key="data_ready",
                label="Datenbasis bereit",
                severity="info",
                detail="Alles aktuell.",
            )
        )
    return DataDiagnosticsResponse(
        as_of=datetime.now(UTC).date().isoformat(),
        health_tone="good" if not missing_price_tickers and not stale_price_tickers else "warning",
        summary="Test diagnostics",
        open_positions_count=open_positions_count,
        price_cache_tickers_count=5000,
        missing_price_count=len(missing_price_tickers or []),
        stale_price_count=len(stale_price_tickers or []),
        missing_yahoo_symbol_count=0,
        isin_mappings_count=1,
        issues=issues,
    )


def _freshness(
    *,
    prices: str,
    breadth: str,
    rs: str,
    sell_ranking: str,
) -> FreshnessResponse:
    return FreshnessResponse(
        generated_at=datetime.now(UTC),
        services=[
            _service("prices", prices),
            _service("market_breadth", breadth),
            _service("relative_strength", rs),
            _service("sell_ranking", sell_ranking),
        ],
    )


def _service(name: str, status: str) -> ServiceFreshness:
    as_of = (datetime.now(UTC) - timedelta(days=1)).date().isoformat() if status != "missing" else ""
    return ServiceFreshness(name=name, status=status, as_of=as_of, lag_minutes=60)


def _universe(*, key: str = "us_common_stocks") -> UniverseStatusResponse:
    return UniverseStatusResponse(
        key=key,
        name="US Common Stocks",
        source="nasdaq_trader",
        member_count=5000,
        updated_at=datetime.now(UTC),
        sample_tickers=["AAPL", "MSFT", "NVDA"],
        metadata={},
    )
