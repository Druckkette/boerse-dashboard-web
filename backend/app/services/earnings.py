from __future__ import annotations

from datetime import date, timedelta

from app.data_sources.earnings_client import fetch_fmp_earnings_calendar
from app.repositories import earnings as earnings_repository
from app.repositories.earnings import EarningsEventWrite


def refresh_earnings_calendar(
    *,
    api_key: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    today = date.today()
    effective_start = start_date or today - timedelta(days=5)
    effective_end = end_date or today + timedelta(days=120)
    entries = fetch_fmp_earnings_calendar(
        api_key=api_key,
        start_date=effective_start,
        end_date=effective_end,
    )
    if not entries:
        raise RuntimeError("FMP Earnings-Kalender enthält für das angefragte Fenster keine Termine.")
    writes = [
        EarningsEventWrite(
            ticker=item.ticker,
            event_date=item.event_date,
            fiscal_date_ending=item.fiscal_date_ending,
            time=item.time,
            eps_estimated=item.eps_estimated,
            eps_actual=item.eps_actual,
            revenue_estimated=item.revenue_estimated,
            revenue_actual=item.revenue_actual,
            raw_json=item.raw,
        )
        for item in entries
    ]
    written = earnings_repository.replace_earnings_window(
        writes,
        start_date=effective_start,
        end_date=effective_end,
    )
    return {
        "ok": True,
        "job_type": "refresh_earnings_calendar",
        "source": "fmp",
        "from": effective_start.isoformat(),
        "to": effective_end.isoformat(),
        "records_seen": len(entries),
        "records_written": written,
    }


def earnings_priority_tickers(*, today: date | None = None) -> list[str]:
    current = today or date.today()
    try:
        return earnings_repository.priority_tickers_for_fundamentals(
            start_date=current - timedelta(days=3),
            end_date=current + timedelta(days=1),
            limit=2000,
        )
    except earnings_repository.EarningsRepositoryUnavailable:
        return []
