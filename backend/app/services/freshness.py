from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    AppSetting,
    BreadthDaily,
    FundamentalSnapshot,
    Institutional13FTrend,
    Instrument,
    MarketSnapshot,
    Position,
    PriceBar,
    RsRating,
)
from app.db.session import SessionLocal
from app.domain.market.constants import MARKET_INDEX_FALLBACK_TICKERS, MARKET_TREND_BENCHMARK
from app.repositories import jobs as job_repository
from app.schemas import FreshnessResponse, ServiceFreshness


def get_freshness() -> FreshnessResponse:
    now = datetime.now(UTC)
    services = _cache_freshness(now)
    services.append(_job_freshness(now, "sell_ranking", "position_atr_monitor", max_lag_minutes=120))
    return FreshnessResponse(generated_at=now, services=services)


def _cache_freshness(now: datetime) -> list[ServiceFreshness]:
    try:
        with SessionLocal() as db:
            latest_price = db.scalar(select(func.max(PriceBar.date)).where(PriceBar.close.is_not(None)))
            latest_market_snapshot = db.scalar(select(func.max(MarketSnapshot.date)))
            latest_breadth = db.scalar(select(func.max(BreadthDaily.date)))
            latest_rs = db.scalar(select(func.max(RsRating.date)))
            latest_13f = db.scalar(
                select(func.max(Institutional13FTrend.report_period)).where(
                    Institutional13FTrend.manager_cik == "AGGREGATE"
                )
            )
            trend_benchmark = _trend_benchmark_freshness(db, now)
            tracked_fundamentals = _tracked_fundamentals_freshness(db, now)
    except SQLAlchemyError:
        return [
            _missing("prices"),
            _missing("market_snapshot"),
            _missing("trend_benchmark"),
            _missing("market_breadth"),
            _missing("relative_strength"),
            _missing("fundamentals_tracked"),
            _missing("institutional_13f"),
        ]

    return [
        _date_freshness(now, "prices", latest_price, max_lag_days=5, detail="Maximales Datum über alle gecachten PriceBars."),
        _date_freshness(now, "market_snapshot", latest_market_snapshot, max_lag_days=5, detail="Gespeicherter MarketSnapshot für Marktstatus und Signalübersicht."),
        trend_benchmark,
        _date_freshness(now, "market_breadth", latest_breadth, max_lag_days=5, detail="BreadthDaily-Daten für Marktbreite, McClellan, NH/NL und AD-Linie."),
        _date_freshness(now, "relative_strength", latest_rs, max_lag_days=7, detail="Zuletzt berechnete Relative-Strength-Ratings."),
        tracked_fundamentals,
        _date_freshness(
            now,
            "institutional_13f",
            latest_13f,
            max_lag_days=120,
            detail="Letzter aggregierter SEC-Form-13F-Reportzeitraum. 13F-Daten werden quartalsweise veröffentlicht.",
            metadata={"expected_interval": "quarterly", "max_lag_days": 120},
        ),
    ]


def _job_freshness(
    now: datetime,
    service_name: str,
    job_type: str,
    *,
    max_lag_minutes: int,
) -> ServiceFreshness:
    latest_job = next(
        (
            job
            for job in job_repository.list_jobs(limit=80)
            if job.job_type == job_type and job.status in {"done", "skipped", "failed", "cancelled"}
        ),
        None,
    )
    if latest_job is None or latest_job.finished_at is None:
        return _missing(service_name)

    finished_at = _as_utc(latest_job.finished_at)
    lag_minutes = _lag_minutes(now, finished_at)
    status = "fresh" if latest_job.status in {"done", "skipped"} and lag_minutes <= max_lag_minutes else "stale"
    return ServiceFreshness(
        name=service_name,
        status=status,
        as_of=finished_at.isoformat(),
        lag_minutes=lag_minutes,
    )


def _date_freshness(
    now: datetime,
    service_name: str,
    latest_date: date | None,
    *,
    max_lag_days: int,
    detail: str = "",
    metadata: dict | None = None,
) -> ServiceFreshness:
    if latest_date is None:
        return _missing(service_name, detail=detail, metadata=metadata)
    as_of_dt = datetime.combine(latest_date, time.min, tzinfo=UTC)
    lag_minutes = _lag_minutes(now, as_of_dt)
    return ServiceFreshness(
        name=service_name,
        status="fresh" if lag_minutes <= max_lag_days * 24 * 60 else "stale",
        as_of=latest_date.isoformat(),
        lag_minutes=lag_minutes,
        detail=detail,
        metadata=metadata or {},
    )


def _trend_benchmark_freshness(db, now: datetime) -> ServiceFreshness:
    candidates = [MARKET_TREND_BENCHMARK, *MARKET_INDEX_FALLBACK_TICKERS.get(MARKET_TREND_BENCHMARK, [])]
    rows = db.execute(
        select(Instrument.ticker, func.max(PriceBar.date))
        .join(PriceBar, PriceBar.instrument_id == Instrument.id)
        .where(
            Instrument.ticker.in_(candidates),
            PriceBar.close.is_not(None),
        )
        .group_by(Instrument.ticker)
    ).all()
    dates_by_ticker = {str(ticker): latest_date for ticker, latest_date in rows if latest_date is not None}
    used_ticker = next((ticker for ticker in candidates if ticker in dates_by_ticker), None)
    latest_date = dates_by_ticker.get(used_ticker or "")
    candidate_dates = {
        ticker: value.isoformat()
        for ticker, value in dates_by_ticker.items()
    }
    detail = (
        f"Trend-Ampel nutzt {used_ticker or MARKET_TREND_BENCHMARK}. "
        f"Fallback-Reihen: {', '.join(candidates[1:]) or 'keine'}."
    )
    return _date_freshness(
        now,
        "trend_benchmark",
        latest_date,
        max_lag_days=5,
        detail=detail,
        metadata={
            "benchmark": MARKET_TREND_BENCHMARK,
            "used_ticker": used_ticker,
            "candidate_dates": candidate_dates,
        },
    )


def _tracked_fundamentals_freshness(db, now: datetime) -> ServiceFreshness:
    tickers = _tracked_fundamental_tickers(db)
    if not tickers:
        latest_date = db.scalar(select(func.max(FundamentalSnapshot.as_of)))
        return _date_freshness(
            now,
            "fundamentals_tracked",
            latest_date,
            max_lag_days=3,
            detail="Kein getracktes Aktien-Set; Datum über alle Fundamental-Snapshots.",
            metadata={"tracked_tickers": [], "missing_tickers": []},
        )

    rows = db.execute(
        select(FundamentalSnapshot.ticker, func.max(FundamentalSnapshot.as_of))
        .where(FundamentalSnapshot.ticker.in_(tickers))
        .group_by(FundamentalSnapshot.ticker)
    ).all()
    latest_by_ticker = {
        str(ticker).upper(): latest_date
        for ticker, latest_date in rows
        if ticker and latest_date is not None
    }
    missing_tickers = [ticker for ticker in tickers if ticker not in latest_by_ticker]
    if not latest_by_ticker:
        return _missing(
            "fundamentals_tracked",
            detail="Für offene Positionen, Watchlist oder zuletzt geöffnete Aktien fehlen Fundamental-Snapshots.",
            metadata={"tracked_tickers": tickers, "missing_tickers": missing_tickers},
        )

    oldest_fresh_ticker = min(latest_by_ticker, key=lambda ticker: latest_by_ticker[ticker])
    latest_date = latest_by_ticker[oldest_fresh_ticker]
    base = _date_freshness(
        now,
        "fundamentals_tracked",
        latest_date,
        max_lag_days=3,
        detail=(
            "Fundamental-Cache für offene Positionen, Watchlist und zuletzt geöffnete Aktien. "
            f"Ältester aktueller Ticker: {oldest_fresh_ticker}."
        ),
        metadata={
            "tracked_tickers": tickers,
            "missing_tickers": missing_tickers,
            "ticker_dates": {
                ticker: value.isoformat()
                for ticker, value in latest_by_ticker.items()
            },
        },
    )
    if missing_tickers and base.status == "fresh":
        return base.model_copy(update={"status": "stale"})
    return base


def _tracked_fundamental_tickers(db) -> list[str]:
    tickers: list[str] = []
    rows = db.scalars(select(Position.ticker).where(Position.is_open.is_(True))).all()
    tickers.extend(str(ticker) for ticker in rows if ticker)

    workspace = db.get(AppSetting, "workspace")
    if workspace is not None and isinstance(workspace.value_json, dict):
        values = workspace.value_json
        tickers.extend(_list_values(values.get("watchlist")))
        tickers.extend(_list_values(values.get("recent_tickers")))

    return _dedupe_tickers(tickers)[:100]


def _list_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _dedupe_tickers(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        clean = str(value or "").strip().upper()
        if clean and clean not in out:
            out.append(clean)
    return out


def _missing(service_name: str, *, detail: str = "", metadata: dict | None = None) -> ServiceFreshness:
    return ServiceFreshness(name=service_name, status="missing", as_of="", lag_minutes=0, detail=detail, metadata=metadata or {})


def _lag_minutes(now: datetime, then: datetime) -> int:
    return max(0, int((now - then).total_seconds() // 60))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
