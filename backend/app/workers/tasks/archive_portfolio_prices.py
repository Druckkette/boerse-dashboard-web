"""Small independent daily capture: never queued behind the full market universe."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.repositories import jobs
from app.services.portfolio import get_portfolio_curve
from app.services.portfolio_curve_prices import refresh_portfolio_curve_prices
from app.workers.celery_app import celery_app


def completed_valuation_day(now: datetime):
    local = now.astimezone(ZoneInfo("Europe/Berlin"))
    day = local.date()
    if (local.hour, local.minute) < (22, 30):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


@celery_app.task(bind=True, name="archive_portfolio_prices", max_retries=2)
def archive_portfolio_prices(self, job_id: str | None = None, payload: dict | None = None) -> dict:
    payload = payload or {}
    job = jobs.get_job(job_id) if job_id else None
    if job is None:
        job = jobs.create_job("archive_portfolio_prices", payload, requested_by=str(payload.get("source") or "scheduler"))
    jobs.mark_running(job.job_id, step="Depotkurse dauerhaft sichern")
    result = {}
    try:
        refresh = refresh_portfolio_curve_prices()
        now = datetime.now(ZoneInfo("Europe/Berlin"))
        completed = completed_valuation_day(now)
        curve = get_portfolio_curve(model="execution_history", start_date=date(completed.year, 1, 1))
        recent = [point for point in curve.points if completed - timedelta(days=7) <= datetime.fromisoformat(point.date).date() <= completed]
        missing = [{"date": point.date, "instruments": point.missing_instruments + (["S&P 500"] if point.sp500_index is None else [])}
            for point in recent if not point.valuation_complete or point.sp500_index is None]
        archive_failed = not refresh.get("archive_ok", False)
        result = dict(ok=not missing and not archive_failed and any(point.date == completed.isoformat() for point in recent) and curve.model == "execution_history",
            partial=not refresh["ok"] or curve.complete_points < curve.total_points,
            completed_day=completed.isoformat(), current_missing=missing,
            complete_points=curve.complete_points, total_points=curve.total_points,
            refresh=refresh)
        if not result["ok"]:
            raise RuntimeError("Depotkurse oder Archiv für abgeschlossene Handelstage unvollständig. Details im Auftrag.")
        jobs.mark_done(job.job_id, result=result,
            message="Depotkurse archiviert. Historische Lücken bleiben im Ergebnis sichtbar." if result["partial"] else "Depotkurse vollständig archiviert.")
        return result
    except Exception as exc:
        jobs.mark_failed(job.job_id, error_message=f"{type(exc).__name__}: {exc}", result=result)
        raise self.retry(exc=exc, args=(job.job_id, payload), countdown=15 * 60)
