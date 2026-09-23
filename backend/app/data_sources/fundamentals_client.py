from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import pandas as pd
import requests

from app.data_sources.fmp_client import (
    FMP_BALANCE_SHEET_URL,
    FMP_INCOME_STATEMENT_URL,
    compact_fmp_response_body,
)
from app.data_sources.provider_guard import guarded_fmp_get
from app.data_sources.provider_usage import current_provider_usage, record_provider_event
from app.data_sources.sec_companyfacts_cache import bulk_status, load_companyfacts
from app.data_sources.sec_request import SecRequestError, sec_get
from app.data_sources.source_priority import SOURCE_PRIORITY


QuarterlyRaw = dict[str, pd.Series | float | str]

SEC_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A",
             "40-F", "40-F/A", "6-K", "6-K/A"}
SEC_CONCEPTS = {
    "DilutedEPS": {
        "us-gaap": ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted",
                    "IncomeLossFromContinuingOperationsPerDilutedShare"),
        "ifrs-full": ("DilutedEarningsLossPerShare", "DilutedEarningsLossPerShareFromContinuingOperations"),
    },
    "TotalRevenue": {
        "us-gaap": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"),
        "ifrs-full": ("Revenue", "RevenueFromContractsWithCustomers"),
    },
    "NetIncome": {
        "us-gaap": ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"),
        "ifrs-full": ("ProfitLoss", "ProfitLossAttributableToOwnersOfParent"),
    },
    "StockholdersEquity": {
        "us-gaap": ("StockholdersEquity", "StockholdersEquityAttributableToParent", "Equity"),
        "ifrs-full": ("EquityAttributableToOwnersOfParent", "Equity"),
    },
}


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
    statements_only: bool = False,
    previous_metadata: dict[str, Any] | None = None,
    force_live_sec: bool = False,
) -> FundamentalEnrichment:
    clean = ticker.strip().upper()
    notes: list[str] = []
    raw = _raw_from_previous_metadata(previous_metadata or {})
    sources: dict[str, str] = {}
    for key in raw or {}:
        sources[key] = "local_snapshot"
    fallback: list[str] = []
    reason_code = ""
    statement_currency = ((previous_metadata or {}).get("enrichment") or {}).get("statement_currency", "USD")
    has_known_currency = bool(raw) and statement_currency != "unknown"
    if raw and not _needs_fmp_statement_data(raw) and not force_live_sec:
        notes.append("Vollständiger lokaler Snapshot")
        record_provider_event("cache_hits")
    elif sec_user_agent:
        sec_raw, sec_note = fetch_quarterly_sec_companyfacts(clean, sec_user_agent,
                                                               timeout=timeout, force_live=force_live_sec)
        notes.append(sec_note)
        if "currency=" in sec_note:
            statement_currency = sec_note.rsplit("currency=", 1)[-1].split()[0]
        if sec_raw:
            raw = merge_quarterly_raw(sec_raw, raw)
            has_known_currency = True
            source = "sec_bulk_cache" if "bulk" in sec_note else "sec_companyfacts_live"
            for key in sec_raw:
                sources[key] = source
            if source == "sec_bulk_cache" and not force_live_sec and _needs_fmp_statement_data(raw):
                try:
                    fetched_at = datetime.fromisoformat(str(bulk_status().get("fetched_at", "")))
                except ValueError:
                    fetched_at = None
                if fetched_at is None or (datetime.now(fetched_at.tzinfo) - fetched_at).total_seconds() > 36 * 3600:
                    live_raw, live_note = fetch_quarterly_sec_companyfacts(clean, sec_user_agent,
                                                                           timeout=timeout, force_live=True)
                    notes.append(live_note)
                    if live_raw:
                        raw = merge_quarterly_raw(live_raw, raw)
                        for key in live_raw:
                            sources[key] = "sec_companyfacts_live"
        if "live_rate_limited" in sec_note:
            reason_code = "rate_limited"
        elif "live_provider_error" in sec_note:
            reason_code = "provider_error"
        elif not sec_raw and "rate_limited" in sec_note:
            reason_code = "rate_limited"
        elif not sec_raw and "unsupported_taxonomy" in sec_note:
            reason_code = "unsupported_taxonomy"
        elif not sec_raw:
            reason_code = "waiting_sec_data"
    elif not sec_user_agent:
        notes.append("SEC_USER_AGENT fehlt")
        reason_code = "waiting_sec_data"
    if _needs_fmp_statement_data(raw):
        record_provider_event("fallback_used")
        fallback.append("yfinance")
        yf_raw, yf_note = fetch_yfinance_statement_history(clean)
        notes.append(yf_note)
        yf_currency = (yf_raw or {}).get("_statement_currency")
        if yf_raw and has_known_currency and yf_currency != statement_currency:
            notes.append(f"Yahoo-Berichtswährung {yf_currency or 'unbekannt'} passt nicht zu {statement_currency}; Werte verworfen")
            yf_raw = None
            reason_code = "waiting_yahoo_data"
        elif yf_raw and yf_currency:
            statement_currency = str(yf_currency)
            has_known_currency = True
        elif yf_raw and not has_known_currency:
            statement_currency = "unknown"
        raw = merge_quarterly_raw(raw, yf_raw)
        if yf_raw:
            for key in yf_raw:
                sources.setdefault(key, "yfinance")
        elif not reason_code:
            reason_code = "waiting_yahoo_data"

    if _needs_fmp_statement_data(raw) and fmp_api_key:
        record_provider_event("fallback_used")
        fallback.append("fmp")
        fmp_raw, fmp_note = fetch_quarterly_fmp(clean, fmp_api_key, timeout=timeout, minimal=True,
                                                needed_fields=_missing_fmp_fields(raw))
        notes.append(fmp_note)
        fmp_currency = (fmp_raw or {}).get("_statement_currency")
        if fmp_raw and has_known_currency and fmp_currency != statement_currency:
            notes.append(f"FMP-Berichtswährung {fmp_currency or 'unbekannt'} passt nicht zu {statement_currency}; Werte verworfen")
            fmp_raw = None
            reason_code = "waiting_fmp_fallback"
        elif fmp_raw and fmp_currency:
            statement_currency = str(fmp_currency)
            has_known_currency = True
        elif fmp_raw and not has_known_currency:
            statement_currency = "unknown"
        raw = merge_quarterly_raw(raw, fmp_raw)
        if fmp_raw:
            for key in fmp_raw:
                sources.setdefault(key, "fmp")
        elif "Rate Limited" in fmp_note:
            reason_code = "rate_limited"
        else:
            reason_code = "waiting_fmp_fallback"

    enrichment = compute_fundamental_enrichment(clean, raw, notes=notes)
    metadata = {
        **enrichment.metadata,
        "data_sources": {
            "eps": sources.get("DilutedEPS") or sources.get("AnnualDilutedEPS"),
            "revenue": sources.get("TotalRevenue") or sources.get("AnnualTotalRevenue"),
            "net_income": sources.get("NetIncome") or sources.get("AnnualNetIncome"),
            "equity": sources.get("StockholdersEquity") or sources.get("AnnualStockholdersEquity"),
        },
        "fallbacks_used": fallback,
        "fmp_requests_used": current_provider_usage().get("fmp_requests", 0),
        "statement_currency": statement_currency,
        "source_priority": list(SOURCE_PRIORITY["statements"]),
        "reason_code": reason_code if _needs_fmp_statement_data(raw) else "",
    }
    return replace(enrichment, metadata=metadata)


def fetch_quarterly_fmp(
    ticker: str,
    api_key: str,
    *,
    timeout: int = 15,
    minimal: bool = False,
    needed_fields: set[str] | None = None,
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
    ]
    errors: list[str] = []
    raw: QuarterlyRaw = {}
    for label, url, params, parser in attempts:
        if needed_fields is not None:
            relevant = ({"AnnualStockholdersEquity"} if "Bilanz" in label else
                        {"AnnualDilutedEPS", "AnnualTotalRevenue", "AnnualNetIncome"} if "jaehrlich" in label else
                        {"DilutedEPS", "TotalRevenue", "NetIncome"})
            if not relevant & needed_fields:
                continue
        try:
            response = guarded_fmp_get(url, params=params, timeout=timeout)
        except requests.exceptions.Timeout:
            errors.append(f"{label}: Timeout")
            continue
        except requests.exceptions.ConnectionError as exc:
            errors.append(f"{label}: Verbindung {str(exc)[:60]}")
            continue

        if response.status_code == 429:
            body = compact_fmp_response_body(response)
            errors.append(f"{label}: Rate Limited" + (f" ({body})" if body else ""))
            break
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
        existing_currency = raw.get("_statement_currency")
        incoming_currency = parsed.get("_statement_currency")
        if existing_currency and incoming_currency != existing_currency:
            errors.append(f"{label}: abweichende Berichtswährung")
            continue
        raw = merge_quarterly_raw(raw, parsed) or raw
        if not any(isinstance(value, pd.Series) and not value.empty for value in parsed.values()):
            errors.append(f"{label}: Keine verwertbaren Daten")

    if raw and any(isinstance(value, pd.Series) and not value.empty for value in raw.values()):
        return raw, "FMP stable"

    return None, " | ".join(errors) if errors else "FMP: keine Quartalsdaten"


def fetch_quarterly_sec_companyfacts(
    ticker: str,
    user_agent: str,
    *,
    timeout: int = 15,
    force_live: bool = False,
) -> tuple[QuarterlyRaw | None, str]:
    clean = ticker.upper().strip()
    if not clean:
        return None, "SEC: kein Ticker"
    if not user_agent.strip():
        return None, "SEC: kein User-Agent"

    try:
        cik = _sec_cik_map(user_agent.strip(), timeout).get(clean, "")
        if not cik:
            return None, "SEC: Ticker nicht im CIK-Universum"
        facts_payload, source = load_companyfacts(cik, user_agent, timeout=timeout, force_live=force_live)
    except requests.exceptions.Timeout:
        return None, "SEC: Timeout"
    except requests.exceptions.ConnectionError as exc:
        return None, f"SEC: Verbindung {str(exc)[:60]}"
    except ValueError:
        return None, "SEC: Ungueltiges JSON"
    except SecRequestError as exc:
        return None, f"SEC {exc.reason_code}: {exc}"
    except (RuntimeError, requests.RequestException) as exc:
        return None, f"SEC provider_error: {exc}"

    fact_data = (facts_payload or {}).get("facts") or {}
    currency = _sec_statement_currency(fact_data)
    if currency is None:
        return None, "SEC unsupported_taxonomy: widersprüchliche Währungseinheiten"
    raw = _raw_from_sec_facts(fact_data, currency=currency)
    if not raw:
        return None, "SEC unsupported_taxonomy: keine sicher zuordenbaren standardisierten Fakten"
    return raw, f"SEC {source} currency={currency}"


def _sec_statement_currency(facts_by_taxonomy: dict[str, Any]) -> str | None:
    sets: list[set[str]] = []
    for key, by_taxonomy in SEC_CONCEPTS.items():
        currencies = set()
        for taxonomy, concepts in by_taxonomy.items():
            facts = facts_by_taxonomy.get(taxonomy) or {}
            for concept in concepts:
                for unit in ((facts.get(concept) or {}).get("units") or {}):
                    base = unit.removesuffix("/shares") if key == "DilutedEPS" else unit
                    if base.isalpha() and len(base) == 3 and (unit.endswith("/shares") == (key == "DilutedEPS")):
                        currencies.add(base)
        if currencies:
            sets.append(currencies)
    if not sets:
        return "USD"
    common = set.intersection(*sets)
    if "USD" in common:
        return "USD"
    return next(iter(common)) if len(common) == 1 else None


def _raw_from_sec_facts(facts_by_taxonomy: dict[str, Any], *, currency: str = "USD") -> QuarterlyRaw:
    raw: QuarterlyRaw = {}
    for key, by_taxonomy in SEC_CONCEPTS.items():
        for taxonomy in ("us-gaap", "ifrs-full"):
            facts = facts_by_taxonomy.get(taxonomy) or {}
            concepts = list(by_taxonomy[taxonomy])
            unit = [f"{currency}/shares"] if key == "DilutedEPS" else [currency]
            if key == "StockholdersEquity":
                points = _extract_sec_point_series(facts, concepts=concepts, unit_keys=unit)
                if points is not None:
                    raw[key] = _merge_series_prefer_primary(raw.get(key), points)
                    raw["AnnualStockholdersEquity"] = _merge_series_prefer_primary(
                        raw.get("AnnualStockholdersEquity"), points)
            else:
                quarter = _extract_sec_quarterly_series(facts, concepts=concepts, unit_keys=unit,
                                                        duration_min=60, duration_max=120)
                annual = _extract_sec_duration_series(facts, concepts=concepts, unit_keys=unit,
                                                      duration_min=330, duration_max=380)
                if quarter is not None:
                    raw[key] = _merge_series_prefer_primary(raw.get(key), quarter)
                if annual is not None:
                    annual_key = {"DilutedEPS": "AnnualDilutedEPS", "TotalRevenue": "AnnualTotalRevenue",
                                  "NetIncome": "AnnualNetIncome"}[key]
                    raw[annual_key] = _merge_series_prefer_primary(raw.get(annual_key), annual)
    return raw


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
        if raw:
            try:
                record_provider_event("yahoo_requests")
                info = yf_ticker.get_info()
                currency = str((info or {}).get("financialCurrency") or "").upper()
                if len(currency) == 3 and currency.isalpha():
                    raw["_statement_currency"] = currency
            except Exception:
                pass
    except Exception as exc:
        return None, f"yfinance Statements: {type(exc).__name__}: {str(exc)[:80]}"
    if not raw:
        return None, "yfinance Statements: keine Historie"
    return raw, "yfinance statements"


@lru_cache(maxsize=4)
def _sec_cik_map(user_agent: str, timeout: int) -> dict[str, str]:
    response = sec_get("https://www.sec.gov/files/company_tickers.json", user_agent=user_agent, timeout=timeout)
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


def _raw_from_previous_metadata(metadata: dict[str, Any]) -> QuarterlyRaw | None:
    serialized = (metadata.get("enrichment") or {}).get("raw_series") or metadata.get("raw_series") or {}
    result: QuarterlyRaw = {}
    for key, rows in serialized.items():
        if not isinstance(rows, dict):
            continue
        values = {}
        for period, number in rows.items():
            stamp = pd.to_datetime(period, errors="coerce")
            value = _float_or_none(number)
            if not pd.isna(stamp) and value is not None:
                values[stamp] = value
        if values:
            result[key] = pd.Series(values).sort_index(ascending=False)
    return result or None


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
            "report_ends": {
                key: str(pd.Timestamp(value.index.max()).date())
                for key, value in raw.items() if key in {"DilutedEPS", "TotalRevenue"}
                and isinstance(value, pd.Series) and not value.empty
            },
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
            "raw_series": {
                key: {str(pd.Timestamp(index).date()): float(number) for index, number in value.items()}
                for key, value in raw.items() if isinstance(value, pd.Series)
                and key in {"DilutedEPS", "TotalRevenue", "NetIncome", "StockholdersEquity",
                            "AnnualDilutedEPS", "AnnualTotalRevenue", "AnnualNetIncome", "AnnualStockholdersEquity"}
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
        prior_equity = equity_by_year.get(year - 1)
        denominator = (equity + prior_equity) / 2 if prior_equity is not None else equity
        if denominator == 0:
            points.append(GrowthPoint(str(year), None, "missing_equity", income, denominator))
            continue
        points.append(GrowthPoint(str(year), round(float(income / denominator * 100), 1), None,
                                  income, denominator))
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
    currency = _fmp_statement_currency(rows)
    if currency:
        raw["_statement_currency"] = currency
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
    currency = _fmp_statement_currency(rows)
    if currency:
        raw["_statement_currency"] = currency
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
    raw: QuarterlyRaw = {"AnnualStockholdersEquity": pd.Series(equity).sort_index(ascending=False)}
    currency = _fmp_statement_currency(rows)
    if currency:
        raw["_statement_currency"] = currency
    return raw


def _fmp_statement_currency(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        value = str(row.get("reportedCurrency") or row.get("reportingCurrency") or "").upper()
        if len(value) == 3 and value.isalpha():
            return value
    return ""


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
        concept_by_end: dict[pd.Timestamp, tuple[pd.Timestamp, float]] = {}
        units = ((facts.get(concept) or {}).get("units") or {})
        for unit_key in unit_keys:
            for item in units.get(unit_key) or []:
                if str(item.get("form") or "") not in SEC_FORMS:
                    continue
                if str(item.get("fp") or "") not in {"Q1", "Q2", "Q3", "Q4", "FY"}:
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
                previous = concept_by_end.get(end)
                if previous is None or filed > previous[0]:
                    concept_by_end[end] = (filed, value)
        for end, value in concept_by_end.items():
            by_end.setdefault(end, value)
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
                if item["form"] in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
                and item["fp"] == "FY" and 330 <= item["days"] <= 380
            ]
            ytd_q3_items = [
                item
                for item in valid_items
                if item["form"] in {"10-Q", "10-Q/A", "6-K", "6-K/A"}
                and item["fp"] == "Q3" and 240 <= item["days"] <= 290
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
    if form not in SEC_FORMS:
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
                if str(item.get("form") or "") not in SEC_FORMS:
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
    latest = series.iloc[:periods]
    dates = [pd.to_datetime(index, errors="coerce") for index in latest.index]
    if any(pd.isna(stamp) for stamp in dates) or any(
        not 60 <= (newer - older).days <= 120 for newer, older in zip(dates, dates[1:])
    ):
        return None
    return round(float(latest.sum()), 2)


def _roe_pct(raw: QuarterlyRaw) -> float | None:
    ttm_income = _trailing_sum(raw.get("NetIncome"), periods=4)
    equity = raw.get("StockholdersEquity")
    if not isinstance(equity, pd.Series):
        equity = raw.get("AnnualStockholdersEquity")
    if ttm_income is None or not isinstance(equity, pd.Series):
        return None
    equity_series = pd.to_numeric(equity, errors="coerce").dropna().sort_index(ascending=False)
    if equity_series.empty:
        return None
    latest = float(equity_series.iloc[0])
    one_year_ago = equity_series[(equity_series.index <= equity_series.index[0] - pd.Timedelta(days=330))
                                 & (equity_series.index >= equity_series.index[0] - pd.Timedelta(days=400))]
    denominator = (latest + float(one_year_ago.iloc[0])) / 2 if not one_year_ago.empty else latest
    if denominator == 0:
        return None
    return round(float(ttm_income / denominator * 100), 1)


def _profit_margin_pct(raw: QuarterlyRaw) -> float | None:
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


def _needs_fmp_statement_data(raw: QuarterlyRaw | None) -> bool:
    return bool(_missing_fmp_fields(raw))


def _missing_fmp_fields(raw: QuarterlyRaw | None) -> set[str]:
    raw = raw or {}
    missing = set()
    for metric, quarterly_key, annual_key in (("eps", "DilutedEPS", "AnnualDilutedEPS"),
                                              ("revenue", "TotalRevenue", "AnnualTotalRevenue")):
        if _usable_growth_count(quarterly_yoy_growth(raw, metric)) < 3:
            missing.add(quarterly_key)
        if _usable_growth_count(annual_yoy_growth(raw, metric)) < 3:
            missing.add(annual_key)
    if _trailing_sum(raw.get("NetIncome"), periods=4) is None:
        missing.add("NetIncome")
    if not isinstance(raw.get("StockholdersEquity"), pd.Series) and not isinstance(raw.get("AnnualStockholdersEquity"), pd.Series):
        missing.add("AnnualStockholdersEquity")
    return missing


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
            record_provider_event("yahoo_requests")
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
