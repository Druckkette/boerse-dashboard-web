from datetime import UTC, datetime

from fastapi import APIRouter

from app.schemas import FreshnessResponse, HealthResponse, ServiceFreshness


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="backend", version="0.1.0")


@router.get("/freshness", response_model=FreshnessResponse)
def freshness() -> FreshnessResponse:
    now = datetime.now(UTC)
    return FreshnessResponse(
        generated_at=now,
        services=[
            ServiceFreshness(name="prices", status="fresh", as_of="2026-06-05", lag_minutes=38),
            ServiceFreshness(name="market_breadth", status="stale", as_of="2026-06-05", lag_minutes=1440),
            ServiceFreshness(name="sell_ranking", status="fresh", as_of="2026-06-08", lag_minutes=5),
        ],
    )

