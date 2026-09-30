from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import (
    BreadthDaily,
    FundamentalSnapshot,
    Institutional13FTrend,
    Instrument,
    JournalContextVersion,
    MarketAssessmentHistory,
    MarketSnapshot,
    PriceBar,
    RsRating,
    StockAssessmentHistory,
    TradeJournalEntry,
)
from app.db.session import SessionLocal
from app.services.market_calendar import previous_us_market_session_date


RULESET = "journal_reconstruction_v1_current_rules"


def backfill_trade_journal_contexts(
    *, entry_ids: list[str] | None = None, limit: int = 500
) -> dict[str, Any]:
    """Create immutable, idempotent context versions without altering original snapshots."""
    with SessionLocal() as db:
        statement = select(TradeJournalEntry).order_by(
            TradeJournalEntry.trade_date, TradeJournalEntry.created_at
        )
        if entry_ids:
            statement = statement.where(TradeJournalEntry.id.in_(entry_ids))
        entries = list(db.scalars(statement.limit(max(1, min(5000, limit)))).all())
        result: dict[str, Any] = {
            "entries_seen": len(entries),
            "versions_written": 0,
            "unchanged": 0,
            "partial": 0,
            "missing": 0,
            "errors": [],
        }
        for entry in entries:
            try:
                session_date = previous_us_market_session_date(entry.trade_date)
                cutoff = datetime.combine(session_date, time.max, tzinfo=UTC)
                stock = _stock_context(db, entry, session_date, cutoff)
                market = _market_context(db, session_date, cutoff)
                for block_type, context in (("stock", stock), ("market", market)):
                    written = _store_context(db, entry.id, block_type, context)
                    result["versions_written" if written else "unchanged"] += 1
                    if context["status"] == "partial":
                        result["partial"] += 1
                    elif context["status"] == "missing":
                        result["missing"] += 1
                db.commit()
            except Exception as exc:
                db.rollback()
                result["errors"].append({
                    "entry_id": entry.id,
                    "ticker": entry.ticker,
                    "reason": f"{type(exc).__name__}: {exc}",
                })
        return result


def _stock_context(db, entry: TradeJournalEntry, session_date: date, cutoff: datetime) -> dict:
    archived = db.scalar(
        select(StockAssessmentHistory)
        .where(
            StockAssessmentHistory.ticker == entry.ticker,
            StockAssessmentHistory.information_cutoff <= cutoff,
        )
        .order_by(desc(StockAssessmentHistory.information_cutoff))
        .limit(1)
    )
    if archived is not None:
        return {
            "status": "archived",
            "origin": "daily_archive",
            "archive_reference_id": archived.id,
            "information_cutoff": cutoff,
            "data_as_of": archived.data_as_of or archived.session_date,
            "assessment_version": archived.assessment_version,
            "ruleset_hash": archived.ruleset_hash,
            "sources": [archived.source],
            "reason_codes": [],
            "payload": archived.payload_json,
        }

    instrument = db.scalar(select(Instrument).where(Instrument.ticker == entry.ticker).limit(1))
    reasons: list[str] = []
    bars: list[PriceBar] = []
    if instrument is not None:
        bars = list(db.scalars(
            select(PriceBar)
            .where(PriceBar.instrument_id == instrument.id, PriceBar.date <= session_date)
            .order_by(desc(PriceBar.date))
            .limit(260)
        ).all())[::-1]
    if len(bars) < 200:
        reasons.append("price_history_below_200_sessions")

    fundamentals = db.scalar(
        select(FundamentalSnapshot)
        .where(FundamentalSnapshot.ticker == entry.ticker, FundamentalSnapshot.as_of <= session_date)
        .order_by(desc(FundamentalSnapshot.as_of), desc(FundamentalSnapshot.updated_at))
        .limit(1)
    )
    if fundamentals is None:
        reasons.append("fundamentals_missing")
    else:
        reasons.append("fundamental_publication_time_unverified")

    rating = None
    if instrument is not None:
        rating = db.scalar(
            select(RsRating)
            .where(RsRating.instrument_id == instrument.id, RsRating.date <= session_date)
            .order_by(desc(RsRating.date))
            .limit(1)
        )
    if rating is None:
        reasons.append("rs_rating_missing")

    filings = list(db.scalars(
        select(Institutional13FTrend)
        .where(
            Institutional13FTrend.ticker == entry.ticker,
            Institutional13FTrend.filing_date.is_not(None),
            Institutional13FTrend.filing_date <= session_date,
        )
        .order_by(desc(Institutional13FTrend.filing_date))
        .limit(100)
    ).all())
    if not filings:
        reasons.append("published_13f_missing")

    closes = [float(bar.close) for bar in bars if bar.close is not None]
    volumes = [float(bar.volume) for bar in bars if bar.volume is not None]
    metrics = {
        "last_close": closes[-1] if closes else None,
        "daily_return_pct": _return(closes[-1], closes[-2]) if len(closes) >= 2 else None,
        "sma10": _mean(closes[-10:]),
        "sma50": _mean(closes[-50:]),
        "sma200": _mean(closes[-200:]),
        "volume_factor_50d": (
            volumes[-1] / _mean(volumes[-50:])
            if len(volumes) >= 50 and _mean(volumes[-50:])
            else None
        ),
        "price_sessions": len(bars),
    }
    payload = {
        "ticker": entry.ticker,
        "snapshot_schema": "journal_context_v1",
        "context_status": "partial" if reasons else "reconstructed",
        "context_label": "Historisch rekonstruiert",
        "information_cutoff": cutoff.isoformat(),
        "data_as_of": session_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "assessment_version": RULESET,
        "temporal_reliability": "conservative_previous_session",
        "metrics": metrics,
        "relative_strength": _model_dict(rating),
        "fundamentals": _model_dict(fundamentals),
        "institutional_13f": [_model_dict(item) for item in filings],
        "data_quality": {"reason_codes": reasons},
    }
    return {
        "status": "partial" if reasons else "reconstructed",
        "origin": "reconstruction_current_rules",
        "archive_reference_id": None,
        "information_cutoff": cutoff,
        "data_as_of": session_date,
        "assessment_version": RULESET,
        "ruleset_hash": _fingerprint({"ruleset": RULESET}),
        "sources": sorted({bar.source for bar in bars} | ({rating.source} if rating else set())),
        "reason_codes": reasons,
        "payload": payload,
    }


def _market_context(db, session_date: date, cutoff: datetime) -> dict:
    archived = db.scalar(
        select(MarketAssessmentHistory)
        .where(
            MarketAssessmentHistory.benchmark == "SPY",
            MarketAssessmentHistory.information_cutoff <= cutoff,
        )
        .order_by(desc(MarketAssessmentHistory.information_cutoff))
        .limit(1)
    )
    if archived is not None:
        return {
            "status": "archived",
            "origin": "daily_archive",
            "archive_reference_id": archived.id,
            "information_cutoff": cutoff,
            "data_as_of": archived.session_date,
            "assessment_version": archived.assessment_version,
            "ruleset_hash": archived.ruleset_hash,
            "sources": [archived.source],
            "reason_codes": [],
            "payload": archived.payload_json,
        }

    snapshot = db.scalar(
        select(MarketSnapshot)
        .where(MarketSnapshot.date <= session_date)
        .order_by(desc(MarketSnapshot.date))
        .limit(1)
    )
    breadth = db.scalar(
        select(BreadthDaily)
        .where(BreadthDaily.date <= session_date)
        .order_by(desc(BreadthDaily.date))
        .limit(1)
    )
    spy = db.scalar(select(Instrument).where(Instrument.ticker == "SPY").limit(1))
    spy_bars = []
    if spy is not None:
        spy_bars = list(db.scalars(
            select(PriceBar)
            .where(PriceBar.instrument_id == spy.id, PriceBar.date <= session_date)
            .order_by(desc(PriceBar.date))
            .limit(2)
        ).all())
    reasons = []
    if snapshot is None:
        reasons.append("market_snapshot_missing")
    if breadth is None:
        reasons.append("breadth_missing")
    if len(spy_bars) < 2:
        reasons.append("benchmark_prices_missing")
    benchmark_return = None
    if len(spy_bars) == 2 and spy_bars[0].close is not None and spy_bars[1].close is not None:
        benchmark_return = _return(float(spy_bars[0].close), float(spy_bars[1].close))
    status = "missing" if snapshot is None and breadth is None and not spy_bars else "partial" if reasons else "reconstructed"
    payload = {
        "snapshot_schema": "journal_market_context_v1",
        "context_status": status,
        "information_cutoff": cutoff.isoformat(),
        "data_as_of": session_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "assessment_version": RULESET,
        "temporal_reliability": "conservative_previous_session",
        "benchmark": {"instrument": "SPY", "daily_return_pct": benchmark_return, "basis": "price_return"},
        "ampel": _model_dict(snapshot),
        "breadth": _model_dict(breadth),
        "data_quality": {"reason_codes": reasons},
    }
    return {
        "status": status,
        "origin": "reconstruction_current_rules",
        "archive_reference_id": None,
        "information_cutoff": cutoff,
        "data_as_of": session_date,
        "assessment_version": RULESET,
        "ruleset_hash": _fingerprint({"ruleset": RULESET}),
        "sources": ["market_snapshots", "breadth_daily", "price_bars"],
        "reason_codes": reasons,
        "payload": payload,
    }


def _store_context(db, entry_id: str, block_type: str, context: dict) -> bool:
    fingerprint = _fingerprint({
        "entry_id": entry_id,
        "block_type": block_type,
        "status": context["status"],
        "payload": {key: value for key, value in context["payload"].items() if key != "generated_at"},
    })
    statement = insert(JournalContextVersion).values(
        journal_entry_id=entry_id,
        block_type=block_type,
        status=context["status"],
        origin=context["origin"],
        information_cutoff=context["information_cutoff"],
        data_as_of=context["data_as_of"],
        archive_reference_id=context["archive_reference_id"],
        schema_version=1,
        assessment_version=context["assessment_version"],
        ruleset_hash=context["ruleset_hash"],
        data_fingerprint=fingerprint,
        sources_json=context["sources"],
        reason_codes_json=context["reason_codes"],
        payload_json=context["payload"],
    ).on_conflict_do_nothing(
        constraint="uq_journal_context_version"
    )
    return bool(db.execute(statement).rowcount)


def _model_dict(value: Any) -> dict:
    if value is None:
        return {}
    return {
        column.name: _json_value(getattr(value, column.name))
        for column in value.__table__.columns
        if column.name not in {"raw_json", "payload_json"}
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _fingerprint(value: Any) -> str:
    normalized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _return(current: float, previous: float) -> float | None:
    return round((current / previous - 1) * 100, 6) if previous else None
