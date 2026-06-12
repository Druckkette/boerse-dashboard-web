from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core_config import get_settings
from app.middleware.rate_limit import InMemoryRateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Boerse Dashboard Web API",
        version="0.1.0",
        description="API-first scaffold for the Streamlit-to-web migration.",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.api_rate_limit_enabled:
        app.add_middleware(
            InMemoryRateLimitMiddleware,
            max_requests=settings.api_rate_limit_requests,
            window_seconds=settings.api_rate_limit_window_seconds,
        )
    app.add_middleware(
        RequestContextMiddleware,
        access_log_enabled=settings.api_access_log_enabled,
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
