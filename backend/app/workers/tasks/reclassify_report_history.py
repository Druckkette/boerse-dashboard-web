"""Manual one-time maintenance task; each batch is restartable by cursor."""
from app.services.report_reclassification import problem_counts, reclassify_batch
from app.workers.celery_app import celery_app


@celery_app.task(name="reclassify_report_history")
def reclassify_report_history(after_ticker: str = "", limit: int = 250) -> dict:
    before = problem_counts() if not after_ticker else None
    result = reclassify_batch(after_ticker=after_ticker, limit=limit)
    result["before"] = before
    result["after"] = problem_counts()
    return result
