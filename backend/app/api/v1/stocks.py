from fastapi import APIRouter, HTTPException, Query

from app.repositories.fundamentals import FundamentalsRepositoryUnavailable
from app.schemas import (
    PriceHistoryResponse,
    Institutional13FRankingResponse,
    Institutional13FTrendResponse,
    RsRatingDetailResponse,
    RsRatingRankingResponse,
    StockFundamentalsResponse,
    StockFundamentalsUpdateRequest,
    StockAssessmentRankingResponse,
    StockAssessmentResponse,
)
from app.services.prices import PriceRange, get_price_history
from app.services.relative_strength import get_relative_strength_for_ticker, get_relative_strength_ranking
from app.services.sec13f import get_institutional_13f_for_ticker, get_institutional_13f_ranking
from app.services.stocks import (
    get_stock_assessment,
    get_stock_assessment_ranking,
    get_stock_fundamentals,
    update_stock_fundamentals,
)


router = APIRouter()


@router.get("/ratings/rs", response_model=RsRatingRankingResponse)
def relative_strength_ranking(limit: int = Query(default=100, ge=1, le=500)) -> RsRatingRankingResponse:
    return get_relative_strength_ranking(limit=limit)


@router.get("/institutional/13f", response_model=Institutional13FRankingResponse)
def institutional_13f_ranking(limit: int = Query(default=100, ge=1, le=500)) -> Institutional13FRankingResponse:
    return get_institutional_13f_ranking(limit=limit)


@router.get("/assessment/ranking", response_model=StockAssessmentRankingResponse)
def stock_assessment_ranking(limit: int = Query(default=50, ge=1, le=120)) -> StockAssessmentRankingResponse:
    return get_stock_assessment_ranking(limit=limit)


@router.get("/{ticker}/prices", response_model=PriceHistoryResponse)
def stock_prices(
    ticker: str,
    range: PriceRange = Query(default="1y", pattern="^(1m|3m|6m|1y|2y|5y)$"),
) -> PriceHistoryResponse:
    return get_price_history(ticker, range_key=range)


@router.get("/{ticker}/rs", response_model=RsRatingDetailResponse)
def stock_relative_strength(ticker: str) -> RsRatingDetailResponse:
    return get_relative_strength_for_ticker(ticker)


@router.get("/{ticker}/assessment", response_model=StockAssessmentResponse)
def stock_assessment(ticker: str) -> StockAssessmentResponse:
    return get_stock_assessment(ticker)


@router.get("/{ticker}/fundamentals", response_model=StockFundamentalsResponse)
def stock_fundamentals(ticker: str) -> StockFundamentalsResponse:
    return get_stock_fundamentals(ticker)


@router.patch("/{ticker}/fundamentals", response_model=StockFundamentalsResponse)
def patch_stock_fundamentals(
    ticker: str,
    request: StockFundamentalsUpdateRequest,
) -> StockFundamentalsResponse:
    try:
        return update_stock_fundamentals(ticker, request)
    except FundamentalsRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Fundamental database unavailable") from exc


@router.get("/{ticker}/institutional/13f", response_model=Institutional13FTrendResponse)
def stock_institutional_13f(ticker: str) -> Institutional13FTrendResponse:
    return get_institutional_13f_for_ticker(ticker)
