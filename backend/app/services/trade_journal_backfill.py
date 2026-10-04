from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
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
from app.domain.market.ampel import AMPEL_RULESET_VERSION, POWER_TREND_RULESET_VERSION, compute_trend_ampel
from app.domain.market.regime import MarketRegimeInput, market_regime_warning_checks
from app.domain.stocks.assessment import compute_stock_assessment
from app.domain.stocks.relative_strength import compute_relative_strength_line
from app.services.market import _build_ampel_warning_checks, _selected_market_ampel_logic, _trend_ampel_metrics
from app.services.stocks import _fundamentals_context, _rs_context, _assessment_score_weights
from app.repositories.relative_strength import RsRatingRow
from app.services.market_calendar import previous_us_market_session_date
from app.services.fx import yahoo_quote_currency


RULESET = "journal_reconstruction_v2_current_rules"
MARKET_RULESET = "journal_market_reconstruction_v3"


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
        stock_cache = {}
        market_cache = {}
        for entry in entries:
            try:
                session_date = previous_us_market_session_date(entry.trade_date)
                cutoff = datetime.combine(session_date, time.max, tzinfo=UTC)
                stock_key = (entry.ticker, session_date)
                if stock_key not in stock_cache:
                    stock_cache[stock_key] = _stock_context(db, entry, session_date, cutoff)
                if session_date not in market_cache:
                    market_cache[session_date] = _market_context(db, session_date, cutoff)
                stock = stock_cache[stock_key]
                market = market_cache[session_date]
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
            StockAssessmentHistory.session_date == session_date,
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
            "payload": {**archived.payload_json, "context_status": "archived",
                        "information_cutoff": archived.information_cutoff.isoformat(),
                        "data_as_of": archived.session_date.isoformat()},
        }

    instrument = db.scalar(select(Instrument).where(Instrument.ticker == entry.ticker).limit(1))
    reasons: list[str] = []
    bars: list[PriceBar] = []
    if instrument is not None:
        bars = list(db.scalars(
            select(PriceBar)
            .where(PriceBar.instrument_id == instrument.id, PriceBar.date <= session_date)
            .order_by(desc(PriceBar.date))
            .limit(800)
        ).all())[::-1]
    if len(bars) < 200:
        reasons.append("price_history_below_200_sessions")

    fundamentals = db.scalar(
        select(FundamentalSnapshot)
        .where(FundamentalSnapshot.ticker == entry.ticker, FundamentalSnapshot.as_of <= session_date,
            FundamentalSnapshot.created_at <= cutoff, FundamentalSnapshot.updated_at <= cutoff)
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

    benchmark_bars = _bars_for_ticker(db, "SPY", session_date, 800)
    rs_context = _rs_context(RsRatingRow(
        ticker=entry.ticker, name="", date=rating.date, rating=rating.rating,
        score=rating.score, percentile=rating.percentile, method=rating.method,
        source=rating.source, universe_size=rating.universe_size,
        metadata_json=rating.metadata_json or {},
    ), load_computed=False) if rating is not None else {}
    line = compute_relative_strength_line(bars, benchmark_bars)
    if line is not None:
        # Recompute the line from dated prices, never reuse today's line/portfolio.
        from types import SimpleNamespace
        line_row = SimpleNamespace(ticker=entry.ticker, date=line.date, rating=None,
            score=None, percentile=None, method="historical_line", source="computed",
            universe_size=0, metadata_json=line.metadata)
        rs_context = {**rs_context, **{
            key: value for key, value in _rs_context(line_row, load_computed=False).items()
            if value is not None and value != [] and key not in {"rating", "percentile", "score", "method", "source", "universe_size", "as_of"}
        }}
    fundamental_context = _fundamentals_context(fundamentals, load_earnings=False)
    fundamental_context.pop("next_earnings_date", None)
    assessment = asdict(compute_stock_assessment(
        entry.ticker, bars, rs_context=rs_context,
        fundamentals_context=fundamental_context, score_weights=_assessment_score_weights(),
    )) if len(bars) >= 50 else {}
    if assessment:
        # Missing fundamentals must not turn into a neutral historical score.
        if fundamentals is None:
            assessment["fundamental_v2"] = {"score": None, "status": "missing"}
            assessment["overall_v2"] = {"score": None, "status": "partial"}
        assessment["as_of"] = bars[-1].date.isoformat()
    if bars and bars[-1].date != session_date:
        reasons.append("stock_prices_stale")
    closes = [float(bar.close) for bar in bars if bar.close is not None]
    volumes = [float(bar.volume) for bar in bars if bar.volume is not None]
    metrics = {
        "last_close": closes[-1] if closes else None,
        "daily_return_pct": _return(closes[-1], closes[-2]) if len(closes) >= 2 else None,
        "sma10": _mean(closes[-10:]) if len(closes) >= 10 else None,
        "sma50": _mean(closes[-50:]) if len(closes) >= 50 else None,
        "sma200": _mean(closes[-200:]) if len(closes) >= 200 else None,
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
        "data_as_of": bars[-1].date.isoformat() if bars else None,
        "generated_at": datetime.now(UTC).isoformat(),
        "assessment_version": RULESET,
        "temporal_reliability": "conservative_previous_session",
        "assessment": assessment,
        "quote_currency": yahoo_quote_currency(entry.ticker),
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
        "data_as_of": bars[-1].date if bars else None,
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
            MarketAssessmentHistory.session_date == session_date,
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
            "payload": {**archived.payload_json, "context_status": "archived",
                        "information_cutoff": archived.information_cutoff.isoformat(),
                        "data_as_of": archived.session_date.isoformat()},
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
    trend_bars = _bars_for_ticker(db, "^GSPC", session_date, 800)
    stored_metrics = (snapshot.metrics_json or {}) if snapshot else {}
    stored_trend = stored_metrics.get("trend_ampel") or {}
    recorded_logic = stored_metrics.get("market_ampel_logic") or stored_trend.get("logic")
    historical_logic_known = bool(snapshot and snapshot.date == session_date and recorded_logic in {"current", "ibd"})
    logic = recorded_logic if historical_logic_known else _selected_market_ampel_logic()
    logic_origin = "historical_snapshot" if historical_logic_known else "current_settings_reconstruction"
    points = compute_trend_ampel([_model_dict(bar) for bar in trend_bars], logic=logic) if trend_bars else []
    checks = _build_ampel_warning_checks(
        points=points, latest=points[-1], intermarket=[], defensive_lead=None,
        defensive_spread_pct=None, index_name="S&P 500",
    ) if len(points) >= 200 else []
    if snapshot is not None and snapshot.date != session_date:
        reasons.append("market_snapshot_stale")
    if breadth is not None and breadth.date != session_date:
        reasons.append("breadth_stale")
    if spy_bars and spy_bars[0].date != session_date:
        reasons.append("benchmark_prices_stale")
    if not checks:
        reasons.append("market_warning_history_missing")
    if not historical_logic_known:
        reasons.append("historical_market_logic_unknown")
    if logic == "ibd" and any(not point.price_data_complete for point in points[-50:]):
        reasons.append("market_ohlc_incomplete")
    status = "missing" if snapshot is None and breadth is None and not spy_bars else "partial" if reasons else "reconstructed"
    market_checks = []
    if snapshot is not None:
        stored = snapshot.metrics_json or {}
        required = {"mcclellan", "advancers", "decliners", "new_highs", "new_lows", "coverage_ratio"}
        if required <= stored.keys() and all(stored[key] is not None for key in required):
            market_checks = market_regime_warning_checks(MarketRegimeInput(
                pct_above_20sma=stored.get("pct_above_20sma"),
                pct_above_50sma=stored.get("pct_above_50sma"),
                pct_above_200sma=stored.get("pct_above_200sma"),
                **{key: stored[key] for key in required},
                universe_size=stored.get("universe_size", 0),
                covered_count=stored.get("covered_count", 0),
                volatility_regime=snapshot.volatility_regime,
                margin_debt_summary=stored.get("margin_debt"),
            ))
    payload = {
        "snapshot_schema": "journal_market_context_v2",
        "context_status": status,
        "information_cutoff": cutoff.isoformat(),
        "data_as_of": session_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "assessment_version": MARKET_RULESET,
        "temporal_reliability": "conservative_previous_session",
        "benchmark": {"instrument": "SPY", "daily_return_pct": benchmark_return, "basis": "price_return",
                      "as_of": spy_bars[0].date.isoformat() if spy_bars else None},
        "trend": ({**_trend_ampel_metrics(points[-1], ticker="^GSPC"), "source": "historical_prices",
                   "logic_origin": logic_origin, "historical_logic_known": historical_logic_known}
                  if len(points) >= 200 else {}),
        "market_ampel_logic": logic,
        "market_ampel_ruleset": AMPEL_RULESET_VERSION,
        "logic_origin": logic_origin,
        "historical_logic_known": historical_logic_known,
        "market_warning_checks": market_checks,
        "warning_checks": [check.model_dump(mode="json") for check in checks],
        "warning_scope": "Historische Indexwarnungen nach heutigen Regeln. Intermarket- und Sektorrotation sind nicht enthalten.",
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
        "assessment_version": MARKET_RULESET,
        "ruleset_hash": _fingerprint({"ruleset": MARKET_RULESET, "logic": logic, "ampel_ruleset": AMPEL_RULESET_VERSION, "powertrend_ruleset": POWER_TREND_RULESET_VERSION}),
        "sources": ["market_snapshots", "breadth_daily", "price_bars"],
        "reason_codes": reasons,
        "payload": payload,
    }


def _bars_for_ticker(db, ticker: str, session_date: date, limit: int) -> list:
    return list(db.scalars(
        select(PriceBar).join(Instrument, PriceBar.instrument_id == Instrument.id)
        .where(Instrument.ticker == ticker, PriceBar.date <= session_date)
        .order_by(desc(PriceBar.date)).limit(limit)
    ).all())[::-1]


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
    ).returning(JournalContextVersion.id)
    # Some PostgreSQL drivers expose ``rowcount == -1`` for INSERT .. ON
    # CONFLICT statements.  ``bool(-1)`` incorrectly reported an unchanged
    # context as newly written even though the unique constraint did its job.
    return db.execute(statement).scalar_one_or_none() is not None


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


if __name__ == "__main__":
    result = backfill_trade_journal_contexts(limit=5000)
    print(json.dumps(result, default=str))
    if result["errors"]:
        raise SystemExit(1)
