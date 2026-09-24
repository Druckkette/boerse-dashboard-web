from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.db.models import EarningsEvent
from app.db.session import SessionLocal
from app.repositories import fundamentals, portfolio, universes
from app.repositories.refresh_work import WorkRequest, enqueue
from app.domain.stocks.instrument_type import classify_instrument, inapplicable_reason
from app.data_sources.provider_usage import record_provider_event


def plan_report_work(*, include_sec13f: bool = True, include_fundamentals: bool = True) -> int:
    now = datetime.now(UTC)
    tickers = list(dict.fromkeys(universes.list_universe_tickers(limit=None)))
    tracked = {row.ticker for row in portfolio.list_open_positions()}
    tickers = sorted(set(tickers) | tracked)
    snapshots = fundamentals.get_latest_fundamentals_for_tickers(tickers)
    profiles = fundamentals.get_instrument_profiles_for_tickers(tickers)
    with SessionLocal() as db:
        events = db.scalars(select(EarningsEvent).where(
            EarningsEvent.event_date >= date.today() - timedelta(days=14),
            EarningsEvent.event_date <= date.today(),
        ).order_by(EarningsEvent.event_date)).all()
    by_ticker = {row.ticker: row for row in events}
    requests = []
    skipped_for_type = 0
    for ticker in tickers:
        if not include_fundamentals:
            break
        previous = snapshots.get(ticker)
        profile = profiles.get(ticker) or {}
        profile_meta = profile.get("metadata") or {}
        kind = classify_instrument(ticker=ticker, name=profile.get("name", ""), asset_class=profile.get("asset_class", ""),
                                   etf=str((profile_meta.get("nasdaq_listing") or {}).get("etf", "")),
                                   nextshares=str((profile_meta.get("nasdaq_listing") or {}).get("nextshares", "")),
                                   sec_forms=profile_meta.get("sec_forms"),
                                   previous_type=profile_meta.get("instrument_type", ""))
        if inapplicable_reason(kind):
            skipped_for_type += 1
            continue
        complete = previous is not None and not fundamentals._missing_required_history_keys(previous.metadata_json)
        due = datetime.combine(previous.as_of, datetime.min.time(), UTC) + timedelta(days=14) if complete else now
        event = by_ticker.get(ticker)
        payload = {}
        revision = "baseline"
        if event:
            revision = f"revision:{event.event_date.isoformat()}:earnings:{event.fiscal_date_ending or ''}"
            due = now
            payload = {"event_date": event.event_date.isoformat(),
                       "expected_period": event.fiscal_date_ending.isoformat() if event.fiscal_date_ending else None,
                       "baseline_period": previous.fiscal_period if previous else ""}
        requests.append(WorkRequest(ticker, "statements", revision, due, 10 if ticker in tracked else 30 if event else 60, payload))
        beta_due = now if previous is None or previous.beta is None else datetime.combine(previous.as_of, datetime.min.time(), UTC) + timedelta(days=7)
        requests.append(WorkRequest(ticker, "beta", "baseline", beta_due, 40 if ticker in tracked else 80))
    if include_sec13f:
        requests.append(WorkRequest("*", "sec13f", "baseline", now, 90))
    if include_fundamentals:
        requests.append(WorkRequest("*", "filings", "baseline", now, 5))
    if skipped_for_type:
        for metric in ("instrument_type_skipped", "avoided_sec_requests", "avoided_yahoo_fallbacks",
                       "avoided_fmp_fallbacks"):
            record_provider_event(metric, skipped_for_type)
    return enqueue(requests)
