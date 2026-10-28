"""Public company-news payloads; provider credentials and raw responses stay private."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NewsEntity(BaseModel):
    symbol: str
    name: str
    exchange: str | None = None
    match_score: float | None = None
    sentiment_score: float | None = None


class NewsArticle(BaseModel):
    uuid: str
    title: str
    description: str | None = None
    url: str
    source: str
    published_at: datetime
    entities: list[NewsEntity]
    match_score: float | None = None
    sentiment_score: float | None = None


class StockNewsResponse(BaseModel):
    ticker: str
    articles: list[NewsArticle] = Field(default_factory=list, max_length=3)
    updated_at: datetime | None = None
    status: Literal[
        "ok", "empty", "stale", "not_configured", "limit_reached", "unavailable", "unsupported"
    ]
    cached: bool = False
    message: str | None = None
