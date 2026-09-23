"""Short background packages; durable rows survive a lost broker message."""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.db.session import engine
from app.data_sources.provider_usage import capture_provider_usage
from app.repositories import jobs, refresh_work
from app.services.report_refresh import refresh_report_group
from app.workers.celery_app import celery_app


def retry_delay(attempts: int) -> timedelta:
    return timedelta(hours=(2, 8, 24, 48, 96, 168)[min(max(0, attempts - 1), 5)])


def source_retry_delay(item: dict) -> timedelta:
    """Recheck urgent positions quickly, but do not churn broad missing-source work."""
    if item.get("priority", 50) <= 40:
        return retry_delay(item["attempts"])
    return timedelta(days=(1, 3, 7, 14)[min(max(0, item["attempts"] - 1), 3)])


@contextmanager
def _ticker_lock(ticker: str):
    """Serialize statement and beta writes for one ticker across report workers."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("SELECT pg_advisory_lock(7341502, hashtext(:ticker))"), {"ticker": ticker})
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(7341502, hashtext(:ticker))"), {"ticker": ticker})


@celery_app.task(name="refresh_report_data", ignore_result=True, soft_time_limit=3500, time_limit=3600)
def refresh_report_data() -> dict:
    # refresh_work.claim() uses FOR UPDATE SKIP LOCKED and a per-row lease, so
    # separate report workers can safely process independent items in parallel.
    return _run_package()


def _run_package() -> dict:
    started = monotonic()
    job = None
    result = {"processed": 0, "failed": 0, "waiting_source": 0, "changed": 0}
    try:
        for _ in range(8):
            if monotonic() - started >= 120:
                break
            now = datetime.now(UTC)
            hour = now.astimezone(ZoneInfo("Europe/Berlin")).hour
            item = refresh_work.claim(allow_sec=2 <= hour < 6)
            if item is None:
                break
            if job is None:
                job = jobs.create_job("refresh_report_data", {}, requested_by="scheduler")
                jobs.mark_running(job.job_id, step="Berichtspflege")
            jobs.update_progress(job.job_id, progress=min(90, result["processed"] * 10),
                                 step=f"{item['data_group']}: {item['ticker']}",
                                 message="Fortsetzbare Berichtspflege; Marktzyklus bleibt unabhaengig.", result=result)
            if item["data_group"] == "assessment":
                batch = [item, *refresh_work.claim_more("assessment", limit=39)]
                _run_assessment_batch(batch, job.job_id, result)
                result["processed"] += len(batch)
            else:
                _run_item(item, job.job_id, result)
                result["processed"] += 1
        result["duration_seconds"] = round(monotonic() - started, 2)
        if job:
            jobs.mark_done(job.job_id, result=result, message="Berichtspaket abgeschlossen; offene Arbeit wird automatisch fortgesetzt.")
        return result
    except Exception as exc:
        if job:
            jobs.mark_failed(job.job_id, error_message=f"{type(exc).__name__}: {exc}"[:500], result=result)
        raise


def _run_item(item: dict, job_id: str, totals: dict) -> None:
    stop = Event()

    def keep_alive():
        while not stop.wait(30):
            try:
                if not refresh_work.heartbeat(item):
                    return
                jobs.update_job(job_id)
            except Exception:
                return

    thread = Thread(target=keep_alive, daemon=True)
    thread.start()
    try:
        if item["data_group"] == "filings":
            from app.services.filing_events import discover_filing_events
            value = discover_filing_events()
            complete, delay = True, timedelta(hours=12)
        elif item["data_group"] == "sec13f":
            from app.services.sec13f import refresh_institutional_13f_from_sec
            value = refresh_institutional_13f_from_sec({"universe": "us_common_stocks", "limit_universe": 10000, "dataset_count": 2})
            complete, delay = bool(value.get("ok")), timedelta(hours=24)
            if value.get("records_written"):
                now = datetime.now(UTC)
                refresh_work.enqueue([
                    refresh_work.WorkRequest(row["ticker"], "assessment", "update:" + now.isoformat(), now, 20)
                    for row in value.get("ticker_breakdown", []) if row.get("status") == "matched"
                ])
        else:
            payload = dict(item["payload"])
            if item["previous_result"].get("complete"):
                payload.pop("event_date", None)
            with capture_provider_usage() as provider_usage:
                with _ticker_lock(item["ticker"]):
                    value = refresh_report_group(item["ticker"], item["data_group"], payload)
            value["provider_usage"] = dict(provider_usage)
            for metric, count in provider_usage.items():
                totals.setdefault("provider_usage", {})[metric] = totals.setdefault("provider_usage", {}).get(metric, 0) + count
            complete = value["complete"]
            delay = timedelta(days=7 if item["data_group"] == "beta" else 14) if complete else source_retry_delay(item)
            if value.get("changed"):
                totals["changed"] += 1
                refresh_work.enqueue([refresh_work.WorkRequest(item["ticker"], "assessment", "update:" + datetime.now(UTC).isoformat(), datetime.now(UTC), 20)])
        if not complete:
            totals["waiting_source"] += 1
        refresh_work.finish(item, result=value, status="current" if complete else "waiting_source", delay=delay)
    except Exception as exc:
        totals["failed"] += 1
        refresh_work.finish(item, result={}, status="error", delay=retry_delay(item["attempts"]), error=f"{type(exc).__name__}: {exc}")
    finally:
        stop.set()
        thread.join(timeout=2)


def _run_assessment_batch(items: list[dict], job_id: str, totals: dict) -> None:
    from app.services.stock_screening import screen_universe

    stop = Event()

    def keep_alive() -> None:
        while not stop.wait(30):
            try:
                refresh_work.heartbeat_many(items)
                jobs.update_job(job_id)
            except Exception:
                return

    thread = Thread(target=keep_alive, daemon=True)
    thread.start()
    try:
        try:
            result = screen_universe(source_job_id=job_id, only_tickers=[item["ticker"] for item in items])
        except Exception as exc:
            for item in items:
                totals["failed"] += 1
                refresh_work.finish(
                    item, result={}, status="error", delay=retry_delay(item["attempts"]),
                    error=f"{type(exc).__name__}: {exc}",
                )
            return
        missing = set(result.get("missing_tickers", []))
        errors = {error["ticker"]: error["error"] for error in result.get("errors", [])}
        for item in items:
            ticker = item["ticker"]
            if ticker in errors:
                totals["failed"] += 1
                refresh_work.finish(
                    item, result={}, status="error", delay=retry_delay(item["attempts"]),
                    error=errors[ticker],
                )
            elif ticker in missing:
                totals["waiting_source"] += 1
                refresh_work.finish(
                    item, result={"complete": False, "reason": "Keine bewertbaren Kursdaten."},
                    status="waiting_source", delay=source_retry_delay(item),
                )
            else:
                refresh_work.finish(item, result={"complete": True}, status="current", delay=timedelta(days=3650))
    finally:
        stop.set()
        thread.join(timeout=2)
