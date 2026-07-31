from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

from app.data_sources.fmp_client import FMP_EARNINGS_CALENDAR_URL, compact_fmp_response_body


@dataclass(frozen=True)
class EarningsCalendarEntry:
    ticker: str
    event_date: date
    fiscal_date_ending: date | None
    time: str
    eps_estimated: float | None
    eps_actual: float | None
    revenue_estimated: float | None
    revenue_actual: float | None
    raw: dict[str, Any]


def fetch_fmp_earnings_calendar(
    *,
    api_key: str,
    start_date: date,
    end_date: date,
    timeout: int = 30,
) -> list[EarningsCalendarEntry]:
    if not api_key.strip():
        raise RuntimeError("FMP_API_KEY ist für den Earnings-Kalender nicht gesetzt.")
    try:
        response = requests.get(
            FMP_EARNINGS_CALENDAR_URL,
            params={
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "apikey": api_key,
            },
            timeout=timeout,
        )
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("FMP Earnings-Kalender: Timeout") from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"FMP Earnings-Kalender: Verbindung fehlgeschlagen: {exc}") from exc
    if response.status_code != 200:
        body = compact_fmp_response_body(response)
        raise RuntimeError(
            f"FMP Earnings-Kalender: HTTP {response.status_code}"
            + (f" ({body})" if body else "")
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("FMP Earnings-Kalender: ungültiges JSON") from exc
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    parsed = [_parse_entry(row) for row in rows if isinstance(row, dict)]
    return [item for item in parsed if item is not None]


def _parse_entry(row: dict[str, Any]) -> EarningsCalendarEntry | None:
    ticker = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
    event_date = _parse_date(row.get("date"))
    if not ticker or event_date is None:
        return None
    return EarningsCalendarEntry(
        ticker=ticker,
        event_date=event_date,
        fiscal_date_ending=_parse_date(row.get("fiscalDateEnding")),
        time=str(row.get("time") or "").strip().lower(),
        eps_estimated=_float_or_none(row.get("epsEstimated")),
        eps_actual=_float_or_none(row.get("epsActual")),
        revenue_estimated=_float_or_none(row.get("revenueEstimated")),
        revenue_actual=_float_or_none(row.get("revenueActual")),
        raw=row,
    )


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
