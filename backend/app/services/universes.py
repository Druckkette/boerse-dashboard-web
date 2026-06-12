from __future__ import annotations

from datetime import UTC, datetime

from app.data_sources.nasdaq_trader import fetch_us_common_stock_universe
from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import universes as universe_repository
from app.schemas import UniverseStatusResponse


def get_universe_status(key: str = "us_common_stocks") -> UniverseStatusResponse:
    try:
        row = universe_repository.get_universe_status(key)
    except universe_repository.UniverseRepositoryUnavailable:
        row = None
    if row is None:
        return UniverseStatusResponse(
            key=key,
            name="US Common Stocks",
            source="fallback",
            member_count=len(DEFAULT_MARKET_UNIVERSE_TICKERS),
            updated_at=None,
            sample_tickers=DEFAULT_MARKET_UNIVERSE_TICKERS[:30],
            metadata={"fallback": True},
        )
    return UniverseStatusResponse(
        key=row.key,
        name=row.name,
        source=row.source,
        member_count=row.member_count,
        updated_at=row.updated_at,
        sample_tickers=row.sample_tickers,
        metadata=row.metadata_json,
    )


def refresh_us_common_stock_universe() -> dict:
    fetched = fetch_us_common_stock_universe()
    row = universe_repository.upsert_universe_members(
        key=fetched.key,
        name=fetched.name,
        source=fetched.source,
        tickers=fetched.tickers,
        metadata=fetched.metadata,
    )
    return {
        "ok": True,
        "job_type": "refresh_universe",
        "key": row.key,
        "member_count": row.member_count,
        "records_seen": len(fetched.tickers),
        "records_written": row.member_count,
        "updated_at": (row.updated_at or datetime.now(UTC)).isoformat(),
        "metadata": row.metadata_json,
    }


def resolve_universe_tickers(
    *,
    explicit_tickers: object,
    universe_key: object,
    fallback: list[str],
    limit: int,
) -> list[str]:
    explicit = _normalize_tickers(explicit_tickers)
    if explicit:
        return explicit[:limit]
    key = str(universe_key or "").strip()
    if key in {"us_common_stocks", "stored", "live"}:
        try:
            stored = universe_repository.list_universe_tickers("us_common_stocks", limit=limit)
        except universe_repository.UniverseRepositoryUnavailable:
            stored = []
        if stored:
            return stored[:limit]
    return _normalize_tickers(fallback)[:limit]


def _normalize_tickers(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, list | tuple | set):
        raw = list(value)
    else:
        raw = []
    return list(
        dict.fromkeys(str(item).strip().upper().replace(".", "-") for item in raw if str(item).strip())
    )
