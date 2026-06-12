from __future__ import annotations

from datetime import UTC, datetime

from app.data_sources.nasdaq_trader import fetch_us_common_stock_universe
from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import universes as universe_repository
from app.schemas import (
    UniverseStatusResponse,
    UniverseSymbolMappingItem,
    UniverseSymbolMappingReviewResponse,
    UniverseSymbolMappingUpdateRequest,
)


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


def get_universe_symbol_mappings(
    key: str = "us_common_stocks",
    *,
    limit: int = 500,
) -> UniverseSymbolMappingReviewResponse:
    clean_key = key.strip() or "us_common_stocks"
    source = "database"
    try:
        member_tickers = universe_repository.list_universe_tickers(clean_key, limit=5_000)
        mapping_rows = universe_repository.list_symbol_mappings(clean_key, limit=limit)
    except universe_repository.UniverseRepositoryUnavailable:
        source = "fallback"
        member_tickers = DEFAULT_MARKET_UNIVERSE_TICKERS
        mapping_rows = []

    if not member_tickers:
        source = "fallback"
        member_tickers = DEFAULT_MARKET_UNIVERSE_TICKERS

    current_members = {ticker.upper() for ticker in member_tickers}
    current_mapping_rows = [row for row in mapping_rows if row.source_ticker.upper() in current_members]
    mapped_by_source = {row.source_ticker.upper(): row for row in current_mapping_rows}
    unmapped = [ticker for ticker in member_tickers if ticker.upper() not in mapped_by_source]
    mapped_count = sum(1 for row in current_mapping_rows if row.status == "active" and row.yahoo_symbol)
    ignored_count = sum(1 for row in current_mapping_rows if row.status == "ignored")
    return UniverseSymbolMappingReviewResponse(
        source=source,
        as_of=datetime.now(UTC).date().isoformat(),
        universe_key=clean_key,
        member_count=len(member_tickers),
        mapped_count=mapped_count,
        ignored_count=ignored_count,
        unmapped_count=len(unmapped),
        mappings=[_mapping_item(row) for row in current_mapping_rows],
        unmapped_sample=unmapped[:80],
    )


def update_universe_symbol_mapping(
    request: UniverseSymbolMappingUpdateRequest,
) -> UniverseSymbolMappingReviewResponse:
    universe_repository.upsert_symbol_mapping(
        key=request.universe_key,
        source_ticker=request.source_ticker,
        yahoo_symbol=request.yahoo_symbol,
        status=request.status,
        source="manual",
        note=request.note,
        confidence=1.0,
    )
    return get_universe_symbol_mappings(request.universe_key)


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


def resolve_universe_price_symbols(
    *,
    explicit_tickers: object,
    universe_key: object,
    fallback: list[str],
    limit: int,
) -> list[universe_repository.ResolvedUniverseSymbolRow]:
    explicit = _normalize_tickers(explicit_tickers)
    if explicit:
        return [
            universe_repository.ResolvedUniverseSymbolRow(
                source_ticker=ticker,
                yahoo_symbol=ticker,
                status="explicit",
                source="payload",
            )
            for ticker in explicit[:limit]
        ]

    key = str(universe_key or "").strip()
    if key in {"us_common_stocks", "stored", "live"}:
        try:
            stored = universe_repository.list_resolved_universe_symbols("us_common_stocks", limit=limit)
        except universe_repository.UniverseRepositoryUnavailable:
            stored = []
        if stored:
            return stored[:limit]

    return [
        universe_repository.ResolvedUniverseSymbolRow(
            source_ticker=ticker,
            yahoo_symbol=ticker,
            status="fallback",
            source="preset",
        )
        for ticker in _normalize_tickers(fallback)[:limit]
    ]


def _mapping_item(row: universe_repository.UniverseSymbolMappingRow) -> UniverseSymbolMappingItem:
    status = row.status if row.status in {"active", "ignored"} else "unmapped"
    return UniverseSymbolMappingItem(
        universe_key=row.universe_key,
        source_ticker=row.source_ticker,
        yahoo_symbol=row.yahoo_symbol,
        status=status,  # type: ignore[arg-type]
        source=row.source,
        note=row.note,
        confidence=row.confidence,
        updated_at=row.updated_at,
    )


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
