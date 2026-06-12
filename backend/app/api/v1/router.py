from fastapi import APIRouter

from app.api.v1 import health, jobs, market, portfolio, sell, settings, setup, stocks, workspace


api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
api_router.include_router(sell.router, prefix="/sell", tags=["sell"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(setup.router, prefix="/setup", tags=["setup"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["workspace"])
