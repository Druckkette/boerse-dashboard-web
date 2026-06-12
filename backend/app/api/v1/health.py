from fastapi import APIRouter

from app.schemas import FreshnessResponse, HealthResponse, SystemReadinessResponse
from app.services.freshness import get_freshness
from app.services.system import get_system_readiness


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="backend", version="0.1.0")


@router.get("/readiness", response_model=SystemReadinessResponse)
def readiness() -> SystemReadinessResponse:
    return get_system_readiness()


@router.get("/freshness", response_model=FreshnessResponse)
def freshness() -> FreshnessResponse:
    return get_freshness()
