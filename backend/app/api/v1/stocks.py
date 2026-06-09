from fastapi import APIRouter, Query

from app.schemas import PriceHistoryResponse
from app.services.prices import PriceRange, get_price_history


router = APIRouter()


@router.get("/{ticker}/prices", response_model=PriceHistoryResponse)
def stock_prices(
    ticker: str,
    range: PriceRange = Query(default="1y", pattern="^(1m|3m|6m|1y|2y|5y)$"),
) -> PriceHistoryResponse:
    return get_price_history(ticker, range_key=range)
