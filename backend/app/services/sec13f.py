from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.repositories import sec13f as sec13f_repository
from app.repositories.sec13f import (
    Institutional13FTrendRow,
    Institutional13FTrendWrite,
    Sec13FRepositoryUnavailable,
)
from app.schemas import (
    Institutional13FRankingResponse,
    Institutional13FTrendItem,
    Institutional13FTrendResponse,
)


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
