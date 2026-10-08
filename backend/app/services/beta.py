"""Anonymous beta admission. Redis stores only expiring technical records, never entries."""
from __future__ import annotations

import secrets
import time
from contextlib import contextmanager
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from redis import Redis
from redis.exceptions import LockError, RedisError

from app.core_config import get_settings
from app.repositories import jobs as job_repository
from app.schemas import JobCreateRequest, TopDailyStockItem
from app.services import jobs, stocks

BUSY = "Die Aktualisierung ist derzeit ausgelastet. Bitte später erneut versuchen."
TERMINAL = {"done", "failed", "skipped", "cancelled"}


def redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True,
                          socket_connect_timeout=1, socket_timeout=2)


@contextmanager
def protection():
    try:
        yield redis_client()
    except (RedisError, LockError) as exc:
        raise HTTPException(503, "Beta-Schutz derzeit nicht verfügbar. Bitte später erneut versuchen.") from exc


def rate_limit(client: Redis, kind: str, maximum: int) -> None:
    # Redis TIME avoids frontend clock differences. Atomic counter+expiry, global;
    # no IP addresses, accounts, cookies, fingerprints or form values are stored.
    key = f"beta:rate:{kind}:{int(client.time()[0]) // 60}"
    count = client.eval("""
        local n = redis.call('INCR', KEYS[1])
        if n == 1 then redis.call('EXPIRE', KEYS[1], 65) end
        return n
    """, 1, key)
    if int(count) > maximum:
        raise HTTPException(429, "Zu viele Beta-Anfragen. Bitte in einer Minute erneut versuchen.",
                            headers={"Retry-After": "60"})


def acquire_compute_slot(client: Redis, kind: str, maximum: int) -> str:
    lease = uuid4().hex
    now = time.time()
    allowed = client.eval("""
        redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
        if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then return 0 end
        redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4]); redis.call('EXPIRE', KEYS[1], 120)
        return 1
    """, 1, f"beta:{kind}-active", now, maximum, now + 120, lease)
    if not allowed:
        raise HTTPException(429, "Die Beta ist derzeit ausgelastet. Bitte kurz warten.",
                            headers={"Retry-After": "5"})
    return lease


def stock_freshness(ticker: str) -> dict:
    assessment = stocks.get_stock_assessment(ticker)
    quality = assessment.data_quality
    # Institutional updates remain scheduler-owned; this job can repair these dependencies.
    needed = ("prices", "fundamentals", "rs_line")
    refresh_needed = assessment.source == "missing" or any(
        quality.get(key, {}).get("status") != "fresh" for key in needed
    )
    fresh = not refresh_needed and all(item.get("status") == "fresh" for item in quality.values())
    return {"ticker": ticker, "fresh": fresh, "refresh_needed": refresh_needed, "as_of": assessment.as_of,
            "dependencies": {key: {field: item.get(field) for field in ("status", "as_of", "label")}
                             for key, item in quality.items()}}


def _load_record(client: Redis, handle: str) -> dict | None:
    import json
    raw = client.get(f"beta:refresh:{handle}")
    return json.loads(raw) if raw else None


def _job_for_record(record: dict):
    job = jobs.get_job(record["internal_id"])
    if not job or job.job_type != "refresh_stock_detail":
        raise HTTPException(503, BUSY)  # Unknown jobs never silently release capacity.
    tickers = jobs._stock_detail_tickers(job.payload)
    if tickers != [record["ticker"]]:
        raise HTTPException(404, "Aktualisierung nicht verfügbar.")
    return job


def _public_status(record: dict, job) -> dict:
    return {"job_id": record["handle"], "ticker": record["ticker"], "status": job.status,
            "progress": max(0, min(100, job.progress)), "finished": job.status in TERMINAL,
            "error": "Die Daten konnten nicht vollständig aktualisiert werden. Bitte später erneut versuchen."
            if job.status == "failed" else None}


def _register(client: Redis, ticker: str, job, *, owned: bool) -> dict:
    import json
    settings = get_settings()
    handle = f"beta_{uuid4().hex}"
    token = secrets.token_urlsafe(32)
    record = {"handle": handle, "internal_id": job.job_id, "ticker": ticker,
              "token": token, "owned": owned}
    client.set(f"beta:refresh:{handle}", json.dumps(record), ex=settings.beta_status_ttl_seconds)
    # Active records remain until confirmed terminal. Unknown/expired state is fail-closed.
    client.hset("beta:active", ticker, json.dumps(record))
    return record


def _reconcile(client: Redis) -> None:
    import json
    for ticker, raw in client.hgetall("beta:active").items():
        record = json.loads(raw)
        job = _job_for_record(record)
        if job.status in TERMINAL:
            client.hdel("beta:active", ticker)
            client.incr("beta:cache-version")


def refresh_stock(ticker: str, mode: str) -> dict:
    import json
    settings = get_settings()
    with protection() as client:
        rate_limit(client, "refresh", settings.beta_refresh_requests_per_minute)
        lock = client.lock("beta:admission", timeout=120, blocking_timeout=5)
        if not lock.acquire(blocking=True):
            raise HTTPException(429, "Diese Aktie wird bereits geprüft. Bitte kurz warten.",
                                headers={"Retry-After": "5"})
        try:
            _reconcile(client)
            raw = client.hget("beta:active", ticker)
            if raw:
                record = json.loads(raw)
                job = _job_for_record(record)
                # Re-authorize an expired status grant only through ticker admission,
                # never by allowing the caller to select an underlying job ID.
                if not _load_record(client, record["handle"]):
                    record = _register(client, ticker, job, owned=record["owned"])
                return {**_public_status(record, job), "capability": record["token"], "joined": True}
            if not stocks.fundamentals_repository.get_instrument_profile(ticker):
                raise HTTPException(404, "Aktie nicht im gemeinsamen Datenbestand gefunden.")
            freshness = stock_freshness(ticker)
            if mode == "auto" and not freshness.get("refresh_needed", not freshness["fresh"]):
                return {"ticker": ticker, "status": "current" if freshness["fresh"] else "limited",
                        "finished": True, "fresh": freshness["fresh"]}
            # A private refresh is adopted only through this ticker-specific admission;
            # its real ID, payload, steps and logs never leave the backend.
            active = job_repository.list_active_jobs(reconcile_stale=False)
            suitable = next((job for job in active if job.job_type == "refresh_stock_detail"
                             and jobs._stock_detail_tickers(job.payload) == [ticker]), None)
            if suitable:
                record = _register(client, ticker, suitable, owned=False)
                return {**_public_status(record, suitable), "capability": record["token"], "joined": True}
            if client.exists(f"beta:cooldown:{ticker}") or (mode == "auto" and client.exists(f"beta:auto:{ticker}")):
                raise HTTPException(429, "Diese Aktie wurde kürzlich geprüft. Bitte später erneut versuchen.",
                                    headers={"Retry-After": str(settings.beta_refresh_cooldown_seconds)})
            owned = sum(json.loads(value)["owned"] for value in client.hvals("beta:active"))
            if max(owned, sum(job.requested_by == "beta" for job in active)) >= settings.beta_refresh_max_active:
                raise HTTPException(429, BUSY, headers={"Retry-After": "60"})
            private = [job for job in active if job.requested_by != "beta"]
            if any(job.job_type == "refresh_stock_detail" for job in private) or (
                settings.beta_pause_when_private_busy and private
            ):
                raise HTTPException(429, BUSY, headers={"Retry-After": "60"})
            if not lock.owned():
                raise HTTPException(503, BUSY)
            payload = {"ticker": ticker, "range": "2y", "benchmark_ticker": "SPY",
                       "include_prices": True, "include_fundamentals": True,
                       "include_rs": True, "include_13f": False, "incremental": True,
                       "source": "beta", "refresh_assessment": True}
            # Reserve before dispatch: a partial failure must not allow enqueue flooding.
            client.set(f"beta:cooldown:{ticker}", "1", ex=settings.beta_refresh_cooldown_seconds)
            client.set(f"beta:auto:{ticker}", "1", ex=settings.beta_auto_cooldown_seconds)
            job = jobs.start_job(JobCreateRequest(type="refresh_stock_detail", payload=payload, requested_by="beta"))
            record = _register(client, ticker, job, owned=job.requested_by == "beta")
            return {**_public_status(record, job), "capability": record["token"], "joined": False}
        finally:
            if lock.owned():
                lock.release()


def refresh_status(handle: str, capability: str) -> dict:
    with protection() as client:
        record = _load_record(client, handle)
        if not record or not secrets.compare_digest(record["token"].encode(), capability.encode()):
            raise HTTPException(404, "Aktualisierung nicht verfügbar oder Berechtigung abgelaufen.")
        job = _job_for_record(record)
        if job.status in TERMINAL and client.hget("beta:active", record["ticker"]):
            # Only delete our handle, never a newer refresh for this ticker.
            client.eval("""
                local value = redis.call('HGET', KEYS[1], ARGV[1])
                if value and cjson.decode(value).handle == ARGV[2] then
                  redis.call('HDEL', KEYS[1], ARGV[1]); redis.call('INCR', KEYS[2])
                end
            """, 2, "beta:active", "beta:cache-version", record["ticker"], handle)
        return _public_status(record, job)


def preview_sell(payload):
    from app.domain.sell.service import preview_manual_sell_decision
    from app.domain.sell.service import SellMarketDataUnavailableError
    settings = get_settings()
    with protection() as client:
        rate_limit(client, "preview", settings.beta_preview_requests_per_minute)
        # Expiring distributed leases; no form input or result is stored.
        lease = acquire_compute_slot(client, "preview", settings.beta_preview_max_active)
        try:
            result = preview_manual_sell_decision(payload)
            # Only display data. Personal/manual configuration and state are not part of this API.
            return {"metrics": result.metrics.model_dump(mode="json", include={
                        "ticker": True, "as_of": True, "current_price": True, "pnl_pct": True, "raw_payload": {
                            "ticker", "buy_date", "buy_price", "currency"}}),
                    "evaluation": result.evaluation.model_dump(mode="json", include={
                        "ticker", "display_label", "recommendation_label", "sell_now_percent",
                        "recommendation_percent", "explanation_short", "stop_price",
                        "next_tranche_trigger_price", "full_exit_price", "killer_signals",
                        "tranche_signals", "warning_signals", "watch_signals",
                        "emergency_features", "offensive_features", "defensive_features"})}
        except SellMarketDataUnavailableError as exc:
            raise HTTPException(409, "Kursverlauf oder Wechselkurs fehlt für diese Prüfung. Bitte Aktie aktualisieren.") from exc
        finally:
            client.zrem("beta:preview-active", lease)


def home_dashboard() -> dict:
    from datetime import UTC, datetime
    from app.services.home import _market_summary, _read
    from app.services import daily_opportunities
    from app.services.industry_group_rs import TAXONOMY_VERSION, ALGORITHM_VERSION
    from app.repositories import industry_group_rs as industry_groups
    errors = []
    market = _read("market", _market_summary, errors, {"indices": []})
    top = _read("opportunities", daily_opportunities.get_top_daily, errors, {"rows": []})
    group_date, groups = _read("industry_groups", lambda: industry_groups.list_home_rankings(
        taxonomy_version=TAXONOMY_VERSION, algorithm_version=ALGORITHM_VERSION, limit=5), errors, (None, []))
    return {"generated_at": datetime.now(UTC).isoformat(), "market": market,
            "opportunities": [TopDailyStockItem.model_validate(row).model_dump(mode="json") for row in top["rows"][:3]],
            "industry_groups": [{key: row.get(key) for key in (
                "code", "name", "rank", "rs_score", "rank_change_20d")} for row in groups],
            "industry_groups_as_of": group_date.isoformat() if group_date else None}


def cache_key(client: Redis, path: str, query: str) -> str:
    version = client.get("beta:cache-version") or "0"
    return "beta:cache:" + sha256(f"{version}:{path}?{query}".encode()).hexdigest()
