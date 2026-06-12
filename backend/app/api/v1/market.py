from fastapi import APIRouter, Query

from app.schemas import (
    BreadthResponse,
    MarketDiagnosticsResponse,
    MarketOverviewResponse,
    SectorRankingResponse,
    VolatilityResponse,
)
from app.services.market import (
    get_breadth,
    get_market_diagnostics,
    get_market_overview,
    get_sector_ranking,
    get_volatility,
)


router = APIRouter()


@router.get("/overview", response_model=MarketOverviewResponse)
def market_overview() -> MarketOverviewResponse:
    return get_market_overview()


@router.get("/breadth", response_model=BreadthResponse)
def market_breadth() -> BreadthResponse:
    return get_breadth()


@router.get("/volatility", response_model=VolatilityResponse)
def market_volatility() -> VolatilityResponse:
    return get_volatility()


@router.get("/diagnostics", response_model=MarketDiagnosticsResponse)
def market_diagnostics() -> MarketDiagnosticsResponse:
    return get_market_diagnostics()


@router.get("/sectors", response_model=SectorRankingResponse)
def market_sectors(
    mode: str = Query(default="daily", pattern="^(daily|weekly)$"),
    periods: int = Query(default=15, ge=3, le=60),
) -> SectorRankingResponse:
    return get_sector_ranking(mode=mode, periods=periods)
