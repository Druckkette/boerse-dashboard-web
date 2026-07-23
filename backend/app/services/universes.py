from __future__ import annotations

from datetime import UTC, datetime

from app.data_sources.yfinance_client import probe_daily_price_symbol
from app.data_sources.nasdaq_trader import fetch_us_common_stock_universe
from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import jobs as job_repository
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
        member_tickers = universe_repository.list_universe_tickers(clean_key, limit=10_000)
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


def diagnose_yahoo_symbols(payload: dict | None = None, *, apply_mappings: bool = False) -> dict:
    payload = payload or {}
    universe_key = str(payload.get("universe") or payload.get("universe_key") or "us_common_stocks").strip()
    limit = _normalize_limit(payload.get("limit") or payload.get("sample_size") or 40)
    period = _normalize_probe_period(payload.get("period") or "1mo")
    tickers = _diagnostic_tickers(payload, universe_key=universe_key, limit=limit)
    items: list[dict] = []
    mapped_count = 0
    candidate_found_count = 0

    for ticker in tickers:
        item = _diagnose_single_yahoo_symbol(ticker, period=period)
        if item["status"] == "candidate_found":
            candidate_found_count += 1
            if apply_mappings and item.get("best_candidate"):
                universe_repository.upsert_symbol_mapping(
                    key=universe_key,
                    source_ticker=ticker,
                    yahoo_symbol=str(item["best_candidate"]),
                    status="active",
                    source="auto_rescue",
                    note="Automatisch validiert über yfinance-Daily-Probe.",
                    confidence=0.80,
                )
                item["mapping_applied"] = True
                mapped_count += 1
        items.append(item)

    ok_count = sum(1 for item in items if item["status"] in {"valid_current", "candidate_found"})
    return {
        "ok": True,
        "job_type": "yahoo_symbol_rescue" if apply_mappings else "yahoo_symbol_diagnostics",
        "universe_key": universe_key,
        "period": period,
        "requested_count": len(tickers),
        "ok_count": ok_count,
        "candidate_found_count": candidate_found_count,
        "mapped_count": mapped_count,
        "not_found_count": sum(1 for item in items if item["status"] == "not_found"),
        "items": items,
    }


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


def _diagnostic_tickers(payload: dict, *, universe_key: str, limit: int) -> list[str]:
    explicit = _normalize_tickers(payload.get("tickers") or payload.get("failed_tickers"))
    if explicit:
        return explicit[:limit]

    latest_failed = _latest_failed_price_tickers(limit=limit)
    if latest_failed:
        return latest_failed

    review = get_universe_symbol_mappings(universe_key, limit=limit)
    return review.unmapped_sample[:limit]


def _latest_failed_price_tickers(*, limit: int) -> list[str]:
    for job in job_repository.list_jobs(limit=25):
        if job.job_type != "refresh_prices":
            continue
        result = job.result if isinstance(job.result, dict) else {}
        failed: list[str] = []
        raw_failed = result.get("failed_tickers")
        if isinstance(raw_failed, list):
            failed.extend(str(item) for item in raw_failed)
        raw_items = result.get("items")
        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, dict) and item.get("ok") is False and item.get("ticker"):
                    failed.append(str(item["ticker"]))
        normalized = _normalize_tickers(failed)
        if normalized:
            return normalized[:limit]
    return []


def _diagnose_single_yahoo_symbol(ticker: str, *, period: str) -> dict:
    clean = _normalize_tickers([ticker])[0]
    candidates = _build_yahoo_symbol_candidates(clean)
    candidate_results = [probe_daily_price_symbol(candidate, period=period) for candidate in candidates]
    valid = [candidate for candidate in candidate_results if candidate.get("ok")]
    best = str(valid[0]["symbol"]) if valid else ""
    status = "not_found"
    if best:
        status = "valid_current" if best == clean else "candidate_found"
    return {
        "source_ticker": clean,
        "best_candidate": best,
        "status": status,
        "mapping_applied": False,
        "candidates": candidate_results,
    }


def _build_yahoo_symbol_candidates(ticker: str) -> list[str]:
    clean = ticker.strip().upper()
    candidates = [clean]
    if "-" in clean:
        candidates.append(clean.replace("-", "."))
        candidates.append(clean.replace("-", ""))
    if "." in clean:
        candidates.append(clean.replace(".", "-"))
        candidates.append(clean.replace(".", ""))
    if clean.endswith(".U"):
        candidates.append(f"{clean[:-2]}-UN")
    if clean.endswith("-U"):
        candidates.append(f"{clean[:-2]}.U")
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _normalize_limit(value: object) -> int:
    try:
        return max(1, min(120, int(value)))
    except (TypeError, ValueError):
        return 40


def _normalize_probe_period(value: object) -> str:
    clean = str(value).strip()
    if clean in {"5d", "1mo", "3mo"}:
        return clean
    return "1mo"


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
