from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import bootstrap_market_data as bootstrap_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_bootstrap_resumes_completed_steps_after_redelivery(monkeypatch: pytest.MonkeyPatch) -> None:
    symbols = [
        SimpleNamespace(source_ticker="AAA", yahoo_symbol="AAA"),
        SimpleNamespace(source_ticker="BBB", yahoo_symbol="BBB"),
    ]
    called: list[str] = []

    monkeypatch.setattr(
        bootstrap_module,
        "refresh_us_common_stock_universe",
        lambda: pytest.fail("completed universe step should not run again"),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "resolve_universe_price_symbols",
        lambda **kwargs: symbols,
    )
    monkeypatch.setattr(
        bootstrap_module,
        "refresh_market_breadth",
        lambda **kwargs: pytest.fail("completed breadth step should not run again"),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "refresh_price_cache_for_symbols",
        lambda *args, **kwargs: pytest.fail("completed price step should not run again"),
    )

    def fake_rs(**kwargs):
        called.append("rs")
        return {"ok": True, "records_written": 2}

    def fake_monitor(**kwargs):
        called.append("monitor")
        return {"ok": False, "skipped": True, "reason": "no portfolio"}

    monkeypatch.setattr(bootstrap_module, "refresh_relative_strength_ratings", fake_rs)
    monkeypatch.setattr(bootstrap_module, "monitor_open_positions", fake_monitor)
    job = job_repository.create_job(
        "bootstrap_market_data",
        {"mode": "initial", "tickers": ["AAA", "BBB"], "benchmark_ticker": "SPY"},
    )
    job_repository.update_job(
        job.job_id,
        result_json={
            "job_type": "bootstrap_market_data",
            "steps": ["universe", "prices", "breadth"],
            "prices": {
                "success_count": 2,
                "failure_count": 0,
                "completed_tickers": ["AAA", "BBB"],
                "records_seen": 20,
                "records_written": 20,
            },
            "breadth": {"ok": True, "skipped": False},
        },
    )

    result = bootstrap_module.bootstrap_market_data.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["resumed"] is True
    assert result["steps"] == ["universe", "prices", "breadth", "relative_strength", "position_monitor"]
    assert called == ["rs", "monitor"]
    assert updated is not None
    assert updated.status == "done"


def test_bootstrap_redelivery_of_completed_job_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap_module,
        "refresh_us_common_stock_universe",
        lambda: pytest.fail("done bootstrap must not execute again"),
    )
    job = job_repository.create_job("bootstrap_market_data", {"mode": "initial"})
    job_repository.mark_done(
        job.job_id,
        result={
            "ok": True,
            "job_type": "bootstrap_market_data",
            "steps": ["universe", "prices", "breadth", "relative_strength", "position_monitor"],
        },
        message="done",
    )

    result = bootstrap_module.bootstrap_market_data.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["already_completed"] is True
    assert updated is not None
    assert updated.status == "done"


def test_price_refresh_checkpoint_skips_completed_tickers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_refresh(symbols: list, *, range_key: str, incremental: bool, batch_size: int = 50) -> list[dict]:
        seen.extend(symbol.ticker for symbol in symbols)
        return [
            {
                "ticker": symbol.ticker,
                "yahoo_symbol": symbol.yahoo_symbol,
                "ok": True,
                "records_seen": 5,
                "records_written": 5,
            }
            for symbol in symbols
        ]

    monkeypatch.setattr(bootstrap_module, "refresh_price_cache_for_symbols", fake_refresh)
    job = job_repository.create_job("bootstrap_market_data", {"mode": "initial"})
    result = bootstrap_module._refresh_prices_for_symbols(
        job_id=job.job_id,
        symbols=[
            {"source_ticker": "AAA", "yahoo_symbol": "AAA"},
            {"source_ticker": "BBB", "yahoo_symbol": "BBB"},
            {"source_ticker": "CCC", "yahoo_symbol": "CCC"},
        ],
        range_key="1y",
        incremental=True,
        result={},
        existing_result={
            "completed_tickers": ["AAA"],
            "success_count": 1,
            "records_seen": 5,
            "records_written": 5,
        },
    )

    assert seen == ["BBB", "CCC"]
    assert result["incremental"] is True
    assert result["success_count"] == 3
    assert result["failure_count"] == 0
    assert result["records_written"] == 15
    assert result["completed_tickers"] == ["AAA", "BBB", "CCC"]


def test_celery_redis_visibility_timeout_exceeds_task_limit() -> None:
    visibility_timeout = bootstrap_module.celery_app.conf.broker_transport_options["visibility_timeout"]

    assert bootstrap_module.celery_app.conf.task_time_limit >= 48 * 60 * 60
    assert bootstrap_module.celery_app.conf.task_soft_time_limit < bootstrap_module.celery_app.conf.task_time_limit
    assert visibility_timeout > bootstrap_module.celery_app.conf.task_time_limit
