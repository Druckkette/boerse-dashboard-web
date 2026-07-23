from __future__ import annotations

from datetime import date, timedelta

from app.domain.market.constants import DEFAULT_MARKET_UNIVERSE_TICKERS
from app.domain.stocks.relative_strength import compute_relative_strength_ratings
from app.repositories import market as market_repository
from app.repositories import relative_strength as rs_repository
from app.repositories.relative_strength import (
    RelativeStrengthRepositoryUnavailable,
    RsRatingRow,
    RsRatingWrite,
)
from app.schemas import RsLinePoint, RsRatingDetailResponse, RsRatingItem, RsRatingRankingResponse


DEFAULT_RS_BENCHMARK_TICKER = "SPY"
DEFAULT_RS_SOURCE = "computed"
DEFAULT_RS_LOOKBACK_DAYS = 430


def refresh_relative_strength_ratings(
    *,
    tickers: list[str] | None = None,
    benchmark_ticker: str = DEFAULT_RS_BENCHMARK_TICKER,
    lookback_days: int = DEFAULT_RS_LOOKBACK_DAYS,
    source: str = DEFAULT_RS_SOURCE,
) -> dict:
    clean_tickers = _normalize_tickers(tickers or DEFAULT_MARKET_UNIVERSE_TICKERS)
    clean_benchmark = benchmark_ticker.strip().upper() or DEFAULT_RS_BENCHMARK_TICKER
    load_tickers = list(dict.fromkeys([*clean_tickers, clean_benchmark]))
    start_date = date.today() - timedelta(days=max(120, min(2500, lookback_days)))

    series = market_repository.load_cached_prices(load_tickers, start_date=start_date)
    ratings = compute_relative_strength_ratings(series, benchmark_ticker=clean_benchmark)
    if not ratings:
        return {
            "ok": False,
            "skipped": True,
            "reason": "Keine ausreichenden Price-Bars im Cache. Zuerst refresh_prices ausführen.",
            "benchmark_ticker": clean_benchmark,
            "universe_size": len(clean_tickers),
            "covered_tickers": len(series),
            "records_seen": sum(len(points) for points in series.values()),
            "records_written": 0,
        }

    snapshot_date = max(item.date for item in ratings)
    writes = [
        RsRatingWrite(
            ticker=item.ticker,
            date=snapshot_date,
            rating=item.rating,
            score=item.score,
            percentile=item.percentile,
            method=item.method,
            source=source,
            universe_size=item.universe_size,
            metadata_json={
                **item.metadata,
                "data_as_of": item.date.isoformat(),
                "snapshot_date": snapshot_date.isoformat(),
            },
        )
        for item in ratings
    ]
    records_written = rs_repository.upsert_rs_ratings(writes)
    top = [_row_to_payload(item) for item in rs_repository.list_latest_rs_ratings(limit=10, source=source)]
    return {
        "ok": True,
        "benchmark_ticker": clean_benchmark,
        "source": source,
        "as_of": snapshot_date.isoformat(),
        "universe_size": len(clean_tickers),
        "covered_tickers": len(series),
        "ratings_count": len(ratings),
        "records_seen": sum(len(points) for points in series.values()),
        "records_written": records_written,
        "top": top,
    }


def get_relative_strength_ranking(*, limit: int = 100) -> RsRatingRankingResponse:
    clean_limit = max(1, min(500, limit))
    try:
        total_count = rs_repository.count_latest_rs_ratings(source=DEFAULT_RS_SOURCE)
        rows = rs_repository.list_latest_rs_ratings(limit=clean_limit, source=DEFAULT_RS_SOURCE)
    except RelativeStrengthRepositoryUnavailable:
        total_count = 0
        rows = []

    if not rows:
        return RsRatingRankingResponse(
            as_of=date.today().isoformat(),
            source="missing",
            total_count=total_count,
            limit=clean_limit,
            rows=[],
        )

    return RsRatingRankingResponse(
        as_of=rows[0].date.isoformat(),
        source="database",
        total_count=total_count,
        limit=clean_limit,
        rows=[_row_to_schema(row, include_history=False) for row in rows],
    )


def get_relative_strength_for_ticker(ticker: str) -> RsRatingDetailResponse:
    try:
        row = rs_repository.get_latest_rs_rating(ticker, source=DEFAULT_RS_SOURCE)
    except RelativeStrengthRepositoryUnavailable:
        row = None

    if row is None:
        return RsRatingDetailResponse(found=False, source="missing", item=None)
    return RsRatingDetailResponse(found=True, source="database", item=_row_to_schema(row, include_history=True))


def _row_to_schema(row: RsRatingRow, *, include_history: bool = False) -> RsRatingItem:
    metadata = row.metadata_json or {}
    return RsRatingItem(
        ticker=row.ticker,
        name=row.name,
        date=row.date.isoformat(),
        rating=row.rating,
        score=row.score,
        percentile=row.percentile,
        method=row.method,
        source=row.source,
        universe_size=row.universe_size,
        ret_1m=_float_or_none(metadata.get("ret_1m_pct")),
        ret_3m=_float_or_none(metadata.get("ret_3m_pct")),
        ret_6m=_float_or_none(metadata.get("ret_6m_pct")),
        ret_12m=_float_or_none(metadata.get("ret_12m_pct")),
        excess_return_3m=_float_or_none(metadata.get("excess_return_3m_pct")),
        excess_return_6m=_float_or_none(metadata.get("excess_return_6m_pct")),
        excess_return_12m=_float_or_none(metadata.get("excess_return_12m_pct")),
        near_high_52w=_bool_or_none(metadata.get("near_high_52w")),
        new_high_52w=_bool_or_none(metadata.get("new_high_52w")),
        rs_ema21=_float_or_none(metadata.get("rs_ema21_last")),
        rs_ema50=_float_or_none(metadata.get("rs_ema50_last")),
        rs_history=_rs_history_from_metadata(metadata) if include_history else [],
    )


def _row_to_payload(row: RsRatingRow) -> dict:
    return _row_to_schema(row).model_dump()


def _normalize_tickers(tickers: list[str]) -> list[str]:
    return list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))[:5000]


def _float_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _rs_history_from_metadata(metadata: dict) -> list[RsLinePoint]:
    raw_history = metadata.get("rs_history")
    if not isinstance(raw_history, list):
        return []
    points: list[RsLinePoint] = []
    for item in raw_history:
        if not isinstance(item, dict):
            continue
        rs = _float_or_none(item.get("rs"))
        date_value = str(item.get("date") or "").strip()
        if not date_value or rs is None:
            continue
        points.append(
            RsLinePoint(
                date=date_value,
                rs=rs,
                rs_ema21=_float_or_none(item.get("rs_ema21")),
                rs_ema50=_float_or_none(item.get("rs_ema50")),
            )
        )
    return points
