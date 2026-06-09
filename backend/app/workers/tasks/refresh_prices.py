from __future__ import annotations

from app.workers.celery_app import celery_app
from app.repositories import jobs as job_repository
from app.services.prices import PriceRange, refresh_price_cache_for_ticker
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


DEFAULT_PRICE_REFRESH_TICKERS = ["SPY", "QQQ", "IWM", "NVDA", "MSFT", "AAPL", "META", "LLY", "PLTR"]


@celery_app.task(bind=True, name="refresh_prices")
def refresh_prices(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job("refresh_prices", payload, requested_by=str(payload.get("source") or "scheduler"))

    tickers = _normalize_tickers(payload.get("tickers") or DEFAULT_PRICE_REFRESH_TICKERS)
    range_key = _normalize_range(payload.get("range") or "1y")
    result: dict = {
        "ok": False,
        "job_type": "refresh_prices",
        "range": range_key,
        "tickers": tickers,
        "records_seen": 0,
        "records_written": 0,
        "items": [],
    }

    job_repository.mark_running(job.job_id, step="Price-Cache-Refresh startet")
    try:
        total = max(1, len(tickers))
        for index, ticker in enumerate(tickers, start=1):
            raise_if_cancelled(job.job_id)
            progress = min(90, 10 + int(index / total * 80))
            job_repository.update_progress(
                job.job_id,
                progress=progress,
                step=f"{ticker} von yfinance laden",
                message=f"{ticker}: tägliche OHLC-Bars werden aktualisiert.",
                result=result,
            )
            item = refresh_price_cache_for_ticker(ticker, range_key=range_key)
            result["items"].append(item)
            result["records_seen"] += int(item.get("records_seen") or 0)
            result["records_written"] += int(item.get("records_written") or 0)

        result["ok"] = True
        job_repository.mark_done(job.job_id, result=result, message="Price-Cache aktualisiert.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {**result, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result=result)
        raise


def _normalize_tickers(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = []
    tickers = [item.strip().upper() for item in raw if item and item.strip()]
    return list(dict.fromkeys(tickers))[:50]


def _normalize_range(value: object) -> PriceRange:
    clean = str(value).strip()
    if clean in {"1m", "3m", "6m", "1y", "2y", "5y"}:
        return clean  # type: ignore[return-value]
    return "1y"
