from fastapi import APIRouter

from app.schemas import BreadthResponse, MarketOverviewResponse
from app.services.dummy_data import get_breadth, get_market_overview


router = APIRouter()


@router.get("/overview", response_model=MarketOverviewResponse)
def market_overview() -> MarketOverviewResponse:
    return get_market_overview()


@router.get("/breadth", response_model=BreadthResponse)
def market_breadth() -> BreadthResponse:
    return get_breadth()

