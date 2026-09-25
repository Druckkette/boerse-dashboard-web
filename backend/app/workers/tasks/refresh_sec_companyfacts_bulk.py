"""Nightly SEC bulk refresh on the shared backend cache volume."""
from app.core_config import get_settings
from app.data_sources.sec_companyfacts_cache import refresh_companyfacts_bulk_cache
from app.data_sources.sec_submissions_cache import refresh_submissions_bulk_cache
from app.services.settings import get_runtime_config_value
from app.workers.celery_app import celery_app


@celery_app.task(name="refresh_sec_companyfacts_bulk", soft_time_limit=7000, time_limit=7200)
def refresh_sec_companyfacts_bulk() -> dict:
    agent = get_runtime_config_value("SEC_USER_AGENT") or get_settings().sec_user_agent
    if not agent:
        return {"ok": False, "reason_code": "waiting_sec_data", "error": "SEC_USER_AGENT fehlt"}

    companyfacts = refresh_companyfacts_bulk_cache(agent)
    submissions = refresh_submissions_bulk_cache(agent)
    return {
        "ok": bool(companyfacts.get("available")),
        **companyfacts,
        "submissions": submissions,
    }
