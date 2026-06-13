from __future__ import annotations

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_KEY, DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import jobs as job_repository
from app.services.market import refresh_market_breadth
from app.services.universes import resolve_universe_tickers
from app.workers.celery_app import celery_app
from app.workers.tasks.common import JobCancelled, raise_if_cancelled


@celery_app.task(bind=True, name="refresh_breadth")
def refresh_breadth(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = job_repository.get_job(job_id) if job_id else None
    if job is None:
        job = job_repository.create_job("refresh_breadth", payload, requested_by=str(payload.get("source") or "scheduler"))

    universe = str(payload.get("universe") or DEFAULT_MARKET_UNIVERSE_KEY)
    tickers = resolve_universe_tickers(
        explicit_tickers=payload.get("tickers"),
        universe_key=payload.get("universe"),
        fallback=DEFAULT_MARKET_UNIVERSE_TICKERS,
        limit=int(payload.get("limit_universe") or 5000),
    )
    lookback_days = int(payload.get("lookback_days") or 550)

    job_repository.mark_running(job.job_id, step="Market-Price-Cache lesen")
    try:
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=20,
            step="Universe vorbereiten",
            message=f"{len(tickers)} Ticker im Universe {universe}.",
            result={"universe": universe, "universe_size": len(tickers)},
        )
        raise_if_cancelled(job.job_id)
        job_repository.update_progress(
            job.job_id,
            progress=55,
            step="Breadth-Indikatoren berechnen",
            message="Advancers/Decliners, SMA-Breitenwerte und McClellan werden aus dem Cache berechnet.",
        )
        result = refresh_market_breadth(tickers=tickers, universe=universe, lookback_days=lookback_days)
        if result.get("skipped"):
            job_repository.mark_skipped(job.job_id, message=str(result.get("reason") or "Keine Daten."), result=result)
            return result

        job_repository.update_progress(
            job.job_id,
            progress=90,
            step="MarketSnapshot schreiben",
            message="MarketSnapshot und BreadthDaily wurden vorbereitet.",
            result=result,
        )
        job_repository.mark_done(job.job_id, result=result, message="Marktbreite aktualisiert.")
        return result
    except JobCancelled:
        job_repository.mark_cancelled(job.job_id)
        return {"ok": False, "cancelled": True, "job_type": "refresh_breadth"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        job_repository.mark_failed(job.job_id, error_message=error, result={"ok": False, "job_type": "refresh_breadth"})
        raise
