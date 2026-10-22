"""Small index updates must not wait behind a full-universe refresh."""
from datetime import UTC, datetime, timedelta

from app.domain.market.constants import MARKET_INDEX_TICKERS
from app.services.market_calendar import expected_us_market_session
from app.workers.celery_app import celery_app
from app.workers.tasks.refresh_prices import refresh_prices


def index_refresh_due(now: datetime) -> bool:
    session = expected_us_market_session(now)
    return session.phase == "intraday" or (
        session.close_at is not None and timedelta(0) <= now - session.close_at <= timedelta(hours=2)
    )


@celery_app.task(name="refresh_market_indices", time_limit=180, soft_time_limit=150)
def refresh_market_indices() -> dict:
    if not index_refresh_due(datetime.now(UTC)):
        return {"skipped": True, "reason": "outside_market_window"}
    return refresh_prices.run(payload={
        "source": "scheduler", "scheduled_window": "market_indices_five_minutes",
        "tickers": [*MARKET_INDEX_TICKERS, "^VIX"], "include_market_helpers": False,
        "range": "1m", "incremental": True, "price_overlap_days": 7,
        "price_provider_timeout_seconds": 15,
    })
