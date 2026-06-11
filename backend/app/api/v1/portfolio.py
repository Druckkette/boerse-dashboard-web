from fastapi import APIRouter, HTTPException, Query, status

from app.repositories.portfolio import PortfolioRepositoryUnavailable
from app.schemas import (
    PortfolioCashFlowRequest,
    PortfolioCashFlowResponse,
    PortfolioCashFlowsResponse,
    PortfolioImportRequest,
    PortfolioImportResponse,
    PortfolioImportHistoryResponse,
    PortfolioPositionDeleteResponse,
    PortfolioPositionWriteRequest,
    PortfolioPositionWriteResponse,
    PortfolioPositionsResponse,
    PortfolioSellRequest,
    PortfolioSellResponse,
    PortfolioSnapshotResponse,
    PortfolioTransactionsResponse,
)
from app.services.portfolio import (
    create_portfolio_cash_flow,
    delete_portfolio_position,
    get_portfolio_cash_flows,
    get_portfolio_import_history,
    get_portfolio_positions,
    get_portfolio_snapshot,
    get_portfolio_transactions,
    import_portfolio_positions,
    sell_portfolio_position,
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


@router.post("/imports/positions", response_model=PortfolioImportResponse)
def import_positions(payload: PortfolioImportRequest) -> PortfolioImportResponse:
    try:
        return import_portfolio_positions(payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc
