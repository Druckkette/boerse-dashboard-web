from __future__ import annotations

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import jobs as job_repository
from app.services.relative_strength import (
    DEFAULT_RS_BENCHMARK_TICKER,
    DEFAULT_RS_LOOKBACK_DAYS,
    refresh_relative_strength_ratings,
)
from app.services.universes import resolve_universe_tickers
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_relative_strength")
def refresh_relative_strength(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job(
            "refresh_relative_strength",
            payload,
            requested_by=str(payload.get("source") or "scheduler"),
        )

    tickers = resolve_universe_tickers(
        explicit_tickers=payload.get("tickers"),
        universe_key=payload.get("universe"),
        fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
        limit=int(payload.get("limit_universe") or 10000),
    )
    benchmark_ticker = str(payload.get("benchmark_ticker") or DEFAULT_RS_BENCHMARK_TICKER).strip().upper()
    lookback_days = int(payload.get("lookback_days") or DEFAULT_RS_LOOKBACK_DAYS)
    source = str(payload.get("rating_source") or "computed").strip() or "computed"

    job_repository.mark_running(job.job_id, step="RS-Refresh startet")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=20,
            step="Price-Cache lesen",
            message=f"{len(tickers)} Ticker gegen {benchmark_ticker}; keine Live-yfinance-Requests.",
            result={
                "job_type": "refresh_relative_strength",
                "benchmark_ticker": benchmark_ticker,
                "universe_size": len(tickers),
            },
        )
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=55,
            step="RS-Scores berechnen",
            message="Relative-Staerke-Linien und Universe-Percentiles werden aus gecachten Kursen berechnet.",
        )
        result = refresh_relative_strength_ratings(
            tickers=tickers,
            benchmark_ticker=benchmark_ticker,
            lookback_days=lookback_days,
            source=source,
        )
        if result.get("skipped"):
            job_repository.mark_skipped(job.job_id, message=str(result.get("reason") or "Keine Daten."), result=result)
            return result

        job_repository.update_progress(
            job.job_id,
            progress=90,
            step="RS-Ratings schreiben",
            message=f"{result.get('ratings_count', 0)} Ratings wurden berechnet.",
            result=result,
        )
        job_repository.mark_done(job.job_id, result=result, message="Relative-Staerke-Ratings aktualisiert.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "refresh_relative_strength"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(
            job.job_id,
            error_message=error,
            result={"ok": False, "job_type": "refresh_relative_strength"},
        )
        raise
