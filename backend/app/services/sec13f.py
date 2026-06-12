from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.data_sources.sec13f_client import build_institutional_13f_payload, normalize_ticker
from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.repositories import sec13f as sec13f_repository
from app.repositories import jobs as job_repository
from app.repositories import portfolio as portfolio_repository
from app.repositories.sec13f import (
    Institutional13FTrendRow,
    Institutional13FTrendWrite,
    Sec13FMappingRow,
    Sec13FRepositoryUnavailable,
)
from app.schemas import (
    Institutional13FRankingResponse,
    Institutional13FTrendItem,
    Institutional13FTrendResponse,
    Sec13FMappingItem,
    Sec13FMappingReviewResponse,
    Sec13FMappingUpdateRequest,
    Sec13FUnmatchedCusipItem,
)

ProgressCallback = Callable[[int, str, str, dict[str, Any]], None]


def ingest_institutional_13f_payload(payload: dict[str, Any]) -> dict:
    tickers_payload = payload.get("tickers") if isinstance(payload.get("tickers"), dict) else payload
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    source_url = str(metadata.get("source_url") or "SEC Form 13F Data Sets")
    rows: list[Institutional13FTrendWrite] = []
    for ticker, raw_record in tickers_payload.items():
        if not isinstance(raw_record, dict):
            continue
        clean = str(ticker or raw_record.get("ticker") or "").strip().upper()
        period = _parse_date(raw_record.get("period") or raw_record.get("report_period"))
        if not clean or period is None:
            continue
        rows.append(
            Institutional13FTrendWrite(
                ticker=clean,
                cusip=str(raw_record.get("cusip") or ""),
                report_period=period,
                filing_date=_parse_date(raw_record.get("filing_date")),
                shares=_float_or_none(raw_record.get("total_shares") or raw_record.get("shares")),
                market_value_usd=_float_or_none(raw_record.get("total_value_usd") or raw_record.get("market_value_usd")),
                shares_change_pct=_float_or_none(raw_record.get("total_shares_delta_pct") or raw_record.get("shares_change_pct")),
                holders_count=_int_or_none(raw_record.get("holder_count") or raw_record.get("holders_count")) or 0,
                source_url=source_url,
                raw_json={**raw_record, "ticker": clean},
            )
        )
    written = sec13f_repository.upsert_aggregate_trends(rows)
    return {
        "ok": bool(written),
        "records_seen": len(tickers_payload) if isinstance(tickers_payload, dict) else 0,
        "records_written": written,
        "source": "payload",
    }


def refresh_institutional_13f_from_sec(
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    universe = _resolve_universe(payload)
    manual_overrides = _load_manual_overrides()
    cache_root = Path(str(payload.get("cache_dir") or os.environ.get("BACKEND_CACHE_DIR") or ".cache"))
    build_result = build_institutional_13f_payload(
        universe=universe,
        cache_dir=cache_root / "sec13f",
        dataset_count=_int_or_default(payload.get("dataset_count"), 2),
        large_holder_min_value_usd=_float_or_default(payload.get("large_holder_min_value_usd"), 10_000_000),
        chunksize=_int_or_default(payload.get("chunksize"), 250_000),
        cusip_overrides=manual_overrides,
        progress=progress_callback,
    )
    ingest_result = ingest_institutional_13f_payload(build_result.payload)
    ingest_result.update(
        {
            "source": "sec",
            "metadata": build_result.metadata,
            "universe": universe,
            "universe_count": len(universe),
            "mapping_count": len(build_result.mapping_rows),
            "unmatched_count": len(build_result.unmatched_rows),
            "unmatched_sample": build_result.unmatched_rows[:50],
            "records_seen": len(build_result.payload.get("tickers", {})),
        }
    )
    return ingest_result


def get_sec13f_mapping_review(limit: int = 500) -> Sec13FMappingReviewResponse:
    try:
        mappings = sec13f_repository.list_cusip_mappings(limit=limit)
    except Sec13FRepositoryUnavailable:
        mappings = []
    unmatched, source_job_id = _latest_unmatched_sample()
    return Sec13FMappingReviewResponse(
        source="database" if mappings or unmatched else "missing",
        as_of=date.today().isoformat(),
        mappings=[_mapping_to_item(row) for row in mappings],
        unmatched=unmatched,
        unmatched_source_job_id=source_job_id,
    )


def update_sec13f_manual_mapping(request: Sec13FMappingUpdateRequest) -> Sec13FMappingReviewResponse:
    sec13f_repository.upsert_manual_cusip_mapping(
        cusip=request.cusip,
        ticker=request.ticker,
        issuer_name=request.issuer_name,
    )
    return get_sec13f_mapping_review()


def get_institutional_13f_for_ticker(ticker: str) -> Institutional13FTrendResponse:
    clean = ticker.strip().upper()
    try:
        row = sec13f_repository.get_latest_trend_for_ticker(clean)
    except Sec13FRepositoryUnavailable:
        row = None
    if row is None:
        return Institutional13FTrendResponse(ticker=clean, source="missing", as_of=date.today().isoformat(), item=None)
    return Institutional13FTrendResponse(
        ticker=clean,
        source="database",
        as_of=row.report_period.isoformat(),
        item=_row_to_item(row),
    )


def get_institutional_13f_ranking(limit: int = 100) -> Institutional13FRankingResponse:
    try:
        rows = sec13f_repository.list_latest_trends(limit=limit)
    except Sec13FRepositoryUnavailable:
        rows = []
    if not rows:
        return Institutional13FRankingResponse(source="missing", as_of=date.today().isoformat(), rows=[])
    return Institutional13FRankingResponse(
        source="database",
        as_of=max(row.report_period for row in rows).isoformat(),
        rows=[_row_to_item(row) for row in rows],
    )


def _row_to_item(row: Institutional13FTrendRow) -> Institutional13FTrendItem:
    raw = row.raw_json or {}
    return Institutional13FTrendItem(
        ticker=row.ticker,
        cusip=row.cusip,
        report_period=str(raw.get("period") or row.report_period.isoformat()),
        previous_period=_str_or_none(raw.get("previous_period")),
        holder_count=_int_or_none(raw.get("holder_count")) or row.holders_count,
        previous_holder_count=_int_or_none(raw.get("previous_holder_count")),
        holder_count_delta=_int_or_none(raw.get("holder_count_delta")),
        large_holder_count=_int_or_none(raw.get("large_holder_count")),
        previous_large_holder_count=_int_or_none(raw.get("previous_large_holder_count")),
        large_holder_delta=_int_or_none(raw.get("large_holder_delta")),
        total_value_usd=_float_or_none(raw.get("total_value_usd")) or row.market_value_usd,
        previous_total_value_usd=_float_or_none(raw.get("previous_total_value_usd")),
        total_value_delta_pct=_float_or_none(raw.get("total_value_delta_pct")),
        total_shares=_float_or_none(raw.get("total_shares")) or row.shares,
        previous_total_shares=_float_or_none(raw.get("previous_total_shares")),
        total_shares_delta_pct=_float_or_none(raw.get("total_shares_delta_pct")) or row.shares_change_pct,
        trend=_trend(raw.get("trend")),
        source_url=row.source_url,
    )


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    numeric = _float_or_none(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _trend(value: Any) -> str:
    clean = str(value or "missing").strip().lower()
    return clean if clean in {"positive", "negative", "neutral", "new"} else "missing"


def _mapping_to_item(row: Sec13FMappingRow) -> Sec13FMappingItem:
    return Sec13FMappingItem(
        cusip=row.cusip,
        ticker=row.ticker,
        issuer_name=row.issuer_name,
        source=row.source,
        confidence=row.confidence,
        updated_at=row.updated_at,
    )


def _latest_unmatched_sample() -> tuple[list[Sec13FUnmatchedCusipItem], str]:
    for job in job_repository.list_jobs(limit=100):
        if job.job_type != "refresh_sec13f" or job.status != "done":
            continue
        sample = job.result.get("unmatched_sample")
        if not isinstance(sample, list):
            continue
        return [_unmatched_item(row) for row in sample if isinstance(row, dict)], job.job_id
    return [], ""


def _unmatched_item(row: dict[str, Any]) -> Sec13FUnmatchedCusipItem:
    return Sec13FUnmatchedCusipItem(
        cusip=str(row.get("cusip") or ""),
        issuer=str(row.get("issuer") or ""),
        title=str(row.get("title") or ""),
        reason=str(row.get("reason") or ""),
        candidate_tickers=str(row.get("candidate_tickers") or ""),
        current_holder_count=_int_or_none(row.get("current_holder_count")),
        current_total_value_usd=_float_or_none(row.get("current_total_value_usd")),
    )


def _load_manual_overrides() -> dict[str, str]:
    try:
        return sec13f_repository.list_manual_cusip_overrides()
    except Sec13FRepositoryUnavailable:
        return {}


def _resolve_universe(payload: dict[str, Any]) -> list[str]:
    explicit = _normalize_tickers(payload.get("tickers"))
    limit = max(1, min(500, _int_or_default(payload.get("limit_universe") or payload.get("limit"), 120)))
    if explicit:
        return explicit[:limit]

    universe_key = str(payload.get("universe") or payload.get("mode") or "open_positions").strip().lower()
    tickers: list[str] = []
    if universe_key in {"open_positions", "positions", "incremental", "manual"}:
        try:
            tickers = [row.ticker for row in portfolio_repository.list_open_positions()]
        except portfolio_repository.PortfolioRepositoryUnavailable:
            tickers = []
    if not tickers:
        tickers = list(DEFAULT_MARKET_UNIVERSE_TICKERS)
    return _normalize_tickers(tickers)[:limit]


def _normalize_tickers(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, list | tuple | set):
        raw = list(value)
    else:
        raw = []
    tickers = [normalize_ticker(item) for item in raw]
    return list(dict.fromkeys(ticker for ticker in tickers if ticker))


def _int_or_default(value: Any, default: int) -> int:
    numeric = _int_or_none(value)
    return numeric if numeric is not None and numeric > 0 else default


def _float_or_default(value: Any, default: float) -> float:
    numeric = _float_or_none(value)
    return numeric if numeric is not None and numeric > 0 else default
