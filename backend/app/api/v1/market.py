from fastapi import APIRouter, HTTPException, Query

from app.repositories.universes import UniverseRepositoryUnavailable
from app.schemas import (
    BreadthResponse,
    MarketAmpelResponse,
    MarketDiagnosticsResponse,
    MarketOverviewResponse,
    SectorRankingResponse,
    UniverseStatusResponse,
    UniverseSymbolMappingReviewResponse,
    UniverseSymbolMappingUpdateRequest,
    VolatilityResponse,
)
from app.services.market import (
    get_breadth,
    get_market_ampel,
    get_market_diagnostics,
    get_market_overview,
    get_sector_ranking,
    get_volatility,
)
from app.services.universes import (
    get_universe_status,
    get_universe_symbol_mappings,
    update_universe_symbol_mapping,
)


router = APIRouter()


@router.get("/overview", response_model=MarketOverviewResponse)
def market_overview() -> MarketOverviewResponse:
    return get_market_overview()


@router.get("/ampel", response_model=MarketAmpelResponse)
def market_ampel(
    ticker: str = Query(default="SPY", max_length=24),
    days: int = Query(default=90, ge=30, le=240),
) -> MarketAmpelResponse:
    return get_market_ampel(ticker=ticker, days=days)


@router.get("/breadth", response_model=BreadthResponse)
def market_breadth() -> BreadthResponse:
    return get_breadth()


@router.get("/universe", response_model=UniverseStatusResponse)
def market_universe() -> UniverseStatusResponse:
    return get_universe_status()


@router.get("/universe/mappings", response_model=UniverseSymbolMappingReviewResponse)
def market_universe_mappings(
    limit: int = Query(default=500, ge=1, le=1000),
) -> UniverseSymbolMappingReviewResponse:
    return get_universe_symbol_mappings(limit=limit)


@router.patch("/universe/mappings", response_model=UniverseSymbolMappingReviewResponse)
def patch_market_universe_mapping(
    request: UniverseSymbolMappingUpdateRequest,
) -> UniverseSymbolMappingReviewResponse:
    try:
        return update_universe_symbol_mapping(request)
    except UniverseRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Universe mapping database unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
