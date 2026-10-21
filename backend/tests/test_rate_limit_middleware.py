from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.rate_limit import InMemoryRateLimitMiddleware


def test_rate_limit_returns_429_after_limit() -> None:
    app = FastAPI()
    app.add_middleware(InMemoryRateLimitMiddleware, max_requests=2, window_seconds=60)

    @app.get("/api/v1/protected")
    def protected() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/api/v1/protected").status_code == 200
    assert client.get("/api/v1/protected").status_code == 200
    response = client.get("/api/v1/protected")

    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded."
    assert response.headers["Retry-After"]


def test_rate_limit_exempts_health_endpoint() -> None:
    app = FastAPI()
    app.add_middleware(InMemoryRateLimitMiddleware, max_requests=1, window_seconds=60)

    @app.get("/api/v1/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)

    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200


def test_client_cannot_get_new_budgets_using_forwarding_headers():
    app = FastAPI()
    app.add_middleware(InMemoryRateLimitMiddleware, max_requests=2, window_seconds=60)
    @app.get("/probe")
    def probe():
        return {"ok": True}
    client = TestClient(app)
    statuses = [client.get("/probe", headers={"X-Forwarded-For": f"203.0.113.{i}", "X-Real-IP": f"203.0.113.{i}"}).status_code for i in range(10)]
    assert statuses == [200, 200] + [429] * 8


def test_inactive_client_keys_expire_without_evicting_active_budgets(monkeypatch):
    from app.middleware import rate_limit
    from starlette.requests import Request
    import asyncio
    now = [100.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    middleware = InMemoryRateLimitMiddleware(FastAPI(), max_requests=1, window_seconds=60, max_clients=1)
    async def next_response(request):
        from starlette.responses import Response
        return Response()
    def call(host):
        request = Request({"type": "http", "method": "GET", "path": "/probe", "headers": [], "client": (host, 1234)})
        return asyncio.run(middleware.dispatch(request, next_response)).status_code
    assert call("192.0.2.1") == 200
    assert call("192.0.2.2") == 429
    assert call("192.0.2.1") == 429
    now[0] = 161
    assert call("192.0.2.2") == 200
    assert list(middleware._requests) == ["192.0.2.2"]
