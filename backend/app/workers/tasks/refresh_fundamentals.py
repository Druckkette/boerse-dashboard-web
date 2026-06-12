from __future__ import annotations

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import jobs as job_repository
from app.services.fundamentals import refresh_fundamentals_for_ticker
from app.services.universes import resolve_universe_tickers
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_fundamentals")
def refresh_fundamentals(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "refresh_fundamentals",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )

    tickers = resolve_universe_tickers(
        explicit_tickers=payload.get("tickers"),
        universe_key=payload.get("universe"),
        fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
        limit=int(payload.get("limit_universe") or 50),
    )
    include_holders = bool(payload.get("include_holders", True))
    fail_fast = bool(payload.get("fail_fast", False))
    result: dict = {
        "ok": False,
        "job_type": "refresh_fundamentals",
        "tickers": tickers,
        "ticker_count": len(tickers),
        "include_holders": include_holders,
        "success_count": 0,
        "failure_count": 0,
        "failed_tickers": [],
        "records_seen": 0,
        "records_written": 0,
        "items": [],
    }

    job_repository.mark_running(job.job_id, step="Fundamental-Refresh startet")
    try:
        total = max(1, len(tickers))
        for index, ticker in enumerate(tickers, start=1):
            raise_if_cancelled(job.job_id)
            job_repository.update_progress(
                job.job_id,
                progress=min(90, 10 + int(index / total * 80)),
                step=f"{ticker} Fundamentals laden",
                message=f"{ticker}: kompakter yfinance-Snapshot wird im Worker geladen.",
                result=result,
            )
            try:
                item = refresh_fundamentals_for_ticker(ticker, include_holders=include_holders)
            except Exception as exc:
                item = {
                    "ticker": ticker,
                    "ok": False,
                    "records_seen": 0,
                    "records_written": 0,
                    "error_message": f"{type(exc).__name__}: {exc}",
                    "source": "yfinance",
                }
                result["failure_count"] += 1
                result["failed_tickers"].append(ticker)
                result["items"].append(item)
                if fail_fast:
                    raise
                continue

            result["items"].append(item)
            result["success_count"] += 1
            result["records_seen"] += int(item.get("records_seen") or 0)
            result["records_written"] += int(item.get("records_written") or 0)

        result["ok"] = result["failure_count"] == 0 and result["success_count"] > 0
        result["partial"] = result["success_count"] > 0 and result["failure_count"] > 0
        if result["success_count"] == 0:
            job_repository.mark_failed(
                job.job_id,
                error_message="Kein Ticker konnte mit Fundamentals aktualisiert werden.",
                result=result,
            )
            return result

        message = "Fundamental-Cache aktualisiert."
        if result["failure_count"]:
            message = f"Fundamental-Cache teilweise aktualisiert; {result['failure_count']} Ticker fehlgeschlagen."
        job_repository.mark_done(job.job_id, result=result, message=message)
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {**result, "cancelled": True}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result=result)
        raise
