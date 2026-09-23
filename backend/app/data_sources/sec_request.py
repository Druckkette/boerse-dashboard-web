"""One Redis-backed fair-access gate for SEC requests from all workers."""
import logging
import time
from collections.abc import Callable

import requests
from redis import Redis, RedisError

from app.core_config import get_settings
from app.data_sources.provider_guard import retry_seconds
from app.data_sources.provider_usage import record_provider_event


logger = logging.getLogger(__name__)
_RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('PEXPIRE', KEYS[1], 1000) end
return count
"""


class SecRequestError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str = "provider_error"):
        super().__init__(message)
        self.reason_code = reason_code


def sec_get(
    url: str, *, user_agent: str, timeout: int = 20, stream: bool = False,
    requester: Callable | None = None, headers: dict[str, str] | None = None,
) -> requests.Response:
    if not user_agent.strip():
        raise SecRequestError("SEC_USER_AGENT fehlt.", reason_code="provider_error")
    get = requester or requests.get
    client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.3, socket_timeout=0.3)
    try:
        for attempt in range(3):
            try:
                cooldown = client.ttl("provider-backoff:sec")
                if cooldown > 0:
                    raise SecRequestError(f"SEC-Pause noch {cooldown}s aktiv.", reason_code="rate_limited")
                while True:
                    second = int(time.time())
                    count = client.eval(_RATE_SCRIPT, 1, f"provider-rate:sec:{second}")
                    if count <= 5:
                        break
                    time.sleep(max(0.01, second + 1 - time.time()))
            except RedisError as exc:
                # Fail closed: independent worker-local limits cannot guarantee a global cap.
                raise SecRequestError("Gemeinsamer SEC-Rate-Guard nicht erreichbar.") from exc

            try:
                response = get(url, headers={**(headers or {}), "User-Agent": user_agent.strip(),
                                             "Accept-Encoding": "gzip, deflate"},
                               timeout=timeout, **({"stream": True} if stream else {}))
                record_provider_event("sec_requests")
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise SecRequestError(f"SEC-Verbindung: {type(exc).__name__}") from exc
            if response.status_code in {403, 429}:
                if response.status_code == 429:
                    record_provider_event("sec_429_count")
                seconds = retry_seconds(response.headers.get("Retry-After"), default=900)
                try:
                    client.set("provider-backoff:sec", "1", ex=seconds)
                except RedisError:
                    pass
                logger.warning("SEC HTTP %s; gemeinsamer Cooldown %ss", response.status_code, seconds)
                response.close()
                raise SecRequestError(f"SEC HTTP {response.status_code}; erneuter Versuch nach {seconds}s.",
                                      reason_code="rate_limited")
            if 500 <= response.status_code <= 599 and attempt < 2:
                response.close()
                time.sleep(0.5 * (2 ** attempt))
                continue
            return response
        raise SecRequestError("SEC-Abruf fehlgeschlagen.")
    finally:
        client.close()
