from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.repositories.fundamentals import FundamentalsRepositoryUnavailable
from app.schemas import (
    PriceHistoryResponse,
    PriceRefreshResponse,
    Institutional13FRankingResponse,
    Institutional13FTrendResponse,
    RsRatingDetailResponse,
    RsRatingRankingResponse,
    Sec13FMappingReviewResponse,
    Sec13FMappingUpdateRequest,
    StockAssessmentCompareResponse,
    StockFundamentalsResponse,
    StockFundamentalsUpdateRequest,
    StockAssessmentRankingResponse,
    StockAssessmentResponse,
    StockScreeningResponse,
    StockScreeningFilters,
    TopDailyStockResponse,
    StockSearchResponse,
    StockSignalChangesResponse,
)
from app.services.prices import PriceRange, get_price_history, refresh_and_get_price_history
from app.services.relative_strength import get_relative_strength_for_ticker, get_relative_strength_ranking
from app.services.sec13f import (
    get_institutional_13f_for_ticker,
    get_institutional_13f_ranking,
    get_sec13f_mapping_review,
    update_sec13f_manual_mapping,
)
from app.services.stocks import (
    get_stock_assessment,
    get_stock_assessment_compare,
    get_stock_assessment_ranking,
    get_stock_fundamentals,
    get_stock_signal_changes,
    search_stocks,
    update_stock_fundamentals,
)


router = APIRouter()


@router.get("/top-daily", response_model=TopDailyStockResponse)
def top_daily_stocks() -> TopDailyStockResponse:
    from app.services.daily_opportunities import get_top_daily

    return TopDailyStockResponse.model_validate(get_top_daily())


@router.get("/screening", response_model=StockScreeningResponse)
def stock_screening(filters: Annotated[StockScreeningFilters, Query()]) -> StockScreeningResponse:
    from app.repositories.stock_assessments import StockAssessmentRepositoryUnavailable
    from app.services.stock_screening import get_screening

    try:
        return StockScreeningResponse.model_validate(get_screening(filters))
    except StockAssessmentRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Die gespeicherte Bestenliste ist momentan nicht erreichbar.") from exc


@router.get("/screening/export")
def export_stock_screening(filters: Annotated[StockScreeningFilters, Query()]) -> Response:
    from app.repositories.stock_assessments import StockAssessmentRepositoryUnavailable
    from app.services.stock_screening import screening_csv

    try:
        return Response(
            content=screening_csv(filters), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="aktien-bestenliste.csv"'},
        )
    except StockAssessmentRepositoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Die Bestenliste konnte nicht exportiert werden.") from exc


@router.get("/search", response_model=StockSearchResponse)
def stock_search(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(default=8, ge=1, le=20),
) -> StockSearchResponse:
    return search_stocks(q, limit=limit)


@router.get("/ratings/rs", response_model=RsRatingRankingResponse)
def relative_strength_ranking(limit: int = Query(default=100, ge=1, le=500)) -> RsRatingRankingResponse:
    return get_relative_strength_ranking(limit=limit)


@router.get("/institutional/13f", response_model=Institutional13FRankingResponse)
def institutional_13f_ranking(limit: int = Query(default=100, ge=1, le=500)) -> Institutional13FRankingResponse:
    return get_institutional_13f_ranking(limit=limit)


@router.get("/institutional/13f/mappings", response_model=Sec13FMappingReviewResponse)
def institutional_13f_mappings(limit: int = Query(default=500, ge=1, le=1000)) -> Sec13FMappingReviewResponse:
    return get_sec13f_mapping_review(limit=limit)


@router.patch("/institutional/13f/mappings", response_model=Sec13FMappingReviewResponse)
def patch_institutional_13f_mapping(request: Sec13FMappingUpdateRequest) -> Sec13FMappingReviewResponse:
    try:
        return update_sec13f_manual_mapping(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="13F mapping database unavailable") from exc


@router.get("/assessment/ranking", response_model=StockAssessmentRankingResponse)
def stock_assessment_ranking(limit: int = Query(default=50, ge=1, le=500)) -> StockAssessmentRankingResponse:
    return get_stock_assessment_ranking(limit=limit)


@router.get("/assessment/compare", response_model=StockAssessmentCompareResponse)
def stock_assessment_compare(
    tickers: str = Query(..., min_length=1),
    limit: int = Query(default=12, ge=2, le=24),
) -> StockAssessmentCompareResponse:
    try:
        return get_stock_assessment_compare(tickers=tickers, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{ticker}/prices", response_model=PriceHistoryResponse)
def stock_prices(
    ticker: str,
    range: PriceRange = Query(default="1y", pattern="^(1m|3m|6m|1y|2y|5y)$"),
) -> PriceHistoryResponse:
    return get_price_history(ticker, range_key=range)


@router.post("/{ticker}/prices/refresh", response_model=PriceRefreshResponse)
def refresh_stock_prices(
    ticker: str,
    range: PriceRange = Query(default="1y", pattern="^(1m|3m|6m|1y|2y|5y)$"),
    fetch_range: PriceRange = Query(default="2y", pattern="^(1m|3m|6m|1y|2y|5y)$"),
    incremental: bool = Query(default=True),
    timeout: int = Query(default=15, ge=3, le=45),
) -> PriceRefreshResponse:
    try:
        return refresh_and_get_price_history(
            ticker,
            range_key=range,
            fetch_range_key=fetch_range,
            incremental=incremental,
            timeout=timeout,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Kursdaten konnten nicht über yfinance aktualisiert werden: {type(exc).__name__}: {exc}",
        ) from exc


@router.get("/{ticker}/rs", response_model=RsRatingDetailResponse)
def stock_relative_strength(ticker: str) -> RsRatingDetailResponse:
    return get_relative_strength_for_ticker(ticker)


@router.get("/{ticker}/assessment", response_model=StockAssessmentResponse)
def stock_assessment(ticker: str) -> StockAssessmentResponse:
    return get_stock_assessment(ticker)


@router.get("/{ticker}/changes", response_model=StockSignalChangesResponse)
def stock_signal_changes(ticker: str) -> StockSignalChangesResponse:
    return get_stock_signal_changes(ticker)


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


@router.get("/{ticker}/report.pdf", response_class=Response)
def investment_report_pdf(
    ticker: str,
    trade_id: str | None = Query(default=None, min_length=1, max_length=64),
) -> Response:
    import logging
    import re
    from sqlalchemy.exc import SQLAlchemyError
    from app.reports.collect import collect_report
    from app.reports.pdf import render_report

    clean = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=-]{0,31}", clean):
        raise HTTPException(status_code=422, detail="Ungültiger Ticker.")
    try:
        report = collect_report(clean, trade_id)
        content = render_report(report)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Datenbank für PDF-Export nicht erreichbar.") from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("PDF export failed for %s", clean)
        raise HTTPException(status_code=500, detail="PDF konnte nicht erzeugt werden. Bitte erneut versuchen.") from exc
    filename = f"{clean}-{'Trade' if trade_id else 'Investment'}-Report.pdf"
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
