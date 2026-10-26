"""Cached chart analysis and worker-side universe scanning. No network I/O in reads."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from collections import Counter
from math import isfinite
from time import monotonic

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import Instrument
from app.db.session import SessionLocal
from app.domain.chart_patterns import (
    ALGORITHM_VERSION,
    Bar,
    LABELS,
    PatternParameters,
    detect_patterns,
)
from app.domain.chart_data_quality import prepare_segments
from app.repositories import settings as repository
from app.repositories.prices import list_price_bars, list_price_bars_for_tickers
from app.services.market_calendar import completed_ticker_market_session
from app.services.chart_price_repair import repair_chart_history


CONFIG_KEY = "chart_analysis_config_v1"
RESULT_KEY = "chart_analysis_scan_v1"
REPAIR_KEY = "chart_analysis_price_repairs_v1"


def _quality_payload(quality) -> dict:
    return {
        "partial": quality.partial,
        "segment_count": len(quality.segments),
        "analysed_bar_count": quality.analysed_bar_count,
        "excluded_bar_count": quality.excluded_bar_count,
        "boundary_count": quality.boundary_count,
        "short_segment_count": quality.short_segment_count,
        "short_segment_bar_count": quality.short_segment_bar_count,
        "issues": quality.issues,
    }


def _split_issues(issues, events, *, cutoff: date, repair=None) -> None:
    """Annotate evidence, without inferring or applying any price correction."""
    events = {**(events or {}), **((repair or {}).get("split_events") or {})}
    for issue in issues:
        if issue["code"] != "extreme_jump":
            continue
        day = date.fromisoformat(issue["date"])
        evidence = []
        for text, ratio in (events or {}).items():
            try:
                split_day = date.fromisoformat(text)
                factor = float(ratio)
            except (TypeError, ValueError):
                continue
            if (
                split_day <= cutoff
                and abs((split_day - day).days) <= 5
                and isfinite(factor)
                and factor > 0
            ):
                evidence.append({"date": text, "ratio": factor})
        if evidence:
            issue["split_events"] = sorted(evidence, key=lambda event: event["date"])
            issue["reason"] += (
                " Ein gespeichertes Splitereignis liegt in zeitlicher Nähe; keine automatische Preisumrechnung."
            )
        if repair and issue["date"] in repair.get("verified_jump_dates", []):
            issue["provider_reconfirmed"] = True
            issue["reason"] += (
                " Die Bewegung besteht auch im vollständigen Neuabruf; ihre Ursache bleibt offen."
            )


def _segment_patterns(ticker, quality, parameters, *, last_date):
    for segment in quality.segments:
        limited = segment[-1].date < last_date
        for pattern in detect_patterns(ticker, segment, parameters):
            row = pattern.model_dump()
            row.update(
                segment_start=segment[0].date.isoformat(),
                segment_end=segment[-1].date.isoformat(),
                continuity_limited=limited,
            )
            if limited:
                row["warnings"].append(
                    f"Historischer Kursabschnitt endet am {segment[-1].date}; "
                    "der Musterstatus gilt nur bis zu diesem Datum. Spätere Gültigkeit unbekannt."
                )
            yield row


def _split_events(ticker):
    try:
        with SessionLocal() as db:
            return (
                db.scalar(
                    select(Instrument.metadata_json["stock_splits"]).where(
                        Instrument.ticker == ticker
                    )
                )
                or {}
            )
    except SQLAlchemyError as exc:
        raise repository.SettingsRepositoryUnavailable(str(exc)) from exc


def get_config() -> dict:
    parameters = PatternParameters.model_validate(repository._read_json_setting(CONFIG_KEY))
    return {
        "parameters": parameters.model_dump(),
        "defaults": PatternParameters().model_dump(),
        "parameter_hash": parameters.fingerprint,
        "algorithm_version": ALGORITHM_VERSION,
        "patterns": LABELS,
    }


def save_config(parameters: PatternParameters) -> dict:
    repository._write_json_setting(
        CONFIG_KEY, parameters.model_dump(), description="Chartanalyse: Regeln aus Kapitel 4.2"
    )
    return get_config()


def _bar(row) -> Bar:
    # Yahoo OHLC already account for splits; split_adjustment_factor is ONLY
    # used for transaction valuation elsewhere. Applying it here would double-adjust.
    return Bar(
        date=row.date,
        open=float(row.open or 0),
        high=float(row.high or 0),
        low=float(row.low or 0),
        close=float(row.close or 0),
        volume=row.volume,
    )


def _chart_number(value):
    return value if value is not None and isfinite(value) else None


def analyse(ticker: str, *, as_of: date | None = None) -> dict:
    parameters = PatternParameters.model_validate(get_config()["parameters"])
    cutoff = min(as_of or date.max, completed_ticker_market_session(ticker).date)
    rows = list_price_bars(ticker, start_date=cutoff - timedelta(days=850))
    # Multiple providers for one date are ambiguous, never silently blended.
    rows = [r for r in rows if r.date <= cutoff]
    bars = [_bar(r) for r in rows]
    quality = prepare_segments(bars)
    if any(issue["code"] == "extreme_jump" for issue in quality.issues):
        state = repository._read_json_setting(REPAIR_KEY).get(ticker, {})
        _split_issues(quality.issues, _split_events(ticker), cutoff=cutoff, repair=state)
    excluded_dates = {
        issue["date"]
        for issue in quality.issues
        if issue["code"] in {"invalid_ohlc", "invalid_volume", "duplicate_date"}
    }
    usable_dates = [bar.date for bar in bars if bar.date.isoformat() not in excluded_dates]
    price_date = max(usable_dates) if usable_dates else None
    return {
        "ticker": ticker,
        "as_of": cutoff.isoformat(),
        "price_as_of": price_date.isoformat() if price_date else None,
        "stale": bool(price_date and price_date < cutoff),
        "algorithm_version": ALGORITHM_VERSION,
        "parameter_hash": parameters.fingerprint,
        "parameters": parameters.model_dump(),
        "diagnostics": list(dict.fromkeys(issue["reason"] for issue in quality.issues)),
        "quality": _quality_payload(quality),
        "points": [
            {
                "date": r.date.isoformat(),
                **{
                    field: None
                    if r.date.isoformat() in excluded_dates
                    else _chart_number(getattr(r, field))
                    for field in ("open", "high", "low", "close", "volume")
                },
                "excluded": r.date.isoformat() in excluded_dates,
            }
            for r in rows
        ],
        "patterns": list(_segment_patterns(ticker, quality, parameters, last_date=bars[-1].date))
        if bars
        else [],
    }


def get_results(
    *,
    kind: str | None = None,
    status: str | None = None,
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict:
    config = get_config()
    snapshot = repository._read_json_setting(RESULT_KEY)
    rows = snapshot.get("patterns", [])
    needle = search.strip().lower()
    filtered = [
        r
        for r in rows
        if (not kind or r["kind"] == kind)
        and (not status or r["status"] == status)
        and (not needle or needle in (r["ticker"] + " " + r.get("name", "")).lower())
    ]
    return {
        **{k: v for k, v in snapshot.items() if k != "patterns"},
        "available": bool(snapshot),
        "obsolete": bool(
            snapshot
            and (
                snapshot.get("parameter_hash") != config["parameter_hash"]
                or snapshot.get("algorithm_version") != ALGORITHM_VERSION
            )
        ),
        "current_parameter_hash": config["parameter_hash"],
        "total": len(filtered),
        "rows": filtered[offset : offset + limit],
        "offset": offset,
        "limit": limit,
    }


def _scan_stocks():
    """Load identifiers and split facts, without loading every company profile."""
    try:
        with SessionLocal() as db:
            return list(
                db.execute(
                    select(
                        Instrument.ticker,
                        Instrument.name,
                        Instrument.yahoo_symbol,
                        Instrument.metadata_json["stock_splits"],
                    )
                    .where(Instrument.asset_class == "stock", ~Instrument.ticker.startswith("^"))
                    .order_by(Instrument.ticker)
                )
            )
    except SQLAlchemyError as exc:
        raise repository.SettingsRepositoryUnavailable(str(exc)) from exc


def _retry_due(attempt, now):
    try:
        return datetime.fromisoformat(attempt["next_retry_at"]) <= now
    except (KeyError, TypeError, ValueError):
        return True


def _repair_candidates(stocks, cutoffs, *, progress, cancelled, limit, seconds):
    """Bounded maintenance phase; ordinary chart reads never perform network I/O."""
    state = repository._read_json_setting(REPAIR_KEY)
    candidates = []
    priorities = {
        "invalid_ohlc": 0,
        "invalid_volume": 0,
        "duplicate_date": 1,
        "gap": 2,
        "insufficient_history": 3,
        "extreme_jump": 4,
        "missing_history": 5,
    }
    now = datetime.now(UTC)
    summary = {
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "deferred": 0,
        "refreshed": 0,
        "cooldown": 0,
        "rate_limited": False,
    }
    for start in range(0, len(stocks), 25):
        if cancelled:
            cancelled()
        chunk = stocks[start : start + 25]
        data = list_price_bars_for_tickers(
            [s[0] for s in chunk], start_date=date.today() - timedelta(days=850)
        )
        for ticker, name, symbol, events in chunk:
            bars = [_bar(r) for r in data.get(ticker, []) if r.date <= cutoffs[ticker]]
            quality = prepare_segments(bars)
            if not quality.issues:
                continue
            if not _retry_due(state.get(ticker, {}), now):
                summary["deferred"] += 1
                summary["cooldown"] += 1
                continue
            attempt = state.get(ticker, {})
            candidates.append(
                (
                    bool(attempt),
                    attempt.get("checked_at", ""),
                    min(priorities.get(i["code"], 9) for i in quality.issues),
                    ticker,
                    symbol,
                )
            )
        if progress:
            progress(min(start + len(chunk), len(stocks)), len(stocks), "quality")
    candidates.sort()
    deadline = monotonic() + max(0, seconds)
    # Untried symbols first, then oldest attempts: repeated daily scans must not
    # spend their entire budget on the same alphabetically first failures.
    for index, (_, _, _, ticker, symbol) in enumerate(candidates):
        if cancelled:
            cancelled()
        if summary["attempted"] >= limit or monotonic() >= deadline or summary["rate_limited"]:
            summary["deferred"] += len(candidates) - index
            break
        checked = datetime.now(UTC)
        # Persist before fetching: cancellation/restart must not repeat an attempt immediately.
        state[ticker] = {
            "checked_at": checked.isoformat(),
            "next_retry_at": (checked + timedelta(days=1)).isoformat(),
            "reason_code": "attempt_started",
        }
        repository._write_json_setting(
            REPAIR_KEY, state, description="Chartanalyse: begrenzte Kursreparaturversuche"
        )
        summary["attempted"] += 1
        result = repair_chart_history(
            ticker,
            symbol,
            start_date=cutoffs[ticker] - timedelta(days=850),
            end_date=cutoffs[ticker],
        )
        if cancelled:
            cancelled()
        refreshed = result.get("records_written", 0) > 0
        remaining = None
        if refreshed:
            summary["refreshed"] += 1
            rows = list_price_bars(ticker, start_date=cutoffs[ticker] - timedelta(days=850))
            remaining = prepare_segments([_bar(r) for r in rows if r.date <= cutoffs[ticker]])
        resolved = remaining is not None and not remaining.issues
        summary["succeeded" if resolved else "failed"] += 1
        summary["rate_limited"] = result.get("reason_code") == "rate_limited"
        state[ticker].update(
            next_retry_at=(checked + timedelta(days=7 if refreshed else 1)).isoformat(),
            reason_code="repaired" if resolved else result.get("reason_code", "provider_error"),
            records_written=result.get("records_written", 0),
            verified_jump_dates=result.get("extreme_jump_dates", []) if refreshed else [],
            split_events=result.get("split_events", {}),
        )
        repository._write_json_setting(
            REPAIR_KEY, state, description="Chartanalyse: begrenzte Kursreparaturversuche"
        )
        if progress:
            progress(summary["attempted"], min(len(candidates), limit), "repair")
    return summary, state


def scan_universe(
    *, progress=None, cancelled=None, repair_prices=False, repair_limit=100, repair_seconds=300
) -> dict:
    config = get_config()
    parameters = PatternParameters.model_validate(config["parameters"])
    stocks = _scan_stocks()
    cutoffs = {stock[0]: completed_ticker_market_session(stock[0]).date for stock in stocks}
    repair_summary = {"attempted": 0, "succeeded": 0, "failed": 0, "deferred": 0, "refreshed": 0}
    repair_state = repository._read_json_setting(REPAIR_KEY)
    if repair_prices:
        repair_summary, repair_state = _repair_candidates(
            stocks,
            cutoffs,
            progress=progress,
            cancelled=cancelled,
            limit=max(0, min(int(repair_limit), 2500)),
            seconds=max(0, min(float(repair_seconds), 1800)),
        )
    patterns, skipped = [], []
    quality_issues, partial_count, quality_counts = [], 0, Counter()
    as_of_dates = []
    for start in range(0, len(stocks), 25):
        if cancelled:
            cancelled()
        chunk = stocks[start : start + 25]
        # A single bounded query per batch, instead of one request per stock.
        data = list_price_bars_for_tickers(
            [s[0] for s in chunk], start_date=date.today() - timedelta(days=850)
        )
        for ticker, name, symbol, events in chunk:
            cutoff = cutoffs[ticker]
            bars = [_bar(row) for row in data.get(ticker, []) if row.date <= cutoff]
            quality = prepare_segments(bars)
            _split_issues(quality.issues, events, cutoff=cutoff, repair=repair_state.get(ticker))
            grouped = {}
            for issue in quality.issues:
                grouped.setdefault(issue["code"], []).append(issue)
            for code, issues in grouped.items():
                quality_counts[code] += 1
                quality_issues.append(
                    {
                        "ticker": ticker,
                        **issues[0],
                        "issue_count": len(issues),
                        "dates": [i["date"] for i in issues[:5]],
                        "partial": quality.partial,
                    }
                )
            if not quality.analysed:
                reason = next(
                    (i for i in quality.issues if i["code"] != "insufficient_history"),
                    quality.issues[0],
                )
                skipped.append(
                    {"ticker": ticker, "reason": reason["reason"], "code": reason["code"]}
                )
                continue
            partial_count += int(quality.partial)
            as_of_dates.append(bars[-1].date.isoformat())
            for pattern in _segment_patterns(ticker, quality, parameters, last_date=bars[-1].date):
                patterns.append(
                    {
                        **pattern,
                        "name": name,
                        "price_as_of": pattern["segment_end"],
                        "stale": pattern["segment_end"] < cutoff.isoformat(),
                    }
                )
        if progress:
            progress(min(start + len(chunk), len(stocks)), len(stocks))
    if cancelled:
        cancelled()
    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "algorithm_version": ALGORITHM_VERSION,
        "parameter_hash": parameters.fingerprint,
        "parameters": parameters.model_dump(),
        "scanned_count": len(stocks),
        "analysed_count": len(stocks) - len(skipped),
        "skipped_count": len(skipped),
        "partial_count": partial_count,
        "quality_counts": dict(quality_counts),
        "quality_issues": quality_issues,
        "repair_summary": repair_summary,
        "skipped": skipped,
        "oldest_price_date": min(as_of_dates) if as_of_dates else None,
        "newest_price_date": max(as_of_dates) if as_of_dates else None,
        "patterns": sorted(patterns, key=lambda r: r["detected_on"], reverse=True),
    }
    # Publish once after success; cancellation/failure retains the previous scan.
    repository._write_json_setting(
        RESULT_KEY, snapshot, description="Chartanalyse: abgeschlossener Universumscan"
    )
    return {
        "ok": True,
        "records_seen": len(stocks),
        "records_written": len(patterns),
        "skipped_count": len(skipped),
        "parameter_hash": parameters.fingerprint,
        "analysed_count": len(stocks) - len(skipped),
        "partial_count": partial_count,
        "repair_summary": repair_summary,
    }
