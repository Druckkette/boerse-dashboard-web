from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_context import RequestContextMiddleware


def test_request_context_adds_request_id_header() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/ping")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_request_context_preserves_clean_incoming_request_id() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/ping", headers={"X-Request-ID": "nas-debug-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "nas-debug-123"
