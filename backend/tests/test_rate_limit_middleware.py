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
