"""Shared FMP backoff for background reports, without persisting credentials."""
import hashlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import requests
from redis import Redis, RedisError

from app.core_config import get_settings
from app.data_sources.provider_usage import record_provider_event


def retry_seconds(value: str | None, default: int = 900) -> int:
    try:
        seconds = int(value or "")
    except ValueError:
        try:
            seconds = int((parsedate_to_datetime(value).astimezone(UTC) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            seconds = default
    return max(1, min(seconds, 86400))


def guarded_fmp_get(url: str, *, params: dict, timeout: int):
    fingerprint = hashlib.sha256(str(params.get("apikey", "")).encode()).hexdigest()[:24]
    client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
    global_key = f"provider-backoff:fmp:{fingerprint}"
    endpoint_key = global_key + ":" + url.rsplit("/", 1)[-1]
    try:
        try:
            remaining = max(client.ttl(global_key), client.ttl(endpoint_key))
        except RedisError:
            remaining = 900  # fail closed: all workers must share the FMP cooldown
        if remaining > 0:
            response = requests.Response()
            response.status_code = 429
            response._content = b'Provider cooldown active; other sources remain available.'
            response.headers["Retry-After"] = str(remaining)
            return response
        response = requests.get(url, params=params, timeout=timeout)
        record_provider_event("fmp_requests")
        if response.status_code == 429:
            record_provider_event("fmp_429_count")
        if response.status_code in {401, 403, 429}:
            seconds = retry_seconds(getattr(response, "headers", {}).get("Retry-After"),
                                    86400 if response.status_code == 429 else 21600)
            if response.status_code == 429:
                seconds = max(1800, seconds)
            # A tariff restriction on one endpoint need not block all other endpoints.
            key = endpoint_key if response.status_code == 403 else global_key
            try:
                client.set(key, "1", ex=seconds)
            except RedisError:
                pass
        return response
    finally:
        client.close()
