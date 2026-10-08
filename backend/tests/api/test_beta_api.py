from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
import os
from types import SimpleNamespace

import fakeredis
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import ConnectionError

from app.beta_policy import RULES, beta_api_allowed, public_projection
from app.core_config import Settings
from app.domain.sell import service as sell_service
from app.main import create_app
from app.repositories import jobs as repository
from app.schemas import JobCreateRequest
from app.services import beta, jobs
from app.workers.tasks import refresh_stock_detail as worker
from tests.helpers.sell_fixture_data import fixture_positions, fixture_price_bars

SECRET = "test-beta-proxy-key-only-" + "x" * 32


@pytest.fixture
def setup(monkeypatch):
    # The same suite can exercise actual Redis Lua/locks using an isolated test instance.
    url = os.getenv("BETA_TEST_REDIS_URL")
    redis = Redis.from_url(url, decode_responses=True) if url else fakeredis.FakeRedis(decode_responses=True)
    redis.flushdb()
    settings = Settings(beta_proxy_secret=SECRET)
    monkeypatch.setattr(beta, "redis_client", lambda: redis)
    monkeypatch.setattr(beta, "get_settings", lambda: settings)
    monkeypatch.setattr("app.middleware.beta_access.get_settings", lambda: settings)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: redis)
    monkeypatch.setattr(repository, "_with_db", lambda operation, *, fallback: fallback())
    repository.clear_memory_jobs()
    calls = []
    monkeypatch.setattr(jobs.celery_app, "send_task", lambda *args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(id="test-task"))
    monkeypatch.setattr(beta.stocks.fundamentals_repository, "get_instrument_profile", lambda ticker: {"ticker": ticker})
    state = {"fresh": False}
    monkeypatch.setattr(beta, "stock_freshness", lambda ticker: {"ticker": ticker, "fresh": state["fresh"], "as_of": "2026-10-07"})
    client = TestClient(create_app())
    return SimpleNamespace(redis=redis, settings=settings, calls=calls, state=state, client=client,
                           headers={"x-beta-proxy-key": SECRET})


def refresh(setup, ticker="NVDA", mode="manual"):
    return setup.client.post(f"/api/v1/beta/stocks/{ticker}/refresh", json={"mode": mode}, headers=setup.headers)


def status(setup, reply, capability=None):
    headers = {**setup.headers, "x-beta-capability": capability if capability is not None else reply["capability"]}
    return setup.client.get(f"/api/v1/beta/stock-refresh/{reply['job_id']}/status", headers=headers)


@pytest.mark.parametrize("headers", [{}, {"x-beta-proxy-key": "browser-role-beta"}])
def test_internal_beta_api_requires_server_credential(setup, headers):
    response = setup.client.get("/api/v1/beta/home", headers=headers)
    assert response.status_code == 403
    assert not setup.calls


@pytest.mark.parametrize("method,path", [
    ("GET", "home"), ("GET", "portfolio/snapshot"), ("GET", "workspace"),
    ("GET", "sell/positions/ranking"), ("POST", "sell/preview"), ("GET", "sell/NVDA/manual"),
    ("POST", "sell/NVDA/evaluate"), ("GET", "jobs"), ("POST", "jobs"),
    ("POST", "jobs/job_private/cancel"), ("GET", "settings"), ("GET", "setup"),
    ("GET", "stocks/NVDA/report.pdf"), ("GET", "stocks/screening/export"),
    ("GET", "stocks/institutional/13f/mappings"), ("PATCH", "stocks/NVDA/fundamentals"),
    ("GET", "industry-groups/rs/diagnostics"), ("GET", "industry-groups/review"), ("POST", "industry-groups/manual-override"),
    ("GET", "market/universe/mappings"), ("GET", "unknown"),
    ("POST", "stocks/NVDA/prices/refresh"), ("GET", "trade-journal/trades"),
])
def test_private_and_unknown_endpoints_are_denied_before_execution(setup, method, path):
    response = setup.client.request(method, "/api/v1/" + path, headers=setup.headers)
    assert response.status_code == 403
    assert not setup.calls


def test_shared_allowlist_covers_each_explicit_public_analysis():
    for rule in RULES:
        path = rule["path"].replace("{ticker}", "NVDA").replace("{group}", "software").replace("{job}", "beta_" + "a" * 32)
        assert beta_api_allowed(rule["method"], path)
        assert not beta_api_allowed("DELETE", path)
        assert not beta_api_allowed(rule["method"], path, "private=true")
    assert not beta_api_allowed("GET", "stocks/../portfolio/assessment")
    assert not beta_api_allowed("GET", "stocks/%2Fportfolio/assessment")
    assert not beta_api_allowed("GET", "stocks/search", "q=" + "x" * 401)


def test_fresh_stock_auto_does_not_enqueue(setup):
    setup.state["fresh"] = True
    response = refresh(setup, mode="auto")
    assert response.status_code == 200
    assert response.json()["status"] == "current"
    assert not setup.calls


@pytest.mark.parametrize("mode", ["manual", "auto"])
def test_targeted_refresh_uses_fixed_payload_existing_queue_low_priority(setup, mode):
    response = refresh(setup, mode=mode)
    assert response.status_code == 200
    reply = response.json()
    args, options = setup.calls[0]
    assert args == ("refresh_stock_detail",)
    assert options["queue"] == "interactive"
    assert options["priority"] == 9
    payload = options["args"][1]
    assert payload == {"ticker": "NVDA", "range": "2y", "benchmark_ticker": "SPY", "include_prices": True,
                       "include_fundamentals": True, "include_rs": True, "include_13f": False,
                       "incremental": True, "source": "beta", "refresh_assessment": True}
    assert reply["job_id"].startswith("beta_")
    assert options["args"][0] not in json.dumps(reply)
    assert status(setup, reply).json()["status"] == "queued"


def test_concurrent_identical_refreshes_are_coalesced(setup):
    # Exercise the real service/mutex concurrently, avoiding TestClient loop ownership.
    def call():
        for _ in range(40):
            try:
                return beta.refresh_stock("NVDA", "manual")
            except HTTPException as exc:
                if exc.status_code != 429:
                    raise
                import time
                time.sleep(.01)
        pytest.fail("Concurrent refresh did not join")
    with ThreadPoolExecutor(max_workers=6) as pool:
        replies = list(pool.map(lambda _: call(), range(6)))
    assert len(setup.calls) == 1
    assert len({reply["job_id"] for reply in replies}) == 1
    assert len({reply["capability"] for reply in replies}) == 1


def test_existing_private_ticker_job_can_only_be_observed_through_scoped_handle(setup):
    job = jobs.start_job(JobCreateRequest(type="refresh_stock_detail", payload={"ticker": "NVDA"}))
    reply = refresh(setup).json()
    assert reply["joined"] is True
    assert len(setup.calls) == 1
    assert job.job_id not in json.dumps(reply)
    assert status(setup, reply, "wrong").status_code == 404
    assert setup.client.get(f"/api/v1/jobs/{job.job_id}", headers=setup.headers).status_code == 403


def test_cooldown_global_capacity_and_private_admission_priority(setup):
    reply = refresh(setup).json()
    assert refresh(setup, "AAPL").status_code == 429
    record = beta._load_record(setup.redis, reply["job_id"])
    repository.mark_done(record["internal_id"])
    assert status(setup, reply).json()["finished"] is True
    assert refresh(setup).status_code == 429
    # Auto attempts remain suppressed even when the manual cooldown expires.
    setup.redis.delete("beta:cooldown:NVDA")
    assert refresh(setup, mode="auto").status_code == 429
    repository.create_job("refresh_stock_assessments", {})
    assert refresh(setup, "AAPL").status_code == 429
    assert len(setup.calls) == 1


def test_failure_status_does_not_leak_provider_keys_payloads_or_logs(setup):
    reply = refresh(setup).json()
    record = beta._load_record(setup.redis, reply["job_id"])
    repository.mark_failed(record["internal_id"], error_message="API_KEY=private-secret password postgres",
                           result={"portfolio": {"entry_price": 12345}, "log": "private"})
    result = status(setup, reply)
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "failed"
    assert data["finished"]
    assert data["error"]
    assert set(data) == {"job_id", "ticker", "status", "progress", "finished", "error"}
    assert "private" not in result.text


def test_progress_completion_invalidates_read_cache(setup):
    reply = refresh(setup).json()
    record = beta._load_record(setup.redis, reply["job_id"])
    old = beta.cache_key(setup.redis, "stocks/NVDA/assessment", "")
    repository.update_progress(record["internal_id"], progress=58, step="private step", message="internal")
    data = status(setup, reply).json()
    assert data["progress"] == 58
    assert "step" not in data
    repository.mark_done(record["internal_id"])
    assert status(setup, reply).json()["status"] == "done"
    assert beta.cache_key(setup.redis, "stocks/NVDA/assessment", "") != old
    assert not setup.redis.hgetall("beta:active")


def test_expired_capability_and_foreign_job_ids_are_denied(setup):
    reply = refresh(setup).json()
    setup.redis.delete(f"beta:refresh:{reply['job_id']}")
    assert status(setup, reply).status_code == 404
    assert setup.client.get("/api/v1/beta/stock-refresh/beta_" + "a" * 32 + "/status", headers=setup.headers).status_code == 404


@pytest.mark.parametrize("body", [{"type": "refresh_universe"}, {"mode": "auto", "payload": {"tickers": ["NVDA", "AAPL"]}}, {"mode": "other"}])
def test_job_type_and_payload_cannot_be_chosen(setup, body):
    assert setup.client.post("/api/v1/beta/stocks/NVDA/refresh", json=body, headers=setup.headers).status_code == 422
    assert not setup.calls


def test_invalid_and_unknown_tickers_are_rejected(setup, monkeypatch):
    assert refresh(setup, "BAD!TICKER").status_code == 403
    monkeypatch.setattr(beta.stocks.fundamentals_repository, "get_instrument_profile", lambda ticker: None)
    assert refresh(setup, "UNKNOWN").status_code == 404
    assert not setup.calls


def test_flooding_and_large_requests_are_bounded(setup):
    setup.settings.beta_refresh_requests_per_minute = 2
    assert refresh(setup).status_code == 200
    assert refresh(setup).status_code == 200
    assert refresh(setup).status_code == 429
    large = setup.client.post("/api/v1/beta/sell/preview", content="x" * 4097, headers=setup.headers)
    assert large.status_code == 413
    assert len(setup.calls) == 1


def test_redis_failure_fails_closed_without_job(setup, monkeypatch):
    def unavailable():
        raise ConnectionError("secret internal host")
    monkeypatch.setattr(beta, "redis_client", unavailable)
    response = refresh(setup)
    assert response.status_code == 503
    assert "secret" not in response.text
    assert not setup.calls


def test_anonymous_cache_reuses_market_only_data_and_strips_operational_summary(setup, monkeypatch):
    calls = []
    monkeypatch.setattr(beta, "home_dashboard", lambda: calls.append(1) or {
        "market": {"indices": []}, "opportunities": [], "industry_groups": [], "source_job_id": "private"})
    for _ in range(2):
        response = setup.client.get("/api/v1/beta/home", headers=setup.headers)
        assert response.status_code == 200
        assert "private" not in response.text
    assert calls == [1]
    assert all("entry_price" not in key for key in setup.redis.scan_iter())
    assert public_projection({"summary": {"source_job_id": "private", "error_message": "secret", "records_written": 5}}) == {"summary": {"records_written": 5}}


def test_beta_home_does_not_read_personal_sources(monkeypatch):
    from app.services import home, daily_opportunities
    from app.repositories import industry_group_rs as industry_groups
    for obj, name in [(home, "get_workspace_state"), (home, "_portfolio_summary"),
                      (home, "get_data_quality_summary"), (home.sell_state_repository, "list_ranking_snapshot")]:
        monkeypatch.setattr(obj, name, lambda *a, **kw: pytest.fail("private home source queried"))
    monkeypatch.setattr(home, "_market_summary", lambda: {"indices": [], "as_of": "2026-10-07"})
    monkeypatch.setattr(daily_opportunities, "get_top_daily", lambda: {"rows": []})
    monkeypatch.setattr(industry_groups, "list_home_rankings", lambda **kw: (None, []))
    assert set(beta.home_dashboard()) == {"generated_at", "market", "opportunities", "industry_groups", "industry_groups_as_of"}


@pytest.fixture
def sell_data(monkeypatch):
    # NVDA is deliberately also present in the private fixture portfolio. Its purchase
    # price/shares, custom stops, tranche history and recommendation state must not be read.
    assert fixture_positions()[0].ticker == "NVDA"
    monkeypatch.setattr(sell_service.prices_repository, "list_price_bars", fixture_price_bars)
    monkeypatch.setattr(sell_service, "yahoo_quote_currency", lambda ticker: "USD")
    monkeypatch.setattr(sell_service, "cached_currency_usd_factor", lambda currency: {"USD": 1., "EUR": 1.2, "GBP": 1.3, "CHF": 1.1, "CAD": .7, "JPY": .006, "HKD": .12, "AUD": .65}[currency])
    for obj in [sell_service.portfolio_repository, sell_service.sell_state_repository]:
        for name in dir(obj):
            if name.startswith(("list_", "get_", "upsert_", "save_", "create_", "update_", "append_")) and callable(getattr(obj, name)):
                monkeypatch.setattr(obj, name, lambda *a, **kw: pytest.fail("personal repository accessed by preview"))


@pytest.mark.parametrize("ticker", ["NVDA", "NO_POSITION"])
@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP", "CHF", "CAD", "JPY", "HKD", "AUD"])
def test_preview_uses_only_form_entry_and_market_cache_without_personal_reads_or_writes(setup, sell_data, ticker, currency):
    # Valid stock identifiers, including a stock absent from the real portfolio.
    ticker = "TEST" if ticker == "NO_POSITION" else ticker
    payload = {"ticker": ticker, "buy_price": 31.25, "buy_date": "2026-02-02", "currency": currency}
    response = setup.client.post("/api/v1/beta/sell/preview", json=payload, headers=setup.headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["metrics"]["raw_payload"] == {"ticker": ticker, "buy_date": "2026-02-02", "buy_price": 31.25, "currency": currency}
    assert data["evaluation"]["emergency_features"]
    assert data["evaluation"]["offensive_features"]
    assert data["evaluation"]["defensive_features"]
    assert "manual" not in data["evaluation"]
    assert "tranche_log" not in data["evaluation"]
    assert "next_recommendation_state" not in data["evaluation"]
    assert not setup.calls
    assert not any("31.25" in (setup.redis.get(key) or "") for key in setup.redis.scan_iter("beta:cache:*"))


@pytest.mark.parametrize("change", [{"buy_price": -1}, {"buy_price": "Infinity"}, {"currency": "INVALID"},
                                     {"buy_date": "2999-01-01"}, {"buy_date": "not-date"},
                                     {"ticker": "../NVDA"}, {"shares": 99}, {"buy_price": 0}])
def test_preview_rejects_invalid_input_and_extra_personal_fields(setup, change):
    payload = {"ticker": "NVDA", "buy_price": 31.25, "buy_date": "2026-02-02", "currency": "USD", **change}
    response = setup.client.post("/api/v1/beta/sell/preview", json=payload, headers=setup.headers)
    assert response.status_code == 422
    assert not setup.calls


def test_preview_rate_and_concurrency_limits(setup, sell_data):
    payload = {"ticker": "NVDA", "buy_price": 31.25, "buy_date": "2026-02-02", "currency": "USD"}
    setup.redis.zadd("beta:preview-active", {"other-calculation": datetime.now(UTC).timestamp() + 60})
    assert setup.client.post("/api/v1/beta/sell/preview", json=payload, headers=setup.headers).status_code == 429
    setup.redis.delete("beta:preview-active")
    setup.settings.beta_preview_requests_per_minute = 1
    assert setup.client.post("/api/v1/beta/sell/preview", json=payload, headers=setup.headers).status_code == 429


def test_worker_recomputes_only_the_requested_stock_after_refresh(setup, monkeypatch):
    for name in ("refresh_price_cache_for_ticker", "refresh_relative_strength_line_for_ticker", "refresh_fundamentals_for_ticker"):
        monkeypatch.setattr(worker, name, lambda *a, **kw: {"ok": True, "records_written": 1})
    calls = []
    monkeypatch.setattr("app.services.stock_screening.screen_universe", lambda **kw: calls.append(kw) or {"ok": True, "records_written": 1})
    reply = refresh(setup).json()
    record = beta._load_record(setup.redis, reply["job_id"])
    job = repository.get_job(record["internal_id"])
    result = worker.refresh_stock_detail.run(job.job_id, job.payload)
    assert result["ok"]
    assert calls == [{"source_job_id": job.job_id, "only_tickers": ["NVDA"]}]
    assert status(setup, reply).json()["status"] == "done"


def test_worker_provider_failure_preserves_error_projection(setup, monkeypatch):
    for name in ("refresh_price_cache_for_ticker", "refresh_relative_strength_line_for_ticker", "refresh_fundamentals_for_ticker"):
        monkeypatch.setattr(worker, name, lambda *a, **kw: {"ok": False, "error_message": "secret-provider-key"})
    reply = refresh(setup).json()
    record = beta._load_record(setup.redis, reply["job_id"])
    job = repository.get_job(record["internal_id"])
    worker.refresh_stock_detail.run(job.job_id, job.payload)
    response = status(setup, reply)
    assert response.json()["status"] == "failed"
    assert "secret-provider" not in response.text


def test_heavy_read_admission_is_bounded_but_cached_data_remains_available(setup, monkeypatch):
    monkeypatch.setattr(beta, "home_dashboard", lambda: {"market": {"indices": []}})
    assert setup.client.get("/api/v1/beta/home", headers=setup.headers).status_code == 200
    now = datetime.now(UTC).timestamp()
    setup.redis.zadd("beta:read-active", {"one": now + 60, "two": now + 60})
    # Cached results consume no calculation slot.
    assert setup.client.get("/api/v1/beta/home", headers=setup.headers).status_code == 200
    assert setup.client.get("/api/v1/beta/stocks/NVDA/freshness", headers=setup.headers).status_code == 429


def test_private_dispatch_is_not_repeated_when_mutex_release_fails(setup, monkeypatch):
    class Lock:
        def acquire(self):
            return True
        def owned(self):
            return True
        def release(self):
            raise ConnectionError("redis failed after dispatch")
    monkeypatch.setattr(setup.redis, "lock", lambda *a, **kw: Lock())
    job = jobs.start_job(JobCreateRequest(type="refresh_stock_detail", payload={"ticker": "NVDA"}))
    assert job.status == "queued"
    assert len(setup.calls) == 1


def test_dynamic_policy_does_not_admit_private_static_backend_routes():
    explicit = {(rule["method"], "/api/v1/" + rule["path"]) for rule in RULES if "{" not in rule["path"]}
    for route in create_app().routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/") or "{" in path:
            continue
        for method in getattr(route, "methods", set()):
            allowed = beta_api_allowed(method, path.removeprefix("/api/v1/"))
            assert allowed == ((method, path) in explicit), (method, path)


def test_beta_admission_never_reconciles_or_modifies_unrelated_job_states(setup, monkeypatch):
    monkeypatch.setattr(repository, "reconcile_stale_jobs", lambda: pytest.fail("beta must not modify unrelated jobs"))
    assert refresh(setup).status_code == 200


def test_expired_running_status_can_only_be_renewed_by_ticker_admission(setup):
    first = refresh(setup).json()
    setup.redis.delete(f"beta:refresh:{first['job_id']}")
    assert status(setup, first).status_code == 404
    renewed = refresh(setup).json()
    assert renewed["joined"] is True
    assert renewed["job_id"] != first["job_id"]
    assert len(setup.calls) == 1
    assert status(setup, renewed).status_code == 200
    assert status(setup, renewed, first["capability"]).status_code == 404
