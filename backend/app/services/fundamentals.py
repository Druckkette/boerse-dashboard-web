from __future__ import annotations

from app.core_config import get_settings
from app.data_sources.fundamentals_client import FundamentalEnrichment, fetch_fundamental_enrichment
from app.data_sources.yfinance_client import FetchedFundamentals, fetch_fundamentals
from app.repositories.fundamentals import FundamentalSnapshotWrite, upsert_fundamentals
from app.services.settings import get_runtime_config_value


def refresh_fundamentals_for_ticker(ticker: str, *, include_holders: bool = True) -> dict:
    clean = ticker.strip().upper()
    if not clean:
        raise ValueError("ticker must not be empty")

    fetched = fetch_fundamentals(clean, include_holders=include_holders)
    settings = get_settings()
    enrichment = fetch_fundamental_enrichment(
        clean,
        fmp_api_key=get_runtime_config_value("FMP_API_KEY") or settings.fmp_api_key,
        sec_user_agent=get_runtime_config_value("SEC_USER_AGENT") or settings.sec_user_agent,
    )
    row = upsert_fundamentals(_to_write(fetched, enrichment))
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
        **_result_fields(fetched, enrichment),
    }


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
        institutional_holders=fetched.institutional_holders,
        institutional_ownership_pct=fetched.institutional_ownership_pct,
        next_earnings_date=enrichment.next_earnings_date or fetched.next_earnings_date,
        beta=enrichment.beta if enrichment.beta is not None else fetched.beta,
        metadata_json={
            "provider": "yfinance",
            "refresh_mode": "worker",
            "enrichment": enrichment.metadata,
            "eps_quarter_history": result_fields["eps_quarter_history"],
            "annual_eps_history": result_fields["annual_eps_history"],
            "revenue_quarter_history": result_fields["revenue_quarter_history"],
            "annual_revenue_history": result_fields["annual_revenue_history"],
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
        "institutional_holders": fetched.institutional_holders,
        "institutional_ownership_pct": fetched.institutional_ownership_pct,
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
