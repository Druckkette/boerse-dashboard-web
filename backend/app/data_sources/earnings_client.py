from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests

from app.data_sources.fmp_client import FMP_EARNINGS_CALENDAR_URL, compact_fmp_response_body


NASDAQ_EARNINGS_CALENDAR_URL = "https://api.nasdaq.com/api/calendar/earnings"
NASDAQ_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/126 Safari/537.36"
    ),
}


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
    source: str
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
        source="fmp",
        raw=row,
    )


def fetch_nasdaq_earnings_calendar(
    *,
    start_date: date,
    end_date: date,
    timeout: int = 20,
    session: requests.Session | None = None,
) -> list[EarningsCalendarEntry]:
    """Fetch the public Nasdaq calendar one weekday at a time.

    Nasdaq does not expose a date-range parameter. Callers should therefore pass
    a deliberately short rolling window; weekends are skipped locally.
    """
    if end_date < start_date:
        raise ValueError("Das Ende des Earnings-Fensters liegt vor dem Start.")

    client = session or requests.Session()
    client.headers.update(NASDAQ_REQUEST_HEADERS)
    entries: list[EarningsCalendarEntry] = []
    failures: list[str] = []
    successful_dates = 0
    current = start_date
    while current <= end_date:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        try:
            response = client.get(
                NASDAQ_EARNINGS_CALENDAR_URL,
                params={"date": current.isoformat()},
                timeout=timeout,
            )
        except requests.exceptions.Timeout:
            failures.append(f"{current.isoformat()}: Timeout")
            current += timedelta(days=1)
            continue
        except requests.exceptions.ConnectionError as exc:
            failures.append(f"{current.isoformat()}: Verbindung fehlgeschlagen ({exc})")
            current += timedelta(days=1)
            continue
        if response.status_code != 200:
            body = str(getattr(response, "text", "") or "").strip()[:300]
            failures.append(
                f"{current.isoformat()}: HTTP {response.status_code}"
                + (f" ({body})" if body else "")
            )
            current += timedelta(days=1)
            continue
        try:
            payload = response.json()
        except ValueError:
            failures.append(f"{current.isoformat()}: ungültiges JSON")
            current += timedelta(days=1)
            continue
        successful_dates += 1
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("rows") if isinstance(data, dict) else None
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            parsed = _parse_nasdaq_entry(row, event_date=current)
            if parsed is not None:
                entries.append(parsed)
        current += timedelta(days=1)

    if successful_dates == 0:
        detail = "; ".join(failures[:3])
        raise RuntimeError(
            "Nasdaq Earnings-Kalender konnte für keinen Handelstag geladen werden"
            + (f": {detail}" if detail else ".")
        )
    return entries


def _parse_nasdaq_entry(
    row: dict[str, Any],
    *,
    event_date: date,
) -> EarningsCalendarEntry | None:
    ticker = str(row.get("symbol") or "").strip().upper()
    if not ticker:
        return None
    return EarningsCalendarEntry(
        ticker=ticker,
        event_date=event_date,
        fiscal_date_ending=_parse_nasdaq_fiscal_period(row.get("fiscalQuarterEnding")),
        time=str(row.get("time") or "").strip().lower(),
        eps_estimated=_float_or_none(row.get("epsForecast")),
        eps_actual=None,
        revenue_estimated=None,
        revenue_actual=None,
        source="nasdaq",
        raw=row,
    )


def _parse_nasdaq_fiscal_period(value: object) -> date | None:
    text = str(value or "").strip()
    if "/" not in text:
        return None
    month_text, year_text = text.split("/", maxsplit=1)
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = months.get(month_text.strip().lower()[:3])
    try:
        year = int(year_text)
    except ValueError:
        return None
    if month is None:
        return None
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return next_month - timedelta(days=1)


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None


def _float_or_none(value: object) -> float | None:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() in {"n/a", "na", "none", "-"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    clean = text.strip("()").replace("$", "").replace(",", "").replace("%", "")
    try:
        parsed = float(clean)
        return -parsed if negative else parsed
    except (TypeError, ValueError):
        return None
