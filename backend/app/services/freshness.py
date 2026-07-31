from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy import exists, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    AppSetting,
    BreadthDaily,
    EarningsEvent,
    FundamentalSnapshot,
    Institutional13FTrend,
    Instrument,
    MarketSnapshot,
    Position,
    PriceBar,
    RsRating,
    Universe,
    UniverseMember,
)
from app.db.session import SessionLocal
from app.domain.market.constants import (
    DEFAULT_MARKET_UNIVERSE_KEY,
    MARKET_CORE_PRICE_TICKERS,
    MARKET_INDEX_FALLBACK_TICKERS,
    MARKET_TREND_BENCHMARK,
    SECTOR_ETF_TICKERS,
)
from app.domain.market.volatility import VOLATILITY_TICKERS
from app.repositories import jobs as job_repository
from app.schemas import FreshnessResponse, ServiceFreshness
from app.services.market_calendar import ExpectedMarketSession, expected_us_market_session


MIN_PRICE_COVERAGE = 0.95
MIN_BREADTH_COVERAGE = 0.95
MIN_RS_COVERAGE = 0.95
MIN_EXTERNAL_RS_RATINGS = 4000
REQUIRED_MARKET_HELPER_TICKERS = list(
    dict.fromkeys([*MARKET_CORE_PRICE_TICKERS, *VOLATILITY_TICKERS, *SECTOR_ETF_TICKERS])
)


def get_freshness() -> FreshnessResponse:
    now = datetime.now(UTC)
    services = _cache_freshness(now)
    services.append(_job_freshness(now, "sell_ranking", "position_atr_monitor", max_lag_minutes=120))
    return FreshnessResponse(generated_at=now, services=services)


def _cache_freshness(now: datetime) -> list[ServiceFreshness]:
    expected_session = expected_us_market_session(now)
    try:
        with SessionLocal() as db:
            latest_market_snapshot = db.scalar(select(func.max(MarketSnapshot.date)))
            latest_13f = db.scalar(
                select(func.max(Institutional13FTrend.report_period)).where(
                    Institutional13FTrend.manager_cik == "AGGREGATE"
                )
            )
            prices = _price_universe_freshness(db, now, expected_session)
            breadth = _breadth_freshness(db, now, expected_session)
            relative_strength = _relative_strength_freshness(db, now, expected_session)
            trend_benchmark = _trend_benchmark_freshness(db, now)
            tracked_fundamentals = _tracked_fundamentals_freshness(db, now)
            latest_earnings_calendar = db.scalar(select(func.max(EarningsEvent.fetched_at)))
    except SQLAlchemyError:
        return [
            _missing("prices"),
            _missing("market_snapshot"),
            _missing("trend_benchmark"),
            _missing("market_breadth"),
            _missing("relative_strength"),
            _missing("fundamentals_tracked"),
            _missing("earnings_calendar"),
            _missing("institutional_13f"),
        ]

    return [
        prices,
        _session_date_freshness(
            now,
            "market_snapshot",
            latest_market_snapshot,
            expected_session=expected_session,
            detail="Gespeicherter MarketSnapshot für Marktstatus und Signalübersicht.",
        ),
        trend_benchmark,
        breadth,
        relative_strength,
        tracked_fundamentals,
        _datetime_freshness(
            now,
            "earnings_calendar",
            latest_earnings_calendar,
            max_lag_minutes=26 * 60,
            detail="FMP Earnings-Kalender für gezielte Fundamental-Updates rund um Berichtstermine.",
            metadata={"expected_interval": "twice_daily"},
        ),
        _date_freshness(
            now,
            "institutional_13f",
            latest_13f,
            max_lag_days=120,
            detail="Letzter aggregierter SEC-Form-13F-Reportzeitraum. 13F-Daten werden quartalsweise veröffentlicht.",
            metadata={"expected_interval": "quarterly", "max_lag_days": 120},
        ),
    ]


def _price_universe_freshness(
    db,
    now: datetime,
    expected_session: ExpectedMarketSession,
) -> ServiceFreshness:
    universe_id = db.scalar(select(Universe.id).where(Universe.key == DEFAULT_MARKET_UNIVERSE_KEY))
    if universe_id is None:
        latest = db.scalar(select(func.max(PriceBar.date)).where(PriceBar.close.is_not(None)))
        return _session_date_freshness(
            now,
            "prices",
            latest,
            expected_session=expected_session,
            detail="Aktives Aktienuniversum fehlt; nur das maximale Price-Bar-Datum kann geprüft werden.",
            metadata={"coverage_available": False},
        )

    membership_date = max(expected_session.date, now.date())
    active_member_filter = (
        UniverseMember.universe_id == universe_id,
        UniverseMember.valid_from <= membership_date,
        (UniverseMember.valid_to.is_(None)) | (UniverseMember.valid_to >= membership_date),
    )
    expected_count = int(
        db.scalar(
            select(func.count(func.distinct(UniverseMember.instrument_id))).where(
                *active_member_filter
            )
        )
        or 0
    )
    current_count = int(
        db.scalar(
            select(func.count(func.distinct(UniverseMember.instrument_id))).where(
                *active_member_filter,
                exists(
                    select(PriceBar.id).where(
                        PriceBar.instrument_id == UniverseMember.instrument_id,
                        PriceBar.date >= expected_session.date,
                        PriceBar.close.is_not(None),
                    )
                ),
            )
        )
        or 0
    )
    latest = (
        expected_session.date
        if current_count
        else db.scalar(select(func.max(PriceBar.date)).where(PriceBar.close.is_not(None)))
    )
    coverage = current_count / expected_count if expected_count else 0.0
    latest_price_date = (
        select(func.max(PriceBar.date))
        .where(
            PriceBar.instrument_id == Instrument.id,
            PriceBar.close.is_not(None),
        )
        .correlate(Instrument)
        .scalar_subquery()
    )
    core_rows = db.execute(
        select(Instrument.ticker, latest_price_date).where(
            Instrument.ticker.in_(REQUIRED_MARKET_HELPER_TICKERS)
        )
    ).all()
    core_dates = {str(ticker): value for ticker, value in core_rows if value is not None}
    missing_core = [
        ticker
        for ticker in REQUIRED_MARKET_HELPER_TICKERS
        if core_dates.get(ticker) is None or core_dates[ticker] < expected_session.date
    ]
    status = (
        "fresh"
        if latest is not None
        and latest >= expected_session.date
        and coverage >= MIN_PRICE_COVERAGE
        and not missing_core
        else "stale"
    )
    return ServiceFreshness(
        name="prices",
        status=status,
        as_of=latest.isoformat() if latest else "",
        lag_minutes=_date_lag_minutes(now, latest),
        detail=(
            f"Price-Cache {current_count}/{expected_count} aktive Universe-Titel "
            f"für {expected_session.date.isoformat()}; Kernsymbole vollständig: "
            f"{'ja' if not missing_core else 'nein'}."
        ),
        metadata={
            **_session_metadata(expected_session),
            "universe": DEFAULT_MARKET_UNIVERSE_KEY,
            "expected_count": expected_count,
            "current_count": current_count,
            "coverage_ratio": coverage,
            "minimum_coverage_ratio": MIN_PRICE_COVERAGE,
            "missing_core_tickers": missing_core,
            "core_dates": {
                ticker: value.isoformat()
                for ticker, value in core_dates.items()
            },
        },
    )


def _breadth_freshness(
    db,
    now: datetime,
    expected_session: ExpectedMarketSession,
) -> ServiceFreshness:
    row = db.scalars(
        select(BreadthDaily)
        .where(BreadthDaily.universe == DEFAULT_MARKET_UNIVERSE_KEY)
        .order_by(BreadthDaily.date.desc())
        .limit(1)
    ).first()
    if row is None:
        return _missing(
            "market_breadth",
            detail="Keine BreadthDaily-Daten für das aktive Aktienuniversum.",
            metadata=_session_metadata(expected_session),
        )
    metadata = dict(row.metadata_json or {})
    coverage = float(metadata.get("coverage_ratio") or 0.0)
    status = (
        "fresh"
        if row.date >= expected_session.date and coverage >= MIN_BREADTH_COVERAGE
        else "stale"
    )
    return ServiceFreshness(
        name="market_breadth",
        status=status,
        as_of=row.date.isoformat(),
        lag_minutes=_date_lag_minutes(now, row.date),
        detail=(
            f"BreadthDaily für {row.universe}: Coverage {coverage * 100:.1f}% "
            f"am {row.date.isoformat()}."
        ),
        metadata={
            **_session_metadata(expected_session),
            "universe": row.universe,
            "coverage_ratio": coverage,
            "minimum_coverage_ratio": MIN_BREADTH_COVERAGE,
            "loaded_universe": int(metadata.get("loaded_universe") or 0),
            "universe_size": int(metadata.get("universe_size") or 0),
        },
    )


def _relative_strength_freshness(
    db,
    now: datetime,
    expected_session: ExpectedMarketSession,
) -> ServiceFreshness:
    source = _configured_rs_source(db)
    latest = db.scalar(select(func.max(RsRating.date)).where(RsRating.source == source))
    if latest is None:
        return _missing(
            "relative_strength",
            detail=f"Keine RS-Ratings für die gewählte Quelle {source}.",
            metadata={**_session_metadata(expected_session), "source": source},
        )
    count = int(
        db.scalar(
            select(func.count()).select_from(RsRating).where(
                RsRating.source == source,
                RsRating.date == latest,
            )
        )
        or 0
    )
    expected_count = _active_universe_count(db, expected_session.date)
    external_source = source == "csv_latest"
    coverage = (
        1.0
        if external_source and count >= MIN_EXTERNAL_RS_RATINGS
        else min(1.0, count / expected_count)
        if expected_count
        else 0.0
    )
    if external_source:
        status = (
            "fresh"
            if latest >= expected_session.date and count >= MIN_EXTERNAL_RS_RATINGS
            else "stale"
        )
        detail = (
            f"Externe RS-Quelle {source}: {count} Ratings mit Datenstand "
            f"{latest.isoformat()}."
        )
    else:
        status = (
            "fresh"
            if latest >= expected_session.date and coverage >= MIN_RS_COVERAGE
            else "stale"
        )
        detail = (
            f"RS-Quelle {source}: {count}/{expected_count} Ratings, "
            f"Coverage {coverage * 100:.1f}%."
        )
    return ServiceFreshness(
        name="relative_strength",
        status=status,
        as_of=latest.isoformat(),
        lag_minutes=_date_lag_minutes(now, latest),
        detail=detail,
        metadata={
            **_session_metadata(expected_session),
            "source": source,
            "ratings_count": count,
            "expected_count": expected_count,
            "coverage_ratio": coverage,
            "minimum_coverage_ratio": MIN_RS_COVERAGE,
            "minimum_external_ratings": MIN_EXTERNAL_RS_RATINGS,
        },
    )


def _active_universe_count(db, as_of: date) -> int:
    universe_id = db.scalar(select(Universe.id).where(Universe.key == DEFAULT_MARKET_UNIVERSE_KEY))
    if universe_id is None:
        return 0
    membership_date = max(as_of, date.today())
    return int(
        db.scalar(
            select(func.count(func.distinct(UniverseMember.instrument_id))).where(
                UniverseMember.universe_id == universe_id,
                UniverseMember.valid_from <= membership_date,
                (UniverseMember.valid_to.is_(None)) | (UniverseMember.valid_to >= membership_date),
            )
        )
        or 0
    )


def _configured_rs_source(db) -> str:
    row = db.get(AppSetting, "runtime")
    value = (row.value_json or {}).get("rs_rating_source") if row is not None else None
    clean = str(value or "computed").strip().lower()
    return clean if clean in {"computed", "csv_latest"} else "computed"


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


def _session_date_freshness(
    now: datetime,
    service_name: str,
    latest_date: date | None,
    *,
    expected_session: ExpectedMarketSession,
    detail: str = "",
    metadata: dict | None = None,
) -> ServiceFreshness:
    if latest_date is None:
        return _missing(
            service_name,
            detail=detail,
            metadata={**_session_metadata(expected_session), **(metadata or {})},
        )
    return ServiceFreshness(
        name=service_name,
        status="fresh" if latest_date >= expected_session.date else "stale",
        as_of=latest_date.isoformat(),
        lag_minutes=_date_lag_minutes(now, latest_date),
        detail=detail,
        metadata={**_session_metadata(expected_session), **(metadata or {})},
    )


def _datetime_freshness(
    now: datetime,
    service_name: str,
    value: datetime | None,
    *,
    max_lag_minutes: int,
    detail: str = "",
    metadata: dict | None = None,
) -> ServiceFreshness:
    if value is None:
        return _missing(service_name, detail=detail, metadata=metadata)
    as_of = _as_utc(value)
    lag_minutes = _lag_minutes(now, as_of)
    return ServiceFreshness(
        name=service_name,
        status="fresh" if lag_minutes <= max_lag_minutes else "stale",
        as_of=as_of.isoformat(),
        lag_minutes=lag_minutes,
        detail=detail,
        metadata=metadata or {},
    )


def _trend_benchmark_freshness(db, now: datetime) -> ServiceFreshness:
    expected_session = expected_us_market_session(now)
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
    return _session_date_freshness(
        now,
        "trend_benchmark",
        latest_date,
        expected_session=expected_session,
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


def _session_metadata(session: ExpectedMarketSession) -> dict:
    return {
        "expected_as_of": session.date.isoformat(),
        "session_phase": session.phase,
        "session_open_at": session.open_at.isoformat() if session.open_at else None,
        "session_close_at": session.close_at.isoformat() if session.close_at else None,
    }


def _date_lag_minutes(now: datetime, value: date | None) -> int:
    if value is None:
        return 0
    return _lag_minutes(now, datetime.combine(value, time.min, tzinfo=UTC))


def _lag_minutes(now: datetime, then: datetime) -> int:
    return max(0, int((now - then).total_seconds() // 60))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
