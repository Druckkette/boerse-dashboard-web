from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import pandas as pd
import requests

from app.data_sources.fmp_client import (
    FMP_BALANCE_SHEET_URL,
    FMP_EARNINGS_URL,
    FMP_INCOME_STATEMENT_GROWTH_URL,
    FMP_INCOME_STATEMENT_URL,
    FMP_PROFILE_URL,
    FMP_RATIOS_TTM_URL,
    compact_fmp_response_body,
)


QuarterlyRaw = dict[str, pd.Series | float]


@dataclass(frozen=True)
class GrowthPoint:
    label: str
    growth_pct: float | None
    flag: str | None
    current: float | None
    previous: float | None


@dataclass(frozen=True)
class FundamentalEnrichment:
    source: str = ""
    fiscal_period: str = ""
    quarterly_eps_growth_pct: float | None = None
    annual_eps_growth_pct: float | None = None
    quarterly_revenue_growth_pct: float | None = None
    annual_revenue_growth_pct: float | None = None
    quarterly_eps_accelerating: bool | None = None
    quarterly_revenue_accelerating: bool | None = None
    trailing_eps: float | None = None
    roe_pct: float | None = None
    profit_margin_pct: float | None = None
    eps_quarter_history: list[dict[str, Any]] = field(default_factory=list)
    annual_eps_history: list[dict[str, Any]] = field(default_factory=list)
    revenue_quarter_history: list[dict[str, Any]] = field(default_factory=list)
    annual_revenue_history: list[dict[str, Any]] = field(default_factory=list)
    roe_history: list[dict[str, Any]] = field(default_factory=list)
    beta: float | None = None
    next_earnings_date: date | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def fetch_fundamental_enrichment(
    ticker: str,
    *,
    fmp_api_key: str = "",
    sec_user_agent: str = "",
    timeout: int = 15,
) -> FundamentalEnrichment:
    clean = ticker.strip().upper()
    notes: list[str] = []
    raw: QuarterlyRaw | None = None
    fmp_profile: dict[str, Any] = {}
    fmp_next_earnings_date: date | None = None

    if fmp_api_key:
        fmp_raw, fmp_note = fetch_quarterly_fmp(clean, fmp_api_key, timeout=timeout)
        if fmp_note:
            notes.append(fmp_note)
        raw = merge_quarterly_raw(fmp_raw, raw)
        fmp_profile, fmp_profile_note = fetch_fmp_profile(clean, fmp_api_key, timeout=timeout)
        if fmp_profile_note:
            notes.append(fmp_profile_note)
        fmp_next_earnings_date, fmp_earnings_note = fetch_fmp_next_earnings_date(clean, fmp_api_key, timeout=timeout)
        if fmp_earnings_note:
            notes.append(fmp_earnings_note)
    else:
        notes.append("FMP: kein API-Key")

    if sec_user_agent:
        sec_raw, sec_note = fetch_quarterly_sec_companyfacts(clean, sec_user_agent, timeout=timeout)
        if sec_note:
            notes.append(sec_note)
        raw = merge_quarterly_raw(raw, sec_raw)
    else:
        notes.append("SEC: kein User-Agent")

    if _needs_yfinance_statement_history(raw):
        yf_raw, yf_note = fetch_yfinance_statement_history(clean)
        if yf_note:
            notes.append(yf_note)
        raw = merge_quarterly_raw(raw, yf_raw)

    enrichment = compute_fundamental_enrichment(clean, raw, notes=notes)
    metadata = {
        **enrichment.metadata,
        "fmp_profile": _compact_metadata(fmp_profile),
    }
    return replace(
        enrichment,
        beta=_float_or_none(fmp_profile.get("beta")),
        next_earnings_date=fmp_next_earnings_date,
        metadata=metadata,
    )


def fetch_quarterly_fmp(
    ticker: str,
    api_key: str,
    *,
    timeout: int = 15,
) -> tuple[QuarterlyRaw | None, str]:
    if not api_key:
        return None, "FMP: kein API-Key"

    attempts = [
        (
            "FMP stable quartalsweise",
            FMP_INCOME_STATEMENT_URL,
            {"symbol": ticker.upper(), "period": "quarter", "limit": 40, "apikey": api_key},
            _raw_from_fmp_income_statement,
        ),
        (
            "FMP stable jaehrlich",
            FMP_INCOME_STATEMENT_URL,
            {"symbol": ticker.upper(), "period": "annual", "limit": 8, "apikey": api_key},
            _raw_from_fmp_annual_income_statement,
        ),
        (
            "FMP stable Bilanz jaehrlich",
            FMP_BALANCE_SHEET_URL,
            {"symbol": ticker.upper(), "period": "annual", "limit": 8, "apikey": api_key},
            _raw_from_fmp_annual_balance_sheet,
        ),
        (
            "FMP stable Wachstum quartalsweise",
            FMP_INCOME_STATEMENT_GROWTH_URL,
            {"symbol": ticker.upper(), "period": "quarter", "limit": 40, "apikey": api_key},
            _raw_from_fmp_quarterly_growth,
        ),
        (
            "FMP stable Wachstum jaehrlich",
            FMP_INCOME_STATEMENT_GROWTH_URL,
            {"symbol": ticker.upper(), "period": "annual", "limit": 8, "apikey": api_key},
            _raw_from_fmp_annual_growth,
        ),
    ]
    errors: list[str] = []
    raw: QuarterlyRaw = {}
    for label, url, params, parser in attempts:
        try:
            response = requests.get(url, params=params, timeout=timeout)
        except requests.exceptions.Timeout:
            errors.append(f"{label}: Timeout")
            continue
        except requests.exceptions.ConnectionError as exc:
            errors.append(f"{label}: Verbindung {str(exc)[:60]}")
            continue

        if response.status_code == 429:
            body = compact_fmp_response_body(response)
            errors.append(f"{label}: Rate Limited" + (f" ({body})" if body else ""))
            continue
        if response.status_code in {401, 403}:
            body = compact_fmp_response_body(response)
            errors.append(f"{label}: Zugriff verweigert" + (f" ({body})" if body else ""))
            continue
        if response.status_code != 200:
            body = compact_fmp_response_body(response)
            errors.append(f"{label}: HTTP {response.status_code}" + (f" ({body})" if body else ""))
            continue

        try:
            payload = response.json()
        except ValueError:
            errors.append(f"{label}: Ungueltiges JSON")
            continue
        if isinstance(payload, dict) and payload.get("Error Message"):
            errors.append(f"{label}: {str(payload['Error Message'])[:120]}")
            continue
        rows = _payload_rows(payload)
        if not rows:
            errors.append(f"{label}: Leere Antwort")
            continue

        parsed = parser(rows)
        raw = merge_quarterly_raw(raw, parsed) or raw
        if not any(isinstance(value, pd.Series) and not value.empty for value in parsed.values()):
            errors.append(f"{label}: Keine verwertbaren Daten")

    if raw and any(isinstance(value, pd.Series) and not value.empty for value in raw.values()):
        _merge_fmp_ttm_ratios(raw, ticker, api_key, timeout=timeout)
        return raw, "FMP stable"

    return None, " | ".join(errors) if errors else "FMP: keine Quartalsdaten"


def fetch_fmp_profile(
    ticker: str,
    api_key: str,
    *,
    timeout: int = 15,
) -> tuple[dict[str, Any], str]:
    if not api_key:
        return {}, "FMP Profile: kein API-Key"
    try:
        response = requests.get(
            FMP_PROFILE_URL,
            params={"symbol": ticker.upper(), "apikey": api_key},
            timeout=min(timeout, 10),
        )
    except requests.exceptions.Timeout:
        return {}, "FMP Profile: Timeout"
    except requests.exceptions.ConnectionError as exc:
        return {}, f"FMP Profile: Verbindung {str(exc)[:60]}"
    if response.status_code != 200:
        body = compact_fmp_response_body(response)
        return {}, f"FMP Profile: HTTP {response.status_code}" + (f" ({body})" if body else "")
    try:
        payload = response.json()
    except ValueError:
        return {}, "FMP Profile: Ungueltiges JSON"
    item = payload[0] if isinstance(payload, list) and payload else payload if isinstance(payload, dict) else {}
    if not isinstance(item, dict) or not item:
        return {}, "FMP Profile: Leere Antwort"
    return item, "FMP Profile"


def fetch_fmp_next_earnings_date(
    ticker: str,
    api_key: str,
    *,
    timeout: int = 15,
) -> tuple[date | None, str]:
    if not api_key:
        return None, "FMP Earnings: kein API-Key"
    try:
        response = requests.get(
            FMP_EARNINGS_URL,
            params={"symbol": ticker.upper(), "apikey": api_key},
            timeout=min(timeout, 10),
        )
    except requests.exceptions.Timeout:
        return None, "FMP Earnings: Timeout"
    except requests.exceptions.ConnectionError as exc:
        return None, f"FMP Earnings: Verbindung {str(exc)[:60]}"
    if response.status_code != 200:
        body = compact_fmp_response_body(response)
        return None, f"FMP Earnings: HTTP {response.status_code}" + (f" ({body})" if body else "")
    try:
        payload = response.json()
    except ValueError:
        return None, "FMP Earnings: Ungueltiges JSON"
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    today = date.today()
    dates = [
        parsed
        for row in rows
        if isinstance(row, dict)
        for parsed in [_parse_date(row.get("date") or row.get("epsDate") or row.get("fiscalDateEnding"))]
        if parsed is not None and parsed >= today
    ]
    if not dates:
        return None, "FMP Earnings: kein kommender Termin"
    return min(dates), "FMP Earnings"


def fetch_quarterly_sec_companyfacts(
    ticker: str,
    user_agent: str,
    *,
    timeout: int = 15,
) -> tuple[QuarterlyRaw | None, str]:
    clean = ticker.upper().strip()
    if not clean:
        return None, "SEC: kein Ticker"
    if not user_agent.strip():
        return None, "SEC: kein User-Agent"

    headers = {"User-Agent": user_agent.strip()}
    try:
        cik = _sec_cik_map(user_agent.strip(), timeout).get(clean, "")
        if not cik:
            return None, "SEC: Ticker nicht im CIK-Universum"

        facts_response = requests.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            headers=headers,
            timeout=timeout,
        )
        if facts_response.status_code != 200:
            return None, f"SEC Facts HTTP {facts_response.status_code}"
        facts_payload = facts_response.json()
    except requests.exceptions.Timeout:
        return None, "SEC: Timeout"
    except requests.exceptions.ConnectionError as exc:
        return None, f"SEC: Verbindung {str(exc)[:60]}"
    except ValueError:
        return None, "SEC: Ungueltiges JSON"
    except RuntimeError as exc:
        return None, f"SEC: {exc}"

    facts = (((facts_payload or {}).get("facts") or {}).get("us-gaap") or {})
    raw: QuarterlyRaw = {}
    eps = _extract_sec_quarterly_series(
        facts,
        concepts=[
            "EarningsPerShareDiluted",
            "EarningsPerShareBasicAndDiluted",
            "IncomeLossFromContinuingOperationsPerDilutedShare",
        ],
        unit_keys=["USD/shares"],
        duration_min=75,
        duration_max=110,
    )
    revenue = _extract_sec_quarterly_series(
        facts,
        concepts=[
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
        ],
        unit_keys=["USD"],
        duration_min=75,
        duration_max=110,
    )
    net_income = _extract_sec_quarterly_series(
        facts,
        concepts=["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
        unit_keys=["USD"],
        duration_min=75,
        duration_max=110,
    )
    equity = _extract_sec_point_series(
        facts,
        concepts=[
            "StockholdersEquity",
            "StockholdersEquityAttributableToParent",
            "Equity",
            "LiabilitiesAndStockholdersEquity",
        ],
        unit_keys=["USD"],
    )
    if eps is not None:
        raw["DilutedEPS"] = eps
    if revenue is not None:
        raw["TotalRevenue"] = revenue
    if net_income is not None:
        raw["NetIncome"] = net_income
    if equity is not None:
        raw["StockholdersEquity"] = equity
    if not raw:
        return None, "SEC: keine Quartalsdaten"
    return raw, "SEC ergaenzt"


def fetch_yfinance_statement_history(ticker: str) -> tuple[QuarterlyRaw | None, str]:
    clean = ticker.upper().strip()
    if not clean:
        return None, "yfinance Statements: kein Ticker"
    try:
        import yfinance as yf

        yf_ticker = yf.Ticker(clean)
        raw = _raw_from_yfinance_statements(
            quarterly_income_stmt=_safe_yfinance_frame(yf_ticker, "quarterly_income_stmt", "quarterly_financials"),
            annual_income_stmt=_safe_yfinance_frame(yf_ticker, "income_stmt", "financials"),
            annual_balance_sheet=_safe_yfinance_frame(yf_ticker, "balance_sheet"),
        )
    except Exception as exc:
        return None, f"yfinance Statements: {type(exc).__name__}: {str(exc)[:80]}"
    if not raw:
        return None, "yfinance Statements: keine Historie"
    return raw, "yfinance statements"


@lru_cache(maxsize=4)
def _sec_cik_map(user_agent: str, timeout: int) -> dict[str, str]:
    headers = {"User-Agent": user_agent}
    response = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"SEC CIK HTTP {response.status_code}")
    payload = response.json()
    rows = payload.values() if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        try:
            out[ticker] = str(int(row.get("cik_str"))).zfill(10)
        except (TypeError, ValueError):
            continue
    return out


def merge_quarterly_raw(primary: QuarterlyRaw | None, secondary: QuarterlyRaw | None) -> QuarterlyRaw | None:
    if primary is None:
        return secondary
    if secondary is None:
        return primary
    merged: QuarterlyRaw = dict(primary)
    for key, secondary_value in secondary.items():
        primary_value = merged.get(key)
        if not isinstance(primary_value, pd.Series) or not isinstance(secondary_value, pd.Series):
            merged.setdefault(key, secondary_value)
            continue
        try:
            merged[key] = pd.concat([primary_value, secondary_value[~secondary_value.index.isin(primary_value.index)]]).sort_index(
                ascending=False
            )
        except Exception:
            merged[key] = primary_value
    return merged


def compute_fundamental_enrichment(
    ticker: str,
    raw: QuarterlyRaw | None,
    *,
    notes: list[str] | None = None,
) -> FundamentalEnrichment:
    notes = notes or []
    if not raw:
        return FundamentalEnrichment(metadata={"notes": notes, "ticker": ticker.upper()})

    eps_growth = quarterly_yoy_growth(raw, "eps")
    annual_eps_growth = annual_yoy_growth(raw, "eps")
    revenue_growth = quarterly_yoy_growth(raw, "revenue")
    annual_revenue_growth = annual_yoy_growth(raw, "revenue")
    roe_history = annual_roe_history(raw)
    fiscal_period = _latest_period_label(raw)
    source_parts = []
    if any("FMP" in note for note in notes):
        source_parts.append("fmp")
    if any("SEC" in note for note in notes):
        source_parts.append("sec")
    source = "+".join(source_parts) or "fundamental-enrichment"
    return FundamentalEnrichment(
        source=source,
        fiscal_period=fiscal_period,
        quarterly_eps_growth_pct=_latest_numeric_growth(eps_growth),
        annual_eps_growth_pct=_latest_numeric_growth(annual_eps_growth),
        quarterly_revenue_growth_pct=_latest_numeric_growth(revenue_growth),
        annual_revenue_growth_pct=_latest_numeric_growth(annual_revenue_growth),
        quarterly_eps_accelerating=_is_accelerating(eps_growth),
        quarterly_revenue_accelerating=_is_accelerating(revenue_growth),
        trailing_eps=_trailing_sum(raw.get("DilutedEPS"), periods=4),
        roe_pct=_roe_pct(raw),
        profit_margin_pct=_profit_margin_pct(raw),
        eps_quarter_history=[_growth_point_payload(point, prefix="eps") for point in eps_growth[:3]],
        annual_eps_history=[_annual_growth_point_payload(point, prefix="eps") for point in annual_eps_growth[:3]],
        revenue_quarter_history=[_growth_point_payload(point, prefix="revenue") for point in revenue_growth[:3]],
        annual_revenue_history=[
            _annual_growth_point_payload(point, prefix="revenue") for point in annual_revenue_growth[:3]
        ],
        roe_history=[_roe_point_payload(point) for point in roe_history[:5]],
        metadata={
            "ticker": ticker.upper(),
            "notes": notes,
            # Stable schema for persisted snapshots:
            # eps_quarter_history/revenue_quarter_history are ordered latest-first and each item contains
            # fiscal_period, current quarter value, same-quarter-prior-year value and computed YoY growth.
            # annual_*_history is ordered latest full fiscal year first and contains annual sums.
            # roe_history is ordered latest full fiscal year first and contains annual ROE percentages.
            "eps_quarter_history": [_growth_point_payload(point, prefix="eps") for point in eps_growth[:3]],
            "annual_eps_history": [_annual_growth_point_payload(point, prefix="eps") for point in annual_eps_growth[:3]],
            "revenue_quarter_history": [_growth_point_payload(point, prefix="revenue") for point in revenue_growth[:3]],
            "annual_revenue_history": [
                _annual_growth_point_payload(point, prefix="revenue") for point in annual_revenue_growth[:3]
            ],
            "roe_history": [_roe_point_payload(point) for point in roe_history[:5]],
            "eps_growth": [_growth_point_payload(point, prefix="eps") for point in eps_growth],
            "annual_eps_growth": [_annual_growth_point_payload(point, prefix="eps") for point in annual_eps_growth],
            "revenue_growth": [_growth_point_payload(point, prefix="revenue") for point in revenue_growth],
            "annual_revenue_growth": [
                _annual_growth_point_payload(point, prefix="revenue") for point in annual_revenue_growth
            ],
            "annual_roe": [_roe_point_payload(point) for point in roe_history],
            "series_lengths": {
                key: int(len(value)) for key, value in raw.items() if isinstance(value, pd.Series)
            },
        },
    )


def quarterly_yoy_growth(raw: QuarterlyRaw, field: str) -> list[GrowthPoint]:
    key = {"eps": "DilutedEPS", "revenue": "TotalRevenue"}.get(field)
    series = raw.get(key or "")
    growth_series = raw.get({"eps": "QuarterlyDilutedEPSGrowthPct", "revenue": "QuarterlyRevenueGrowthPct"}.get(field, ""))
    growth_points = _growth_points_from_growth_series(growth_series, annual=False)
    if not isinstance(series, pd.Series):
        return growth_points[:3]
    values = pd.to_numeric(series, errors="coerce").dropna().sort_index(ascending=False)
    if len(values) < 2:
        return growth_points[:3]

    buckets: dict[tuple[int, int], float] = {}
    for index, value in values.items():
        ts = pd.to_datetime(index, errors="coerce")
        if pd.isna(ts):
            continue
        yq = (int(ts.year), int(ts.quarter))
        buckets.setdefault(yq, float(value))
    if not buckets:
        return []

    points: list[GrowthPoint] = []
    for year, quarter in sorted(buckets.keys(), reverse=True)[:3]:
        current = buckets[(year, quarter)]
        previous = buckets.get((year - 1, quarter))
        label = f"{year} Q{quarter}"
        points.append(_growth_point(label, current, previous))
    return _prefer_growth_history(points, growth_points)


def annual_yoy_growth(raw: QuarterlyRaw, field: str) -> list[GrowthPoint]:
    annual_key = {"eps": "AnnualDilutedEPS", "revenue": "AnnualTotalRevenue"}.get(field)
    annual_series = raw.get(annual_key or "")
    direct_growth_series = raw.get({"eps": "AnnualDilutedEPSGrowthPct", "revenue": "AnnualRevenueGrowthPct"}.get(field, ""))
    direct_growth_points = _growth_points_from_growth_series(direct_growth_series, annual=True)
    annual_points: list[GrowthPoint] = []
    if isinstance(annual_series, pd.Series):
        annual_points = _annual_yoy_from_series(annual_series)
    annual_points = _prefer_growth_history(annual_points, direct_growth_points)

    key = {"eps": "DilutedEPS", "revenue": "TotalRevenue"}.get(field)
    series = raw.get(key or "")
    if not isinstance(series, pd.Series):
        return annual_points[:3]
    values = pd.to_numeric(series, errors="coerce").dropna().sort_index(ascending=False)
    if len(values) < 8:
        return annual_points[:3]

    buckets: dict[int, dict[int, float]] = {}
    for index, value in values.items():
        ts = pd.to_datetime(index, errors="coerce")
        if pd.isna(ts):
            continue
        buckets.setdefault(int(ts.year), {}).setdefault(int(ts.quarter), float(value))

    annual_totals = {
        year: round(sum(quarters.values()), 4)
        for year, quarters in buckets.items()
        if len(quarters) >= 4
    }
    if not annual_totals:
        return annual_points[:3]

    quarterly_derived_points: list[GrowthPoint] = []
    for year in sorted(annual_totals.keys(), reverse=True)[:3]:
        current = annual_totals[year]
        previous = annual_totals.get(year - 1)
        quarterly_derived_points.append(_growth_point(str(year), current, previous))
    return _prefer_growth_history(annual_points, quarterly_derived_points)


def annual_roe_history(raw: QuarterlyRaw) -> list[GrowthPoint]:
    income_series = raw.get("AnnualNetIncome")
    equity_series = raw.get("AnnualStockholdersEquity")
    if not isinstance(income_series, pd.Series):
        income_series = _annual_total_from_quarterly(raw.get("NetIncome"))
    if not isinstance(equity_series, pd.Series):
        equity_series = raw.get("StockholdersEquity")
    if not isinstance(income_series, pd.Series) or not isinstance(equity_series, pd.Series):
        return []

    income_by_year = _year_value_map(income_series)
    equity_by_year = _year_value_map(equity_series)
    points: list[GrowthPoint] = []
    for year in sorted(income_by_year.keys() & equity_by_year.keys(), reverse=True)[:5]:
        income = income_by_year.get(year)
        equity = equity_by_year.get(year)
        if income is None or equity in (None, 0):
            points.append(GrowthPoint(str(year), None, "missing_equity", income, equity))
            continue
        points.append(GrowthPoint(str(year), round(float(income / equity * 100), 1), None, income, equity))
    return points


def _annual_yoy_from_series(series: pd.Series) -> list[GrowthPoint]:
    values_by_year = _year_value_map(series)
    if not values_by_year:
        return []
    points: list[GrowthPoint] = []
    for year in sorted(values_by_year.keys(), reverse=True)[:3]:
        current = values_by_year[year]
        previous = values_by_year.get(year - 1)
        points.append(_growth_point(str(year), current, previous))
    return points


def _growth_points_from_growth_series(value: Any, *, annual: bool) -> list[GrowthPoint]:
    if not isinstance(value, pd.Series):
        return []
    series = pd.to_numeric(value, errors="coerce").dropna().sort_index(ascending=False)
    points: list[GrowthPoint] = []
    for index, growth in series.items():
        ts = pd.to_datetime(index, errors="coerce")
        if pd.isna(ts):
            label = str(index)
        elif annual:
            label = str(int(ts.year))
        else:
            label = f"{int(ts.year)} Q{int(ts.quarter)}"
        points.append(GrowthPoint(label, _normalize_growth_pct(float(growth)), None, None, None))
    return points[:3]


def _prefer_growth_history(primary: list[GrowthPoint], fallback: list[GrowthPoint]) -> list[GrowthPoint]:
    if not primary:
        return fallback[:3]
    if not fallback:
        return primary[:3]
    primary_quality = _growth_history_quality(primary)
    fallback_quality = _growth_history_quality(fallback)
    if fallback_quality > primary_quality:
        return fallback[:3]
    return primary[:3]


def _growth_history_quality(points: list[GrowthPoint]) -> tuple[int, int, int]:
    latest_three = points[:3]
    comparable = sum(1 for point in latest_three if point.growth_pct is not None)
    valued = sum(1 for point in latest_three if point.current is not None and point.previous is not None)
    return comparable, valued, len(latest_three)


def _year_value_map(series: pd.Series) -> dict[int, float]:
    values = pd.to_numeric(series, errors="coerce").dropna().sort_index(ascending=False)
    out: dict[int, float] = {}
    for index, value in values.items():
        ts = pd.to_datetime(index, errors="coerce")
        if pd.isna(ts):
            continue
        out.setdefault(int(ts.year), float(value))
    return out


def _annual_total_from_quarterly(value: Any) -> pd.Series | None:
    if not isinstance(value, pd.Series):
        return None
    values = pd.to_numeric(value, errors="coerce").dropna().sort_index(ascending=False)
    buckets: dict[int, dict[int, float]] = {}
    for index, number in values.items():
        ts = pd.to_datetime(index, errors="coerce")
        if pd.isna(ts):
            continue
        buckets.setdefault(int(ts.year), {}).setdefault(int(ts.quarter), float(number))
    annual_totals = {
        pd.Timestamp(year=year, month=12, day=31): round(sum(quarters.values()), 4)
        for year, quarters in buckets.items()
        if len(quarters) >= 4
    }
    if not annual_totals:
        return None
    return pd.Series(annual_totals).sort_index(ascending=False)


def _raw_from_fmp_income_statement(rows: list[dict[str, Any]]) -> QuarterlyRaw:
    eps: dict[pd.Timestamp, float] = {}
    revenue: dict[pd.Timestamp, float] = {}
    net_income: dict[pd.Timestamp, float] = {}
    for row in rows:
        ts = _fmp_statement_timestamp(row)
        if pd.isna(ts):
            continue
        eps_value = _first_float_value(
            row,
            "epsDiluted",
            "epsdiluted",
            "dilutedEPS",
            "dilutedEps",
            "diluted_eps",
            "eps",
        )
        revenue_value = _first_float_value(row, "revenue", "totalRevenue", "total_revenue")
        net_income_value = _first_float_value(row, "netIncome", "netincome", "net_income", "bottomLineNetIncome")
        if eps_value is not None:
            eps[ts] = eps_value
        if revenue_value is not None:
            revenue[ts] = revenue_value
        if net_income_value is not None:
            net_income[ts] = net_income_value
    raw: QuarterlyRaw = {}
    if eps:
        raw["DilutedEPS"] = pd.Series(eps).sort_index(ascending=False)
    if revenue:
        raw["TotalRevenue"] = pd.Series(revenue).sort_index(ascending=False)
    if net_income:
        raw["NetIncome"] = pd.Series(net_income).sort_index(ascending=False)
    return raw


def _raw_from_fmp_annual_income_statement(rows: list[dict[str, Any]]) -> QuarterlyRaw:
    eps: dict[pd.Timestamp, float] = {}
    revenue: dict[pd.Timestamp, float] = {}
    net_income: dict[pd.Timestamp, float] = {}
    for row in rows:
        ts = _fmp_statement_timestamp(row)
        if pd.isna(ts):
            continue
        eps_value = _first_float_value(
            row,
            "epsDiluted",
            "epsdiluted",
            "dilutedEPS",
            "dilutedEps",
            "diluted_eps",
            "eps",
        )
        revenue_value = _first_float_value(row, "revenue", "totalRevenue", "total_revenue")
        net_income_value = _first_float_value(row, "netIncome", "netincome", "net_income", "bottomLineNetIncome")
        if eps_value is not None:
            eps[ts] = eps_value
        if revenue_value is not None:
            revenue[ts] = revenue_value
        if net_income_value is not None:
            net_income[ts] = net_income_value
    raw: QuarterlyRaw = {}
    if eps:
        raw["AnnualDilutedEPS"] = pd.Series(eps).sort_index(ascending=False)
    if revenue:
        raw["AnnualTotalRevenue"] = pd.Series(revenue).sort_index(ascending=False)
    if net_income:
        raw["AnnualNetIncome"] = pd.Series(net_income).sort_index(ascending=False)
    return raw


def _raw_from_fmp_annual_balance_sheet(rows: list[dict[str, Any]]) -> QuarterlyRaw:
    equity: dict[pd.Timestamp, float] = {}
    for row in rows:
        ts = _fmp_statement_timestamp(row)
        if pd.isna(ts):
            continue
        value = _first_float_value(
            row,
            "totalStockholdersEquity",
            "totalEquity",
            "totalEquityGrossMinorityInterest",
            "stockholdersEquity",
            "shareholdersEquity",
        )
        if value is None:
            assets = _first_float_value(row, "totalAssets", "assets")
            liabilities = _first_float_value(row, "totalLiabilities", "liabilities")
            if assets is not None and liabilities is not None:
                value = assets - liabilities
        if value is not None:
            equity[ts] = value
    if not equity:
        return {}
    return {"AnnualStockholdersEquity": pd.Series(equity).sort_index(ascending=False)}


def _raw_from_fmp_quarterly_growth(rows: list[dict[str, Any]]) -> QuarterlyRaw:
    eps_growth: dict[pd.Timestamp, float] = {}
    revenue_growth: dict[pd.Timestamp, float] = {}
    for row in rows:
        ts = _fmp_statement_timestamp(row)
        if pd.isna(ts):
            continue
        eps_value = _first_float_value(
            row,
            "growthEPSDiluted",
            "growthEpsDiluted",
            "growthEPS",
            "epsDilutedGrowth",
            "epsdilutedGrowth",
            "epsGrowth",
        )
        revenue_value = _first_float_value(
            row,
            "growthRevenue",
            "revenueGrowth",
            "growthTotalRevenue",
            "totalRevenueGrowth",
        )
        if eps_value is not None:
            eps_growth[ts] = eps_value
        if revenue_value is not None:
            revenue_growth[ts] = revenue_value
    raw: QuarterlyRaw = {}
    if eps_growth:
        raw["QuarterlyDilutedEPSGrowthPct"] = pd.Series(eps_growth).sort_index(ascending=False)
    if revenue_growth:
        raw["QuarterlyRevenueGrowthPct"] = pd.Series(revenue_growth).sort_index(ascending=False)
    return raw


def _raw_from_fmp_annual_growth(rows: list[dict[str, Any]]) -> QuarterlyRaw:
    eps_growth: dict[pd.Timestamp, float] = {}
    revenue_growth: dict[pd.Timestamp, float] = {}
    for row in rows:
        ts = _fmp_statement_timestamp(row)
        if pd.isna(ts):
            continue
        eps_value = _first_float_value(
            row,
            "growthEPSDiluted",
            "growthEpsDiluted",
            "growthEPS",
            "epsDilutedGrowth",
            "epsdilutedGrowth",
            "epsGrowth",
        )
        revenue_value = _first_float_value(
            row,
            "growthRevenue",
            "revenueGrowth",
            "growthTotalRevenue",
            "totalRevenueGrowth",
        )
        if eps_value is not None:
            eps_growth[ts] = eps_value
        if revenue_value is not None:
            revenue_growth[ts] = revenue_value
    raw: QuarterlyRaw = {}
    if eps_growth:
        raw["AnnualDilutedEPSGrowthPct"] = pd.Series(eps_growth).sort_index(ascending=False)
    if revenue_growth:
        raw["AnnualRevenueGrowthPct"] = pd.Series(revenue_growth).sort_index(ascending=False)
    return raw


def _raw_from_yfinance_statements(
    *,
    quarterly_income_stmt: pd.DataFrame | None,
    annual_income_stmt: pd.DataFrame | None,
    annual_balance_sheet: pd.DataFrame | None,
) -> QuarterlyRaw:
    raw: QuarterlyRaw = {}
    quarterly_eps = _series_from_yfinance_statement(
        quarterly_income_stmt,
        "Diluted EPS",
        "DilutedEPS",
        "Basic EPS",
    )
    quarterly_revenue = _series_from_yfinance_statement(
        quarterly_income_stmt,
        "Total Revenue",
        "TotalRevenue",
        "Revenue",
    )
    quarterly_net_income = _series_from_yfinance_statement(
        quarterly_income_stmt,
        "Net Income",
        "NetIncome",
        "Net Income Common Stockholders",
    )
    annual_eps = _series_from_yfinance_statement(
        annual_income_stmt,
        "Diluted EPS",
        "DilutedEPS",
        "Basic EPS",
    )
    annual_revenue = _series_from_yfinance_statement(
        annual_income_stmt,
        "Total Revenue",
        "TotalRevenue",
        "Revenue",
    )
    annual_net_income = _series_from_yfinance_statement(
        annual_income_stmt,
        "Net Income",
        "NetIncome",
        "Net Income Common Stockholders",
    )
    annual_equity = _series_from_yfinance_statement(
        annual_balance_sheet,
        "Stockholders Equity",
        "StockholdersEquity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity",
    )
    if quarterly_eps is not None:
        raw["DilutedEPS"] = quarterly_eps
    if quarterly_revenue is not None:
        raw["TotalRevenue"] = quarterly_revenue
    if quarterly_net_income is not None:
        raw["NetIncome"] = quarterly_net_income
    if annual_eps is not None:
        raw["AnnualDilutedEPS"] = annual_eps
    if annual_revenue is not None:
        raw["AnnualTotalRevenue"] = annual_revenue
    if annual_net_income is not None:
        raw["AnnualNetIncome"] = annual_net_income
    if annual_equity is not None:
        raw["AnnualStockholdersEquity"] = annual_equity
    return raw


def _series_from_yfinance_statement(frame: pd.DataFrame | None, *row_names: str) -> pd.Series | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    by_normalized = {_normalize_statement_row_name(index): index for index in frame.index}
    selected = None
    for name in row_names:
        selected = by_normalized.get(_normalize_statement_row_name(name))
        if selected is not None:
            break
    if selected is None:
        return None
    try:
        series = pd.to_numeric(frame.loc[selected], errors="coerce").dropna()
    except Exception:
        return None
    if series.empty:
        return None
    series.index = pd.to_datetime(series.index, errors="coerce")
    series = series[~pd.isna(series.index)]
    if series.empty:
        return None
    return series.sort_index(ascending=False)


def _normalize_statement_row_name(value: Any) -> str:
    return "".join(char for char in str(value or "").lower() if char.isalnum())


def _fmp_statement_timestamp(row: dict[str, Any]) -> pd.Timestamp:
    raw_date = (
        row.get("date")
        or row.get("fiscalDateEnding")
        or row.get("fiscal_date_ending")
        or row.get("period")
    )
    parsed = pd.to_datetime(raw_date, errors="coerce")
    if not pd.isna(parsed):
        return parsed
    year = row.get("calendarYear") or row.get("year") or row.get("fiscalYear")
    period = str(row.get("period") or "").strip().upper()
    quarter_month_by_period = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}
    if period in quarter_month_by_period:
        try:
            month = quarter_month_by_period[period]
            return pd.Timestamp(year=int(year), month=month, day=1) + pd.offsets.MonthEnd(0)
        except (TypeError, ValueError):
            return pd.NaT
    try:
        return pd.Timestamp(year=int(year), month=12, day=31)
    except (TypeError, ValueError):
        return pd.NaT


def _merge_fmp_ttm_ratios(raw: QuarterlyRaw, ticker: str, api_key: str, *, timeout: int) -> None:
    attempts = [
        (FMP_RATIOS_TTM_URL, {"symbol": ticker.upper(), "apikey": api_key}),
    ]
    for url, params in attempts:
        try:
            response = requests.get(url, params=params, timeout=min(timeout, 10))
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        try:
            payload = response.json()
        except ValueError:
            continue
        item = payload[0] if isinstance(payload, list) and payload else payload if isinstance(payload, dict) else {}
        roe = _float_or_none(item.get("returnOnEquityTTM"))
        margin = _float_or_none(item.get("netProfitMarginTTM"))
        if roe is not None:
            raw["_roe_ttm"] = roe
        if margin is not None:
            raw["_pm_ttm"] = margin
        return


def _extract_sec_duration_series(
    facts: dict[str, Any],
    *,
    concepts: list[str],
    unit_keys: list[str],
    duration_min: int | None = None,
    duration_max: int | None = None,
) -> pd.Series | None:
    by_end: dict[pd.Timestamp, tuple[pd.Timestamp, float]] = {}
    for concept in concepts:
        units = ((facts.get(concept) or {}).get("units") or {})
        for unit_key in unit_keys:
            for item in units.get(unit_key) or []:
                if str(item.get("form") or "") not in {"10-Q", "10-K"}:
                    continue
                if str(item.get("fp") or "") not in {"Q1", "Q2", "Q3", "Q4"}:
                    continue
                end = pd.to_datetime(item.get("end"), errors="coerce")
                value = _float_or_none(item.get("val"))
                if pd.isna(end) or value is None:
                    continue
                if duration_min is not None or duration_max is not None:
                    start = pd.to_datetime(item.get("start"), errors="coerce")
                    if pd.isna(start):
                        continue
                    days = int((end - start).days)
                    if duration_min is not None and days < duration_min:
                        continue
                    if duration_max is not None and days > duration_max:
                        continue
                filed = pd.to_datetime(item.get("filed"), errors="coerce")
                filed = filed if not pd.isna(filed) else pd.Timestamp.min
                previous = by_end.get(end)
                if previous is None or filed > previous[0]:
                    by_end[end] = (filed, value)
    return _series_from_by_end(by_end)


def _extract_sec_quarterly_series(
    facts: dict[str, Any],
    *,
    concepts: list[str],
    unit_keys: list[str],
    duration_min: int | None = None,
    duration_max: int | None = None,
) -> pd.Series | None:
    direct = _extract_sec_duration_series(
        facts,
        concepts=concepts,
        unit_keys=unit_keys,
        duration_min=duration_min,
        duration_max=duration_max,
    )
    derived_q4 = _extract_sec_derived_q4_series(facts, concepts=concepts, unit_keys=unit_keys)
    return _merge_series_prefer_primary(direct, derived_q4)


def _extract_sec_derived_q4_series(
    facts: dict[str, Any],
    *,
    concepts: list[str],
    unit_keys: list[str],
) -> pd.Series | None:
    by_end: dict[pd.Timestamp, tuple[pd.Timestamp, float]] = {}
    for concept in concepts:
        units = ((facts.get(concept) or {}).get("units") or {})
        for unit_key in unit_keys:
            items = [_sec_duration_item(item) for item in units.get(unit_key) or []]
            valid_items = [item for item in items if item is not None]
            annual_items = [
                item
                for item in valid_items
                if item["form"] == "10-K" and item["fp"] == "FY" and 330 <= item["days"] <= 380
            ]
            ytd_q3_items = [
                item
                for item in valid_items
                if item["form"] == "10-Q" and item["fp"] == "Q3" and 240 <= item["days"] <= 290
            ]
            for annual in annual_items:
                candidates = [
                    item
                    for item in ytd_q3_items
                    if item["start"] == annual["start"] and 70 <= (annual["end"] - item["end"]).days <= 120
                ]
                if not candidates:
                    continue
                ytd_q3 = max(candidates, key=lambda item: (item["end"], item["filed"]))
                derived_value = round(float(annual["value"] - ytd_q3["value"]), 6)
                previous = by_end.get(annual["end"])
                if previous is None or annual["filed"] > previous[0]:
                    by_end[annual["end"]] = (annual["filed"], derived_value)
    return _series_from_by_end(by_end)


def _sec_duration_item(item: dict[str, Any]) -> dict[str, Any] | None:
    form = str(item.get("form") or "")
    fp = str(item.get("fp") or "")
    if form not in {"10-Q", "10-K"}:
        return None
    end = pd.to_datetime(item.get("end"), errors="coerce")
    start = pd.to_datetime(item.get("start"), errors="coerce")
    value = _float_or_none(item.get("val"))
    if pd.isna(end) or pd.isna(start) or value is None:
        return None
    filed = pd.to_datetime(item.get("filed"), errors="coerce")
    filed = filed if not pd.isna(filed) else pd.Timestamp.min
    return {
        "form": form,
        "fp": fp,
        "start": start,
        "end": end,
        "filed": filed,
        "value": value,
        "days": int((end - start).days),
    }


def _merge_series_prefer_primary(primary: pd.Series | None, secondary: pd.Series | None) -> pd.Series | None:
    if primary is None:
        return secondary
    if secondary is None:
        return primary
    missing_secondary = secondary[~secondary.index.isin(primary.index)]
    if missing_secondary.empty:
        return primary.sort_index(ascending=False)
    return pd.concat([primary, missing_secondary]).sort_index(ascending=False)


def _extract_sec_point_series(
    facts: dict[str, Any],
    *,
    concepts: list[str],
    unit_keys: list[str],
) -> pd.Series | None:
    by_end: dict[pd.Timestamp, tuple[pd.Timestamp, float]] = {}
    for concept in concepts:
        units = ((facts.get(concept) or {}).get("units") or {})
        for unit_key in unit_keys:
            for item in units.get(unit_key) or []:
                if str(item.get("form") or "") not in {"10-Q", "10-K"}:
                    continue
                end = pd.to_datetime(item.get("end"), errors="coerce")
                value = _float_or_none(item.get("val"))
                if pd.isna(end) or value is None:
                    continue
                filed = pd.to_datetime(item.get("filed"), errors="coerce")
                filed = filed if not pd.isna(filed) else pd.Timestamp.min
                previous = by_end.get(end)
                if previous is None or filed > previous[0]:
                    by_end[end] = (filed, value)
        if by_end:
            break
    return _series_from_by_end(by_end)


def _series_from_by_end(values: dict[pd.Timestamp, tuple[pd.Timestamp, float]]) -> pd.Series | None:
    if not values:
        return None
    return pd.Series({end: value for end, (_, value) in values.items()}).sort_index(ascending=False)


def _growth_point(label: str, current: float, previous: float | None) -> GrowthPoint:
    if previous is None:
        return GrowthPoint(label, None, "missing_prior", current, None)
    if previous < 0 < current:
        return GrowthPoint(label, None, "turnaround", current, previous)
    if previous < 0 and current <= 0:
        return GrowthPoint(label, None, "still_neg", current, previous)
    if previous > 0 > current:
        return GrowthPoint(label, None, "turned_neg", current, previous)
    if previous == 0:
        return GrowthPoint(label, None, "prev_zero", current, previous)
    return GrowthPoint(label, round((current / previous - 1) * 100, 1), None, current, previous)


def _growth_point_payload(point: GrowthPoint, *, prefix: str) -> dict[str, Any]:
    return {
        "fiscal_period": point.label,
        f"{prefix}_current_quarter": point.current,
        f"{prefix}_same_quarter_last_year": point.previous,
        f"{prefix}_growth_yoy_pct": point.growth_pct,
        "growth_pct": point.growth_pct,
        "flag": point.flag,
    }


def _annual_growth_point_payload(point: GrowthPoint, *, prefix: str) -> dict[str, Any]:
    return {
        "fiscal_year": point.label,
        f"{prefix}_current_year": point.current,
        f"{prefix}_previous_year": point.previous,
        f"{prefix}_growth_yoy_pct": point.growth_pct,
        "growth_pct": point.growth_pct,
        "flag": point.flag,
    }


def _roe_point_payload(point: GrowthPoint) -> dict[str, Any]:
    return {
        "fiscal_year": point.label,
        "roe_pct": point.growth_pct,
        "net_income": point.current,
        "shareholders_equity": point.previous,
        "flag": point.flag,
    }


def _latest_numeric_growth(points: list[GrowthPoint]) -> float | None:
    for point in points:
        if point.growth_pct is not None:
            return point.growth_pct
    return None


def _is_accelerating(points: list[GrowthPoint]) -> bool | None:
    latest_three = points[:3]
    if (
        len(latest_three) < 3
        or any(point.growth_pct is None or point.flag is not None for point in latest_three)
    ):
        return None
    rates = [float(point.growth_pct) for point in latest_three if point.growth_pct is not None]
    return all(rates[index] > rates[index + 1] for index in range(len(rates) - 1))


def _trailing_sum(value: Any, *, periods: int) -> float | None:
    if not isinstance(value, pd.Series):
        return None
    series = pd.to_numeric(value, errors="coerce").dropna().sort_index(ascending=False)
    if len(series) < periods:
        return None
    return round(float(series.iloc[:periods].sum()), 2)


def _roe_pct(raw: QuarterlyRaw) -> float | None:
    fmp_value = _ratio_to_pct(raw.get("_roe_ttm"))
    if fmp_value is not None:
        return fmp_value
    ttm_income = _trailing_sum(raw.get("NetIncome"), periods=4)
    equity = raw.get("StockholdersEquity")
    if ttm_income is None or not isinstance(equity, pd.Series):
        return None
    equity_series = pd.to_numeric(equity, errors="coerce").dropna().sort_index(ascending=False)
    if equity_series.empty or float(equity_series.iloc[0]) == 0:
        return None
    return round(float(ttm_income / float(equity_series.iloc[0]) * 100), 1)


def _profit_margin_pct(raw: QuarterlyRaw) -> float | None:
    fmp_value = _ratio_to_pct(raw.get("_pm_ttm"))
    if fmp_value is not None:
        return fmp_value
    ttm_income = _trailing_sum(raw.get("NetIncome"), periods=4)
    ttm_revenue = _trailing_sum(raw.get("TotalRevenue"), periods=4)
    if ttm_income is None or ttm_revenue in (None, 0):
        return None
    return round(float(ttm_income / ttm_revenue * 100), 1)


def _latest_period_label(raw: QuarterlyRaw) -> str:
    for key in ["DilutedEPS", "TotalRevenue", "NetIncome"]:
        value = raw.get(key)
        if isinstance(value, pd.Series) and not value.empty:
            ts = pd.to_datetime(value.sort_index(ascending=False).index[0], errors="coerce")
            if not pd.isna(ts):
                return f"{int(ts.year)} Q{int(ts.quarter)}"
    return ""


def _needs_yfinance_statement_history(raw: QuarterlyRaw | None) -> bool:
    if not raw:
        return True
    return (
        _usable_growth_count(quarterly_yoy_growth(raw, "eps")) < 3
        or _usable_growth_count(quarterly_yoy_growth(raw, "revenue")) < 3
        or _usable_growth_count(annual_yoy_growth(raw, "eps")) < 3
        or _usable_growth_count(annual_yoy_growth(raw, "revenue")) < 3
    )


def _usable_growth_count(points: list[GrowthPoint]) -> int:
    return sum(
        1
        for point in points[:3]
        if point.growth_pct is not None or (point.current is not None and point.previous is not None)
    )


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "incomeStatement", "incomeStatements"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        if payload:
            return [payload]
    return []


def _safe_yfinance_frame(ticker: Any, *attributes: str) -> pd.DataFrame | None:
    for attribute in attributes:
        try:
            value = getattr(ticker, attribute)
        except Exception:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value
    return None


def _first_float_value(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _float_or_none(row.get(key))
        if value is not None:
            return value
    return None


def _ratio_to_pct(value: Any) -> float | None:
    number = _float_or_none(value)
    if number is None:
        return None
    if abs(number) <= 5:
        number *= 100
    return round(number, 1)


def _normalize_growth_pct(value: float) -> float:
    number = float(value)
    if abs(number) <= 5:
        number *= 100
    return round(number, 1)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _compact_metadata(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "symbol",
        "companyName",
        "currency",
        "exchangeShortName",
        "industry",
        "sector",
        "beta",
    }
    return {key: value.get(key) for key in allowed if value.get(key) not in (None, "")}
