from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
def reset_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    job_repository.clear_memory_jobs()
    monkeypatch.setattr(
        smart_module.stock_assessment_repository,
        "latest_generated_at",
        lambda: datetime.now(UTC),
    )
    monkeypatch.setattr(
        smart_module,
        "refresh_stock_assessment_snapshots",
        lambda **kwargs: {"ok": True, "records_seen": 2, "records_written": 2},
    )


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

    assert [action.key for action in plan] == [
        "refresh_missing_position_prices",
        "refresh_stock_assessments",
        "position_monitor",
    ]
    assert plan[0].payload["tickers"] == ["NVDA", "MSFT"]
    assert plan[0].payload["range"] == "1y"


def test_market_price_merge_always_includes_open_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        smart_module.portfolio_repository,
        "list_open_positions",
        lambda: [SimpleNamespace(ticker="2318.HK"), SimpleNamespace(ticker="ZPDH.DE")],
    )

    merged = smart_module._merge_price_symbols(
        [smart_module._SimplePriceSymbol(source_ticker="SPY", yahoo_symbol="SPY")],
        benchmark_ticker="SPY",
    )

    tickers = {symbol.source_ticker for symbol in merged}
    assert {"SPY", "2318.HK", "ZPDH.DE"}.issubset(tickers)


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
        "refresh_stock_assessments",
        "position_monitor",
    ]


def test_smart_plan_refreshes_market_dependencies_after_stale_trend_benchmark() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(open_positions_count=1),
        freshness=_freshness(
            prices="fresh",
            trend_benchmark="stale",
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
        "refresh_stock_assessments",
        "position_monitor",
    ]
    assert plan[0].payload["include_market_helpers"] is True


def test_smart_plan_refreshes_stale_tracked_fundamentals() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
            fundamentals="stale",
        ),
        universe_status=_universe(),
        payload={"universe": "us_common_stocks"},
    )

    assert [action.key for action in plan] == ["refresh_fundamentals", "refresh_stock_assessments"]
    assert plan[0].payload["fundamental_universe"] == "tracked"
    assert plan[0].payload["incremental"] is True


def test_smart_plan_can_force_incremental_all_fundamentals() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
            fundamentals="fresh",
        ),
        universe_status=_universe(),
        payload={
            "universe": "us_common_stocks",
            "force_fundamentals": True,
            "fundamental_universe": "all",
            "fundamental_limit": 5000,
        },
    )

    assert [action.key for action in plan] == ["refresh_fundamentals", "refresh_stock_assessments"]
    assert plan[0].payload["fundamental_universe"] == "all"
    assert plan[0].payload["fundamental_limit"] == 5000
    assert plan[0].payload["fundamental_max_refresh_count"] == 250
    assert plan[0].payload["incremental"] is True


def test_smart_plan_allows_custom_fundamental_batch_limit() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
            fundamentals="stale",
        ),
        universe_status=_universe(),
        payload={
            "universe": "us_common_stocks",
            "fundamental_universe": "all",
            "fundamental_limit": 5000,
            "fundamental_max_refresh_count": 40,
        },
    )

    assert [action.key for action in plan] == ["refresh_fundamentals", "refresh_stock_assessments"]
    assert plan[0].payload["fundamental_limit"] == 5000
    assert plan[0].payload["fundamental_max_refresh_count"] == 40


def test_smart_plan_repairs_incomplete_current_fundamentals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smart_module, "_incomplete_fundamental_tickers", lambda payload: ["BE"])

    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
            fundamentals="fresh",
        ),
        universe_status=_universe(),
        payload={"universe": "us_common_stocks"},
    )

    assert [action.key for action in plan] == ["refresh_fundamentals", "refresh_stock_assessments"]
    assert plan[0].payload["tickers"] == ["BE"]
    assert plan[0].payload["repair_incomplete_histories"] is True
    assert "unvollständig" in plan[0].reason


def test_smart_plan_refreshes_missing_13f_trends() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
            sec13f="missing",
        ),
        universe_status=_universe(),
        payload={"universe": "us_common_stocks"},
    )

    assert [action.key for action in plan] == ["refresh_sec13f", "refresh_stock_assessments"]
    assert plan[0].payload["universe"] == "tracked"
    assert plan[0].payload["limit_universe"] == 500


def test_scheduled_smart_plan_forces_market_dependencies_even_when_current() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
        ),
        universe_status=_universe(),
        payload={"mode": "scheduled", "universe": "us_common_stocks"},
    )

    assert [action.key for action in plan] == [
        "refresh_market_prices",
        "refresh_breadth",
        "refresh_relative_strength",
        "refresh_fundamentals",
        "refresh_stock_assessments",
    ]
    assert plan[0].payload["incremental"] is True
    assert plan[0].payload["price_provider_timeout_seconds"] == 15
    assert plan[0].payload["price_action_max_seconds"] == 7200
    assert plan[0].payload["price_batch_size"] == 50
    assert plan[0].payload["price_overlap_days"] == 1
    fundamentals_action = next(action for action in plan if action.key == "refresh_fundamentals")
    assert fundamentals_action.payload["fundamental_universe"] == "all"
    assert fundamentals_action.payload["fundamental_limit"] == 10000
    assert fundamentals_action.payload["fundamental_max_refresh_count"] == 250
    assert fundamentals_action.payload["fundamental_action_max_seconds"] == 2700
    assert "Geplanter Smart-Refresh" in plan[0].reason


def test_scheduled_smart_plan_adds_13f_only_when_stale() -> None:
    plan = smart_module.build_smart_refresh_plan(
        diagnostics=_diagnostics(),
        freshness=_freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
            sec13f="stale",
        ),
        universe_status=_universe(),
        payload={"mode": "scheduled", "universe": "us_common_stocks"},
    )

    assert [action.key for action in plan] == [
        "refresh_market_prices",
        "refresh_breadth",
        "refresh_relative_strength",
        "refresh_fundamentals",
        "refresh_sec13f",
        "refresh_stock_assessments",
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


def test_smart_refresh_task_runs_13f_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(smart_module, "get_data_diagnostics", lambda: _diagnostics())
    monkeypatch.setattr(
        smart_module,
        "get_freshness",
        lambda: _freshness(prices="fresh", breadth="fresh", rs="fresh", sell_ranking="fresh", sec13f="missing"),
    )
    monkeypatch.setattr(smart_module, "get_universe_status", lambda key: _universe(key=key))
    monkeypatch.setattr(smart_module, "get_runtime_config_value", lambda key: "boerse-dashboard-web test@example.com")

    def fake_13f_refresh(payload: dict, *, progress_callback):
        calls.append(f"13f:{payload['universe']}:{payload['limit_universe']}")
        progress_callback(50, "SEC Test", "synthetische 13F-Daten", {"records_seen": 1})
        return {"ok": True, "records_seen": 1, "records_written": 1, "source": "sec"}

    monkeypatch.setattr(smart_module, "refresh_institutional_13f_from_sec", fake_13f_refresh)

    job = job_repository.create_job("smart_refresh_market_data", {"mode": "smart"})
    result = smart_module.smart_refresh_market_data.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert calls == ["13f:tracked:500"]
    assert result["results"]["refresh_sec13f"]["records_written"] == 1
    assert updated is not None
    assert updated.status == "done"


def test_smart_refresh_task_skips_13f_without_sec_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smart_module, "get_data_diagnostics", lambda: _diagnostics())
    monkeypatch.setattr(
        smart_module,
        "get_freshness",
        lambda: _freshness(prices="fresh", breadth="fresh", rs="fresh", sell_ranking="fresh", sec13f="missing"),
    )
    monkeypatch.setattr(smart_module, "get_universe_status", lambda key: _universe(key=key))
    monkeypatch.setattr(smart_module, "get_runtime_config_value", lambda key: "")
    monkeypatch.setattr(
        smart_module,
        "refresh_institutional_13f_from_sec",
        lambda *args, **kwargs: pytest.fail("13F should not start without SEC_USER_AGENT"),
    )

    job = job_repository.create_job("smart_refresh_market_data", {"mode": "smart"})
    result = smart_module.smart_refresh_market_data.run(job.job_id, job.payload)

    assert result["ok"] is True
    assert result["results"]["refresh_sec13f"]["skipped"] is True
    assert "SEC_USER_AGENT" in result["results"]["refresh_sec13f"]["reason"]


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
        "refresh_price_cache_for_symbols",
        lambda symbols, *, range_key, incremental=False, timeout=15, batch_size=50, overlap_days=1: [
            calls.append(f"price:{symbol.ticker}:{range_key}:{incremental}") or {
                "ticker": symbol.ticker,
                "ok": True,
                "records_seen": 10,
                "records_written": 10,
            }
            for symbol in symbols
        ],
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
    assert calls == ["price:NVDA:1y:True", "monitor"]
    assert updated is not None
    assert updated.status == "done"


def test_scheduled_smart_refresh_runs_market_snapshot_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(smart_module, "get_data_diagnostics", lambda: _diagnostics())
    monkeypatch.setattr(
        smart_module,
        "get_freshness",
        lambda: _freshness(prices="fresh", breadth="fresh", rs="fresh", sell_ranking="fresh"),
    )
    monkeypatch.setattr(smart_module, "get_universe_status", lambda key: _universe(key=key))
    monkeypatch.setattr(
        smart_module,
        "resolve_universe_price_symbols",
        lambda **kwargs: [smart_module._SimplePriceSymbol(source_ticker="SPY", yahoo_symbol="SPY")],
    )
    monkeypatch.setattr(smart_module, "resolve_universe_tickers", lambda **kwargs: ["SPY"])
    monkeypatch.setattr(
        smart_module,
        "refresh_price_cache_for_symbols",
        lambda symbols, *, range_key, incremental=False, timeout=15, batch_size=50, overlap_days=1: [
            calls.append(f"price:{symbol.ticker}:{range_key}:{incremental}") or {
                "ticker": symbol.ticker,
                "ok": True,
                "records_seen": 10,
                "records_written": 10,
            }
            for symbol in symbols
        ],
    )
    monkeypatch.setattr(
        smart_module,
        "refresh_market_breadth",
        lambda *args, **kwargs: calls.append("breadth") or {"ok": True, "snapshot_date": "2026-06-19"},
    )
    monkeypatch.setattr(
        smart_module,
        "refresh_relative_strength_ratings",
        lambda *args, **kwargs: calls.append("rs") or {"ok": True, "rows_written": 1},
    )
    monkeypatch.setattr(smart_module, "resolve_fundamental_tickers", lambda payload=None: ["NVDA"])
    monkeypatch.setattr(
        smart_module,
        "refresh_fundamentals_for_ticker",
        lambda ticker, *, include_holders=True: calls.append(f"fundamentals:{ticker}") or {
            "ticker": ticker,
            "ok": True,
            "records_seen": 1,
            "records_written": 1,
        },
    )

    job = job_repository.create_job(
        "smart_refresh_market_data",
        {"mode": "scheduled", "source": "scheduler", "scheduled_window": "afternoon"},
    )
    result = smart_module.smart_refresh_market_data.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert "price:SPY:6m:True" in calls
    assert "price:^GSPC:6m:True" in calls
    assert calls[-3:] == ["breadth", "rs", "fundamentals:NVDA"]
    assert result["results"]["refresh_breadth"]["snapshot_date"] == "2026-06-19"
    assert updated is not None
    assert updated.status == "done"


def test_smart_refresh_fundamentals_are_batched_and_deferred(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(smart_module, "get_data_diagnostics", lambda: _diagnostics())
    monkeypatch.setattr(
        smart_module,
        "get_freshness",
        lambda: _freshness(
            prices="fresh",
            breadth="fresh",
            rs="fresh",
            sell_ranking="fresh",
            fundamentals="stale",
        ),
    )
    monkeypatch.setattr(smart_module, "get_universe_status", lambda key: _universe(key=key))
    monkeypatch.setattr(smart_module, "resolve_fundamental_tickers", lambda payload=None: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(smart_module, "_latest_fundamental_states", lambda tickers: {})
    monkeypatch.setattr(
        smart_module,
        "refresh_fundamentals_for_ticker",
        lambda ticker, *, include_holders=True: calls.append(ticker) or {
            "ticker": ticker,
            "ok": True,
            "records_seen": 1,
            "records_written": 1,
        },
    )

    job = job_repository.create_job(
        "smart_refresh_market_data",
        {
            "mode": "smart",
            "force_fundamentals": True,
            "fundamental_universe": "all",
            "fundamental_max_refresh_count": 2,
        },
    )
    result = smart_module.smart_refresh_market_data.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    fundamentals = result["results"]["refresh_fundamentals"]
    assert result["ok"] is True
    assert result["partial"] is True
    assert result["partial_actions"] == ["refresh_fundamentals"]
    assert calls == ["AAA", "BBB"]
    assert fundamentals["selected_ticker_count"] == 2
    assert fundamentals["deferred_count"] == 1
    assert fundamentals["stopped_due_to_limit"] is True
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
    trend_benchmark: str = "fresh",
    fundamentals: str = "fresh",
    sec13f: str = "fresh",
) -> FreshnessResponse:
    return FreshnessResponse(
        generated_at=datetime.now(UTC),
        services=[
            _service("prices", prices),
            _service("trend_benchmark", trend_benchmark),
            _service("market_breadth", breadth),
            _service("relative_strength", rs),
            _service("fundamentals_tracked", fundamentals),
            _service("institutional_13f", sec13f),
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
