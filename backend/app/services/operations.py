"""Small operational projection: no provider calls, secrets or personal notes."""
from datetime import UTC, datetime
from sqlalchemy import func, select
from app.db.models import AppSetting, Instrument, Job, Position, PriceBar, StockAssessmentSnapshot
from app.db.session import SessionLocal
from app.data_sources.provider_usage import usage_today
from app.services.market_calendar import completed_us_market_session


def operation_status():
    from app.workers.queue_health import monitor_queue_status
    now = datetime.now(UTC)
    session = completed_us_market_session(now).date
    with SessionLocal() as db:
        latest = db.scalar(select(Job).where(Job.job_type == "position_atr_monitor", Job.status == "done").order_by(Job.finished_at.desc().nullslast()).limit(1))
        count, oldest = db.execute(select(func.count(), func.min(Job.created_at)).where(Job.status == "queued")).one()
        active = db.execute(select(Job.job_type, Job.heartbeat_at).where(Job.status == "running").order_by(Job.heartbeat_at).limit(20)).all()
        total, current, oldest_calculation = db.execute(select(func.count(), func.count().filter(StockAssessmentSnapshot.as_of >= session), func.min(StockAssessmentSnapshot.as_of))).one()
        quotes = db.execute(select(Position.ticker, func.max(PriceBar.date)).outerjoin(Instrument, Instrument.ticker == Position.ticker).outerjoin(PriceBar, (PriceBar.instrument_id == Instrument.id) & PriceBar.close.is_not(None)).where(Position.is_open.is_(True)).group_by(Position.ticker).order_by(Position.ticker)).all()
        backup = db.get(AppSetting, "last_verified_backup")
        backup_value = {key: value for key, value in (backup.value_json or {}).items() if key in {"checked_at", "sha256", "check", "restore_tested_at"}} if backup else None
    return dict(generated_at=now.isoformat(), completed_session=session.isoformat(),
        monitor_last_success=latest.finished_at.isoformat() if latest and latest.finished_at else None,
        monitor_queue=monitor_queue_status(),
        queued=count, oldest_queued_at=oldest.isoformat() if oldest else None,
        oldest_queue_seconds=max(0, (now - oldest).total_seconds()) if oldest else None,
        active=[dict(type=kind, heartbeat_at=heartbeat.isoformat() if heartbeat else None, stale=heartbeat is None or (now - heartbeat).total_seconds() > 300) for kind, heartbeat in active],
        assessments=dict(total=total, current=current, oldest_session=oldest_calculation.isoformat() if oldest_calculation else None),
        position_quotes=[dict(ticker=ticker, as_of=stamp.isoformat() if stamp else None, current=stamp is not None and stamp >= session) for ticker, stamp in quotes],
        provider_usage=usage_today(), backup=backup_value,
        notes=["Technische Erreichbarkeit wird separat durch Readiness geprüft.", "Aktueller Kursstand allein bestätigt keine vollständige Datenabdeckung.", "Archivprüfung eines Backups ist kein erfolgreicher Wiederherstellungstest."])


def record_archive_check(digest: str):
    import re
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid SHA256")
    with SessionLocal() as db:
        row = db.get(AppSetting, "last_verified_backup")
        if row is None:
            row = AppSetting(key="last_verified_backup", description="Most recent backup archive catalogue verification")
            db.add(row)
        row.value_json = {"checked_at": datetime.now(UTC).isoformat(), "sha256": digest, "check": "pg_restore_catalogue"}
        db.commit()


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "--record-archive-check":
        raise SystemExit("Usage: python -m app.services.operations --record-archive-check SHA256")
    record_archive_check(sys.argv[2])
