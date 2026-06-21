from __future__ import annotations

import pytest

from app.repositories import jobs as job_repository
from app.workers.tasks import refresh_prices as refresh_prices_module


@pytest.fixture(autouse=True)
def reset_jobs() -> None:
    job_repository.clear_memory_jobs()


def test_refresh_prices_volatility_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_refresh(
        ticker: str,
        *,
        range_key: str,
        yahoo_symbol: str | None = None,
        incremental: bool = False,
        timeout: int = 15,
    ) -> dict:
        seen.append(ticker)
        return {
            "ticker": ticker,
            "yahoo_symbol": yahoo_symbol or ticker,
            "records_seen": 10,
            "records_written": 10,
            "first_date": "2025-01-01",
            "last_date": "2025-01-10",
            "source": "yfinance",
        }

    monkeypatch.setattr(refresh_prices_module, "refresh_price_cache_for_ticker", fake_refresh)
    job = job_repository.create_job("refresh_prices", {"preset": "volatility", "range": "1y"})

    result = refresh_prices_module.refresh_prices.run(job.job_id, job.payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is True
    assert result["preset"] == "volatility"
    assert result["tickers"] == ["SPY", "^VIX", "VXX"]
    assert seen == ["SPY", "^VIX", "VXX"]
    assert result["success_count"] == 3
    assert result["failure_count"] == 0
    assert updated is not None
    assert updated.status == "done"


def test_refresh_prices_all_preset_includes_trend_benchmark_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    monkeypatch.setattr(
        refresh_prices_module,
        "resolve_universe_price_symbols",
        lambda **kwargs: [
            refresh_prices_module._SimplePriceSymbol(source_ticker="AAA", yahoo_symbol="AAA"),
        ],
    )

    def fake_refresh(
        ticker: str,
        *,
        range_key: str,
        yahoo_symbol: str | None = None,
        incremental: bool = False,
        timeout: int = 15,
    ) -> dict:
        seen.append(ticker)
        return {
            "ticker": ticker,
            "yahoo_symbol": yahoo_symbol or ticker,
            "records_seen": 1,
            "records_written": 1,
            "source": "yfinance",
        }

    monkeypatch.setattr(refresh_prices_module, "refresh_price_cache_for_ticker", fake_refresh)
    job = job_repository.create_job("refresh_prices", {"preset": "all", "range": "6m"})

    result = refresh_prices_module.refresh_prices.run(job.job_id, job.payload)

    assert result["ok"] is True
    assert "AAA" in seen
    assert "^GSPC" in seen
    assert "SPY" in seen
    assert "EURUSD=X" in seen


def test_refresh_prices_passes_incremental_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, bool]] = []

    def fake_refresh(
        ticker: str,
        *,
        range_key: str,
        yahoo_symbol: str | None = None,
        incremental: bool = False,
        timeout: int = 15,
    ) -> dict:
        seen.append((ticker, incremental))
        return {
            "ticker": ticker,
            "yahoo_symbol": yahoo_symbol or ticker,
            "records_seen": 1,
            "records_written": 1,
            "source": "yfinance",
        }

    monkeypatch.setattr(refresh_prices_module, "refresh_price_cache_for_ticker", fake_refresh)
    payload = {"tickers": ["AAA"], "range": "6m", "incremental": True}
    job = job_repository.create_job("refresh_prices", payload)

    result = refresh_prices_module.refresh_prices.run(job.job_id, payload)

    assert result["ok"] is True
    assert result["incremental"] is True
    assert seen == [("AAA", True)]


def test_refresh_prices_passes_provider_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake_refresh(
        ticker: str,
        *,
        range_key: str,
        yahoo_symbol: str | None = None,
        incremental: bool = False,
        timeout: int = 15,
    ) -> dict:
        seen.append(timeout)
        return {
            "ticker": ticker,
            "yahoo_symbol": yahoo_symbol or ticker,
            "records_seen": 1,
            "records_written": 1,
            "source": "yfinance",
        }

    monkeypatch.setattr(refresh_prices_module, "refresh_price_cache_for_ticker", fake_refresh)
    payload = {"tickers": ["AAA"], "range": "6m", "price_provider_timeout_seconds": 7}
    job = job_repository.create_job("refresh_prices", payload)

    result = refresh_prices_module.refresh_prices.run(job.job_id, payload)

    assert result["ok"] is True
    assert result["provider_timeout_seconds"] == 7
    assert seen == [7]


def test_refresh_prices_continues_after_single_ticker_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_refresh(
        ticker: str,
        *,
        range_key: str,
        yahoo_symbol: str | None = None,
        incremental: bool = False,
        timeout: int = 15,
    ) -> dict:
        if ticker == "BAD":
            raise RuntimeError("upstream rejected ticker")
        return {
            "ticker": ticker,
            "yahoo_symbol": yahoo_symbol or ticker,
            "records_seen": 5,
            "records_written": 5,
            "source": "yfinance",
        }

    monkeypatch.setattr(refresh_prices_module, "refresh_price_cache_for_ticker", fake_refresh)
    payload = {"tickers": ["AAA", "BAD", "CCC"], "range": "1y"}
    job = job_repository.create_job("refresh_prices", payload)

    result = refresh_prices_module.refresh_prices.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is False
    assert result["partial"] is True
    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert result["failed_tickers"] == ["BAD"]
    assert result["records_written"] == 10
    assert updated is not None
    assert updated.status == "done"
    assert "teilweise" in updated.message


def test_refresh_prices_marks_job_failed_when_all_tickers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_refresh(
        ticker: str,
        *,
        range_key: str,
        incremental: bool = False,
        yahoo_symbol: str | None = None,
        timeout: int = 15,
    ) -> dict:
        raise RuntimeError(f"{ticker} unavailable")

    monkeypatch.setattr(refresh_prices_module, "refresh_price_cache_for_ticker", fake_refresh)
    payload = {"tickers": ["AAA", "BBB"], "range": "1y"}
    job = job_repository.create_job("refresh_prices", payload)

    result = refresh_prices_module.refresh_prices.run(job.job_id, payload)
    updated = job_repository.get_job(job.job_id)

    assert result["ok"] is False
    assert result["success_count"] == 0
    assert result["failure_count"] == 2
    assert result["failed_tickers"] == ["AAA", "BBB"]
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error_message == "Kein Ticker konnte aktualisiert werden."
