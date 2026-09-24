from __future__ import annotations

from dataclasses import asdict, fields, replace
from datetime import date

from app.core_config import get_settings
from app.data_sources.fundamentals_client import FundamentalEnrichment, fetch_fundamental_enrichment
from app.data_sources.provider_usage import capture_provider_usage
from app.data_sources.yfinance_client import FetchedFundamentals, fetch_fundamentals
from app.repositories import earnings as earnings_repository
from app.repositories.earnings import EarningsEventWrite
from app.repositories.fundamentals import (FundamentalSnapshotWrite, get_latest_fundamentals,
                                          upsert_fundamentals)
from app.services.settings import get_runtime_config_value
from app.domain.stocks.instrument_type import classify_instrument, inapplicable_reason
from app.data_sources.provider_usage import record_provider_event
from app.repositories import fundamentals as fundamentals_repository


def refresh_fundamentals_for_ticker(ticker: str, *, include_holders: bool = True) -> dict:
    clean = ticker.strip().upper()
    if not clean:
        raise ValueError("ticker must not be empty")

    previous = get_latest_fundamentals(clean)
    profile = fundamentals_repository.get_instrument_profile(clean)
    profile_metadata = profile.get("metadata") or {}
    kind = classify_instrument(ticker=clean, name=profile.get("name", ""), asset_class=profile.get("asset_class", ""),
                               etf=str((profile_metadata.get("nasdaq_listing") or {}).get("etf", "")),
                               nextshares=str((profile_metadata.get("nasdaq_listing") or {}).get("nextshares", "")),
                               sec_sic=profile_metadata.get("sec_sic") or "",
                               sec_forms=profile_metadata.get("sec_forms"),
                               previous_type=profile_metadata.get("instrument_type", ""))
    if inapplicable_reason(kind):
        if profile and kind != profile_metadata.get("instrument_type"):
            fundamentals_repository.save_instrument_classification(clean, kind, source="instrument_profile")
        for metric in ("avoided_sec_requests", "avoided_yahoo_fallbacks", "avoided_fmp_fallbacks",
                       "instrument_type_skipped"):
            record_provider_event(metric)
        return {"ticker": clean, "ok": True, "records_seen": 0, "records_written": 0,
                "instrument_type": kind, "reason_code": inapplicable_reason(kind),
                "provider_usage": {}}
    settings = get_settings()
    with capture_provider_usage() as usage:
        enrichment = fetch_fundamental_enrichment(
            clean,
            fmp_api_key=get_runtime_config_value("FMP_API_KEY") or settings.fmp_api_key,
            sec_user_agent=get_runtime_config_value("SEC_USER_AGENT") or settings.sec_user_agent,
            previous_metadata={**(previous.metadata_json if previous else {}), "instrument_type": kind},
        )
        found_kind = enrichment.metadata.get("instrument_type") or kind
        diagnostics = enrichment.metadata.get("statement_diagnostics") or {}
        forms = ([diagnostics["latest_annual_form"]] if diagnostics.get("latest_annual_form") else
                 diagnostics.get("forms_seen") or [])
        if found_kind != "unknown" and profile and (found_kind != profile_metadata.get("instrument_type") or forms != profile_metadata.get("sec_forms", [])):
            fundamentals_repository.save_instrument_classification(clean, found_kind, source="sec_companyfacts",
                                                                    sec_forms=forms)
        try:
            calendar_event = earnings_repository.next_earnings_event(clean, include_fmp=False)
        except earnings_repository.EarningsRepositoryUnavailable:
            calendar_event = None
        calendar_date = calendar_event[0] if calendar_event else None
        from app.services.report_refresh import cached_price_beta
        local_beta = cached_price_beta(clean)
        needs_yahoo = local_beta is None or calendar_date is None
        if needs_yahoo:
            fetched = fetch_fundamentals(clean, include_holders=False, include_calendar=calendar_date is None)
        else:
            empty = {field.name: None for field in fields(FetchedFundamentals)}
            empty.update(ticker=clean, as_of=date.today(), source="", fiscal_period="")
            fetched = FetchedFundamentals(**empty)
        if calendar_date is None and fetched.next_earnings_date is not None:
            try:
                earnings_repository.upsert_earnings_events([
                    EarningsEventWrite(ticker=clean, event_date=fetched.next_earnings_date, source="yfinance")
                ])
            except earnings_repository.EarningsRepositoryUnavailable:
                pass
        if calendar_date is None and fetched.next_earnings_date is None:
            try:
                fallback_event = earnings_repository.next_earnings_event(clean)
            except earnings_repository.EarningsRepositoryUnavailable:
                fallback_event = None
            if fallback_event and fallback_event[1] == "fmp":
                calendar_date = fallback_event[0]
                calendar_event = fallback_event
        enrichment = replace(enrichment, beta=local_beta if local_beta is not None else fetched.beta if fetched.beta is not None else enrichment.beta,
                             next_earnings_date=calendar_date or fetched.next_earnings_date or enrichment.next_earnings_date,
                             metadata={**enrichment.metadata,
                                       "beta_source": "local_price_cache" if local_beta is not None else "yfinance" if fetched.beta is not None else None,
                                       "earnings_date_source": calendar_event[1] if calendar_date is not None and calendar_event else "yfinance" if fetched.next_earnings_date is not None else None})
        write = merge_snapshot_write(previous, _to_write(fetched, enrichment))
        row = upsert_fundamentals(write)
    available_fields = [
        key
        for key, value in _result_fields(fetched, enrichment).items()
        if value is not None and value != "" and value != []
    ]
    return {
        "ticker": row.ticker,
        "ok": True,
        "source": row.source,
        "as_of": row.as_of.isoformat(),
        "records_seen": 1,
        "records_written": 1,
        "available_fields": available_fields,
        "enrichment_source": enrichment.source,
        "enrichment_notes": enrichment.metadata.get("notes", []),
        "provider_usage": dict(usage),
        **_result_fields(fetched, enrichment),
    }


def merge_snapshot_write(previous, write: FundamentalSnapshotWrite) -> FundamentalSnapshotWrite:
    if previous is None:
        return write
    values = asdict(write)
    for field in fields(FundamentalSnapshotWrite):
        key = field.name
        if key == "metadata_json":
            continue
        if values[key] is None or values[key] == "":
            values[key] = getattr(previous, key)
    metadata = {**(previous.metadata_json or {}), **(values["metadata_json"] or {})}
    metadata["data_sources"] = {
        **((previous.metadata_json or {}).get("data_sources") or {}),
        **{key: value for key, value in (metadata.get("data_sources") or {}).items() if value},
    }
    for key in ("eps_quarter_history", "annual_eps_history", "revenue_quarter_history",
                "annual_revenue_history", "roe_history"):
        old = (previous.metadata_json or {}).get(key) or []
        new = metadata.get(key) or []
        rows = {}
        for item in [*old, *new]:
            label = item.get("fiscal_period") or item.get("fiscal_year")
            if label:
                rows[label] = {**rows.get(label, {}), **{k: v for k, v in item.items() if v is not None}}
                for name, value in item.items():
                    if "growth" in name or name == "flag":
                        rows[label][name] = value
        metadata[key] = [rows[label] for label in sorted(rows, reverse=True)]
    values["metadata_json"] = metadata
    return FundamentalSnapshotWrite(**values)


def _to_write(fetched: FetchedFundamentals, enrichment: FundamentalEnrichment) -> FundamentalSnapshotWrite:
    result_fields = _result_fields(fetched, enrichment)
    return FundamentalSnapshotWrite(
        ticker=fetched.ticker,
        as_of=fetched.as_of,
        source=_combined_source(fetched.source, enrichment.source),
        fiscal_period=result_fields["fiscal_period"] or "",
        quarterly_eps_growth_pct=result_fields["quarterly_eps_growth_pct"],
        annual_eps_growth_pct=result_fields["annual_eps_growth_pct"],
        quarterly_revenue_growth_pct=result_fields["quarterly_revenue_growth_pct"],
        annual_revenue_growth_pct=result_fields["annual_revenue_growth_pct"],
        roe_pct=result_fields["roe_pct"],
        profit_margin_pct=result_fields["profit_margin_pct"],
        trailing_eps=result_fields["trailing_eps"],
        quarterly_eps_accelerating=result_fields["quarterly_eps_accelerating"],
        quarterly_revenue_accelerating=result_fields["quarterly_revenue_accelerating"],
        institutional_holders=None,
        institutional_ownership_pct=None,
        next_earnings_date=enrichment.next_earnings_date or fetched.next_earnings_date,
        beta=enrichment.beta if enrichment.beta is not None else fetched.beta,
        metadata_json={
            "provider": enrichment.source or fetched.source,
            "instrument_type": enrichment.metadata.get("instrument_type", "unknown"),
            "listing_date": enrichment.metadata.get("listing_date"),
            "statement_diagnostics": enrichment.metadata.get("statement_diagnostics", {}),
            "primary_cik": enrichment.metadata.get("primary_cik"),
            "predecessor_ciks": enrichment.metadata.get("predecessor_ciks", []),
            "sec_ciks": enrichment.metadata.get("sec_ciks", []),
            "refresh_mode": "worker",
            "enrichment": enrichment.metadata,
            "data_sources": {
                **enrichment.metadata.get("data_sources", {}),
                "beta": enrichment.metadata.get("beta_source"),
                "earnings_date": enrichment.metadata.get("earnings_date_source"),
            },
            "eps_quarter_history": result_fields["eps_quarter_history"],
            "annual_eps_history": result_fields["annual_eps_history"],
            "revenue_quarter_history": result_fields["revenue_quarter_history"],
            "annual_revenue_history": result_fields["annual_revenue_history"],
            "roe_history": result_fields["roe_history"],
        },
    )


def _result_fields(fetched: FetchedFundamentals, enrichment: FundamentalEnrichment) -> dict:
    return {
        "fiscal_period": enrichment.fiscal_period or fetched.fiscal_period,
        "quarterly_eps_growth_pct": enrichment.quarterly_eps_growth_pct
        if enrichment.quarterly_eps_growth_pct is not None
        else fetched.quarterly_eps_growth_pct,
        "annual_eps_growth_pct": enrichment.annual_eps_growth_pct
        if enrichment.annual_eps_growth_pct is not None
        else fetched.annual_eps_growth_pct,
        "quarterly_revenue_growth_pct": enrichment.quarterly_revenue_growth_pct
        if enrichment.quarterly_revenue_growth_pct is not None
        else fetched.quarterly_revenue_growth_pct,
        "annual_revenue_growth_pct": enrichment.annual_revenue_growth_pct
        if enrichment.annual_revenue_growth_pct is not None
        else fetched.annual_revenue_growth_pct,
        "roe_pct": enrichment.roe_pct if enrichment.roe_pct is not None else fetched.roe_pct,
        "profit_margin_pct": enrichment.profit_margin_pct
        if enrichment.profit_margin_pct is not None
        else fetched.profit_margin_pct,
        "trailing_eps": enrichment.trailing_eps if enrichment.trailing_eps is not None else fetched.trailing_eps,
        "quarterly_eps_accelerating": enrichment.quarterly_eps_accelerating,
        "eps_quarter_history": enrichment.eps_quarter_history,
        "annual_eps_history": enrichment.annual_eps_history,
        "quarterly_revenue_accelerating": enrichment.quarterly_revenue_accelerating,
        "revenue_quarter_history": enrichment.revenue_quarter_history,
        "annual_revenue_history": enrichment.annual_revenue_history,
        "roe_history": enrichment.roe_history,
        "institutional_holders": None,
        "institutional_ownership_pct": None,
        "next_earnings_date": (
            enrichment.next_earnings_date.isoformat()
            if enrichment.next_earnings_date
            else fetched.next_earnings_date.isoformat()
            if fetched.next_earnings_date
            else None
        ),
        "beta": enrichment.beta if enrichment.beta is not None else fetched.beta,
    }


def _combined_source(base: str, enrichment_source: str) -> str:
    parts = [part for part in [base, enrichment_source] if part]
    return "+".join(dict.fromkeys(parts)) or base or "worker"
