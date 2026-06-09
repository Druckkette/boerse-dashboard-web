from fastapi import APIRouter

from app.schemas import PortfolioPositionsResponse, PortfolioSnapshotResponse
from app.services.dummy_data import get_portfolio_positions, get_portfolio_snapshot


router = APIRouter()


@router.get("/positions", response_model=PortfolioPositionsResponse)
def positions() -> PortfolioPositionsResponse:
    return PortfolioPositionsResponse(positions=get_portfolio_positions())


@router.get("/snapshot", response_model=PortfolioSnapshotResponse)
def snapshot() -> PortfolioSnapshotResponse:
    return get_portfolio_snapshot()

