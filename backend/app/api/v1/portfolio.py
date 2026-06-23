from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.repositories.portfolio import PortfolioRepositoryUnavailable
from app.schemas import (
    BuyStrengthAssessmentResponse,
    BuyStrengthOverviewResponse,
    IsinMappingListResponse,
    IsinMappingPatchRequest,
    PortfolioCashFlowRequest,
    PortfolioCashFlowResponse,
    PortfolioCashFlowsResponse,
    PortfolioCurveResponse,
    PortfolioImportRequest,
    PortfolioImportResponse,
    PortfolioImportHistoryResponse,
    PortfolioPositionDeleteResponse,
    PortfolioPositionSizeRequest,
    PortfolioPositionSizeResponse,
    PortfolioPositionStopRequest,
    PortfolioPositionWriteRequest,
    PortfolioPositionWriteResponse,
    PortfolioPositionsResponse,
    PortfolioSellRequest,
    PortfolioSellResponse,
    PortfolioSnapshotResponse,
    PortfolioTransactionsResponse,
    TradeRepublicTransactionImportRequest,
    TradeRepublicTransactionImportResponse,
)
from app.services.portfolio import (
    calculate_position_size,
    create_portfolio_cash_flow,
    delete_portfolio_position,
    get_buy_strength_assessment,
    get_buy_strength_overview,
    get_portfolio_cash_flows,
    get_portfolio_curve,
    get_portfolio_import_history,
    get_isin_mappings,
    get_portfolio_positions,
    get_portfolio_snapshot,
    get_portfolio_transactions,
    import_portfolio_positions,
    import_trade_republic_transaction_export,
    sell_portfolio_position,
    update_isin_mappings,
    update_portfolio_position_stop,
    upsert_portfolio_position,
)


router = APIRouter()


@router.get("/positions", response_model=PortfolioPositionsResponse)
def positions() -> PortfolioPositionsResponse:
    return PortfolioPositionsResponse(positions=get_portfolio_positions())


@router.post("/positions", response_model=PortfolioPositionWriteResponse)
def create_or_update_position(payload: PortfolioPositionWriteRequest) -> PortfolioPositionWriteResponse:
    try:
        return upsert_portfolio_position(payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.patch("/positions/{ticker}", response_model=PortfolioPositionWriteResponse)
def patch_position(ticker: str, payload: PortfolioPositionWriteRequest) -> PortfolioPositionWriteResponse:
    try:
        next_payload = payload.model_copy(update={"ticker": ticker})
        return upsert_portfolio_position(next_payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.patch("/positions/{ticker}/stop", response_model=PortfolioPositionWriteResponse)
def patch_position_stop(ticker: str, payload: PortfolioPositionStopRequest) -> PortfolioPositionWriteResponse:
    try:
        return update_portfolio_position_stop(ticker, payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.delete("/positions/{ticker}", response_model=PortfolioPositionDeleteResponse)
def delete_position(ticker: str) -> PortfolioPositionDeleteResponse:
    try:
        return delete_portfolio_position(ticker)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.post("/positions/{ticker}/sell", response_model=PortfolioSellResponse)
def sell_position(ticker: str, payload: PortfolioSellRequest) -> PortfolioSellResponse:
    try:
        return sell_portfolio_position(ticker, payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/snapshot", response_model=PortfolioSnapshotResponse)
def snapshot() -> PortfolioSnapshotResponse:
    return get_portfolio_snapshot()


@router.get("/curve", response_model=PortfolioCurveResponse)
def curve(
    days: int = Query(default=370, ge=30, le=2500),
    start_date: date | None = Query(default=None),
) -> PortfolioCurveResponse:
    return get_portfolio_curve(days=days, start_date=start_date)


@router.get("/buy-strength", response_model=BuyStrengthOverviewResponse)
def buy_strength_overview(weeks: int = Query(default=3, ge=1, le=6)) -> BuyStrengthOverviewResponse:
    return get_buy_strength_overview(weeks=weeks)


@router.get("/buy-strength/{ticker}", response_model=BuyStrengthAssessmentResponse)
def buy_strength_detail(ticker: str, weeks: int = Query(default=3, ge=1, le=6)) -> BuyStrengthAssessmentResponse:
    return get_buy_strength_assessment(ticker, weeks=weeks)


@router.post("/position-size", response_model=PortfolioPositionSizeResponse)
def position_size(payload: PortfolioPositionSizeRequest) -> PortfolioPositionSizeResponse:
    return calculate_position_size(payload)


@router.get("/transactions", response_model=PortfolioTransactionsResponse)
def transactions(limit: int = Query(default=250, ge=1, le=1000)) -> PortfolioTransactionsResponse:
    return get_portfolio_transactions(limit=limit)


@router.get("/cash-flows", response_model=PortfolioCashFlowsResponse)
def cash_flows(limit: int = Query(default=250, ge=1, le=1000)) -> PortfolioCashFlowsResponse:
    return get_portfolio_cash_flows(limit=limit)


@router.post("/cash-flows", response_model=PortfolioCashFlowResponse)
def create_cash_flow(payload: PortfolioCashFlowRequest) -> PortfolioCashFlowResponse:
    try:
        return create_portfolio_cash_flow(payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.get("/imports", response_model=PortfolioImportHistoryResponse)
def imports(limit: int = Query(default=100, ge=1, le=500)) -> PortfolioImportHistoryResponse:
    return get_portfolio_import_history(limit=limit)


@router.get("/isin-mappings", response_model=IsinMappingListResponse)
def isin_mappings() -> IsinMappingListResponse:
    return get_isin_mappings()


@router.patch("/isin-mappings", response_model=IsinMappingListResponse)
def patch_isin_mappings(payload: IsinMappingPatchRequest) -> IsinMappingListResponse:
    try:
        return update_isin_mappings(payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.post("/imports/positions", response_model=PortfolioImportResponse)
def import_positions(payload: PortfolioImportRequest) -> PortfolioImportResponse:
    try:
        return import_portfolio_positions(payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc


@router.post("/imports/tr-transactions", response_model=TradeRepublicTransactionImportResponse)
def import_trade_republic_transactions(
    payload: TradeRepublicTransactionImportRequest,
) -> TradeRepublicTransactionImportResponse:
    try:
        return import_trade_republic_transaction_export(payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc
