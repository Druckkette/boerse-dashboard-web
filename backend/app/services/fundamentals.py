from __future__ import annotations

from app.data_sources.yfinance_client import FetchedFundamentals, fetch_fundamentals
from app.repositories.fundamentals import FundamentalSnapshotWrite, upsert_fundamentals


def refresh_fundamentals_for_ticker(ticker: str, *, include_holders: bool = True) -> dict:
    clean = ticker.strip().upper()
    if not clean:
        raise ValueError("ticker must not be empty")

    fetched = fetch_fundamentals(clean, include_holders=include_holders)
    row = upsert_fundamentals(_to_write(fetched))
    available_fields = [
        key
        for key, value in _result_fields(fetched).items()
        if value is not None and value != ""
    ]
    return {
        "ticker": row.ticker,
        "ok": True,
        "source": row.source,
        "as_of": row.as_of.isoformat(),
        "records_seen": 1,
        "records_written": 1,
        "available_fields": available_fields,
        **_result_fields(fetched),
    }


def _to_write(fetched: FetchedFundamentals) -> FundamentalSnapshotWrite:
    return FundamentalSnapshotWrite(
        ticker=fetched.ticker,
        as_of=fetched.as_of,
        source=fetched.source,
        fiscal_period=fetched.fiscal_period,
        quarterly_eps_growth_pct=fetched.quarterly_eps_growth_pct,
        annual_eps_growth_pct=fetched.annual_eps_growth_pct,
        quarterly_revenue_growth_pct=fetched.quarterly_revenue_growth_pct,
        annual_revenue_growth_pct=fetched.annual_revenue_growth_pct,
        roe_pct=fetched.roe_pct,
        profit_margin_pct=fetched.profit_margin_pct,
        trailing_eps=fetched.trailing_eps,
        quarterly_eps_accelerating=None,
        quarterly_revenue_accelerating=None,
        institutional_holders=fetched.institutional_holders,
        institutional_ownership_pct=fetched.institutional_ownership_pct,
        next_earnings_date=fetched.next_earnings_date,
        beta=fetched.beta,
        metadata_json={"provider": "yfinance", "refresh_mode": "worker"},
    )


def _result_fields(fetched: FetchedFundamentals) -> dict:
    return {
        "fiscal_period": fetched.fiscal_period,
        "quarterly_eps_growth_pct": fetched.quarterly_eps_growth_pct,
        "annual_eps_growth_pct": fetched.annual_eps_growth_pct,
        "quarterly_revenue_growth_pct": fetched.quarterly_revenue_growth_pct,
        "annual_revenue_growth_pct": fetched.annual_revenue_growth_pct,
        "roe_pct": fetched.roe_pct,
        "profit_margin_pct": fetched.profit_margin_pct,
        "trailing_eps": fetched.trailing_eps,
        "institutional_holders": fetched.institutional_holders,
        "institutional_ownership_pct": fetched.institutional_ownership_pct,
        "next_earnings_date": fetched.next_earnings_date.isoformat() if fetched.next_earnings_date else None,
        "beta": fetched.beta,
    }
