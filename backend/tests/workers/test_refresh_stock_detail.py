from __future__ import annotations

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import refresh_stock_detail as stock_detail_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_refresh_stock_detail_runs_targeted_stock_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        stock_detail_module,
        "refresh_price_cache_for_ticker",
        lambda ticker, *, range_key, incremental: calls.append(f"price:{ticker}:{range_key}:{incremental}") or {
            "ok": True,
            "records_seen": 10,
            "records_written": 10,
        },
    )
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_relative_strength_ratings",
        lambda *, tickers, benchmark_ticker: calls.append(f"rs:{tickers[0]}:{benchmark_ticker}") or {
            "ok": True,
            "records_written": 1,
        },
    )
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_fundamentals_for_ticker",
        lambda ticker, *, include_holders: calls.append(f"fundamentals:{ticker}:{include_holders}") or {
            "ok": True,
            "records_written": 1,
        },
    )
    monkeypatch.setattr(stock_detail_module, "get_runtime_config_value", lambda key: "boerse-dashboard-web test@example.com")
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_institutional_13f_from_sec",
        lambda payload: calls.append(f"13f:{payload['tickers'][0]}") or {"ok": True, "records_written": 1},
    )

    payload = {"ticker": "SNDK", "range": "2y", "benchmark_ticker": "SPY", "source": "test"}
    job = job_repository.create_job("refresh_stock_detail", payload)
    result = stock_detail_module.refresh_stock_detail.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["success_count"] == 1
    assert calls == [
        "price:SNDK:2y:True",
        "price:SPY:2y:True",
        "rs:SNDK:SPY",
        "fundamentals:SNDK:True",
        "13f:SNDK",
    ]
    assert updated is not None
    assert updated.status == "done"


def test_refresh_stock_detail_skips_13f_without_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_price_cache_for_ticker",
        lambda *args, **kwargs: {"ok": True, "records_written": 1},
    )
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_relative_strength_ratings",
        lambda *args, **kwargs: {"ok": True, "records_written": 1},
    )
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_fundamentals_for_ticker",
        lambda *args, **kwargs: {"ok": True, "records_written": 1},
    )
    monkeypatch.setattr(stock_detail_module, "get_runtime_config_value", lambda key: "")
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_institutional_13f_from_sec",
        lambda *args, **kwargs: pytest.fail("13F should not start without SEC_USER_AGENT"),
    )

    job = job_repository.create_job("refresh_stock_detail", {"ticker": "SNDK"})
    result = stock_detail_module.refresh_stock_detail.run(job.job_id, job.payload)
    item = result["items"][0]

    assert result["ok"] is True
    assert item["steps"]["sec13f"]["skipped"] is True
    assert "SEC_USER_AGENT" in item["steps"]["sec13f"]["reason"]


def test_refresh_stock_detail_can_skip_price_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        stock_detail_module,
        "refresh_price_cache_for_ticker",
        lambda *args, **kwargs: pytest.fail("price refresh should be handled by the detail page"),
    )
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_relative_strength_ratings",
        lambda *, tickers, benchmark_ticker: calls.append(f"rs:{tickers[0]}:{benchmark_ticker}") or {
            "ok": True,
            "records_written": 1,
        },
    )
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_fundamentals_for_ticker",
        lambda ticker, *, include_holders: calls.append(f"fundamentals:{ticker}") or {
            "ok": True,
            "records_written": 1,
        },
    )

    payload = {"ticker": "NVDA", "include_prices": False, "include_13f": False}
    job = job_repository.create_job("refresh_stock_detail", payload)
    result = stock_detail_module.refresh_stock_detail.run(job.job_id, payload)
    item = result["items"][0]

    assert result["ok"] is True
    assert result["include_prices"] is False
    assert item["steps"]["price"]["skipped"] is True
    assert item["steps"]["benchmark_price"]["skipped"] is True
    assert calls == ["rs:NVDA:SPY", "fundamentals:NVDA"]


def test_refresh_stock_detail_reports_fundamental_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_provider_empty(*args, **kwargs):
        raise RuntimeError("provider empty")

    monkeypatch.setattr(
        stock_detail_module,
        "refresh_price_cache_for_ticker",
        lambda *args, **kwargs: {"ok": True, "records_written": 1},
    )
    monkeypatch.setattr(
        stock_detail_module,
        "refresh_relative_strength_ratings",
        lambda *args, **kwargs: {"ok": True, "records_written": 1},
    )
    monkeypatch.setattr(stock_detail_module, "refresh_fundamentals_for_ticker", raise_provider_empty)

    job = job_repository.create_job("refresh_stock_detail", {"ticker": "SNDK", "include_13f": False})
    result = stock_detail_module.refresh_stock_detail.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is False
    assert "fundamentals" in result["items"][0]["errors"][0]
    assert updated is not None
    assert updated.status == "failed"
