from fastapi import APIRouter

from app.schemas import BreadthResponse, MarketOverviewResponse, VolatilityResponse
from app.services.market import get_breadth, get_market_overview, get_volatility


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
