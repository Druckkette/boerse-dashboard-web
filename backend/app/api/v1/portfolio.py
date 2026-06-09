from fastapi import APIRouter, HTTPException, status

from app.repositories.portfolio import PortfolioRepositoryUnavailable
from app.schemas import (
    PortfolioImportRequest,
    PortfolioImportResponse,
    PortfolioPositionsResponse,
    PortfolioSnapshotResponse,
)
from app.services.portfolio import (
    get_portfolio_positions,
    get_portfolio_snapshot,
    import_portfolio_positions,
)


router = APIRouter()


@router.get("/positions", response_model=PortfolioPositionsResponse)
def positions() -> PortfolioPositionsResponse:
    return PortfolioPositionsResponse(positions=get_portfolio_positions())


@router.get("/snapshot", response_model=PortfolioSnapshotResponse)
def snapshot() -> PortfolioSnapshotResponse:
    return get_portfolio_snapshot()


@router.post("/imports/positions", response_model=PortfolioImportResponse)
def import_positions(payload: PortfolioImportRequest) -> PortfolioImportResponse:
    try:
        return import_portfolio_positions(payload)
    except PortfolioRepositoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Portfolio-Datenbank ist nicht erreichbar: {exc}",
        ) from exc
