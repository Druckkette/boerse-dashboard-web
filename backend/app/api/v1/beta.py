import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import Literal

from app.beta_policy import TICKER_PATTERN
from app.domain.sell.schemas import SellPreviewRequest
from app.services import beta

router = APIRouter()


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["auto", "manual"] = "manual"


class BetaPreviewRequest(SellPreviewRequest):
    model_config = ConfigDict(extra="forbid")


def clean_ticker(value: str) -> str:
    if not re.fullmatch(TICKER_PATTERN, value):
        raise HTTPException(422, "Ungültiger Ticker.")
    return value.upper()


@router.get("/home")
def home():
    return beta.home_dashboard()


@router.get("/stocks/{ticker}/freshness")
def freshness(ticker: str):
    return beta.stock_freshness(clean_ticker(ticker))


@router.post("/stocks/{ticker}/refresh")
def refresh(ticker: str, payload: RefreshRequest):
    return beta.refresh_stock(clean_ticker(ticker), payload.mode)


@router.get("/stock-refresh/{handle}/status")
def status(handle: str, x_beta_capability: str = Header(default="")):
    return beta.refresh_status(handle, x_beta_capability)


@router.post("/sell/preview")
def preview(payload: BetaPreviewRequest):
    clean_ticker(payload.ticker)
    return beta.preview_sell(payload)
