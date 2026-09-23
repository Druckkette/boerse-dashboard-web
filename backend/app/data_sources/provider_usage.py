"""Best-effort provider counters, shared by workers and attached to job results."""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from redis import Redis, RedisError

from app.core_config import get_settings


METRICS = (
    "sec_requests", "sec_bulk_downloads", "sec_429_count", "yahoo_requests",
    "fmp_requests", "fmp_429_count", "cache_hits", "fallback_used",
)
_current: ContextVar[Counter | None] = ContextVar("provider_usage", default=None)


@contextmanager
def capture_provider_usage():
    counts: Counter = Counter()
    token = _current.set(counts)
    try:
        yield counts
    finally:
        _current.reset(token)


def record_provider_event(metric: str, amount: int = 1) -> None:
    if metric not in METRICS or amount <= 0:
        return
    counts = _current.get()
    if counts is not None:
        counts[metric] += amount
    day = datetime.now(UTC).strftime("%Y%m%d")
    try:
        client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
        try:
            pipe = client.pipeline()
            pipe.incrby(f"provider-usage:{day}:{metric}", amount)
            pipe.expire(f"provider-usage:{day}:{metric}", 8 * 86400)
            pipe.execute()
        finally:
            client.close()
    except RedisError:
        pass


def usage_today() -> dict[str, int]:
    day = datetime.now(UTC).strftime("%Y%m%d")
    try:
        client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
        try:
            values = client.mget([f"provider-usage:{day}:{metric}" for metric in METRICS])
        finally:
            client.close()
        return {metric: int(value or 0) for metric, value in zip(METRICS, values)}
    except RedisError:
        return {metric: 0 for metric in METRICS}


def current_provider_usage() -> dict[str, int]:
    return dict(_current.get() or {})
