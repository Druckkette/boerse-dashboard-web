"""Export the latest journal sells and necessary immutable executions privately.

Run inside the NAS backend, redirect stdout to a protected local file. Journal
notes, questionnaires, credentials and unrelated portfolio positions are omitted.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import sys

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.fx import yahoo_quote_currency
from app.services.market_calendar import completed_us_market_session
from app.services.settings import get_app_settings


def export(limit=20):
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    cutoff = completed_us_market_session().date
    with SessionLocal() as db:
        db.execute(text("SET statement_timeout='60000'"))
        sales = [dict(row) for row in db.execute(text("""
            select j.id,j.ticker,j.trade_date,j.price,j.shares,j.currency,j.realized_pnl,
                   j.portfolio_snapshot_json,t.raw_json->>'event_ts' as execution_at,
                   t.fees as execution_fees,t.tax as execution_tax
            from trade_journal_entries j left join transactions t on t.id=j.source_transaction_id
            where j.entry_type='sell'
            order by j.trade_date desc,nullif(t.raw_json->>'event_ts','') desc nulls last,
                     j.created_at desc,j.id desc limit :limit
        """), {"limit": limit}).mappings()]
        # Keep just the immutable FIFO data needed by the replay.
        for sale in sales:
            snapshot = sale["portfolio_snapshot_json"] or {}
            sale["portfolio_snapshot_json"] = {key: snapshot.get(key) for key in ["fees", "tax", "allocations", "unallocated_shares"]}
        ids = sorted({a["buy_transaction_id"] for sale in sales for a in sale["portfolio_snapshot_json"].get("allocations") or []})
        buys = [dict(row) for row in db.execute(text("""
            select id,ticker,date,shares,price,currency,fees,tax,raw_json->>'event_ts' as execution_at
            from transactions where id=any(:ids)
        """), {"ids": ids}).mappings()]
        start = min((b["date"] for b in buys), default=cutoff) - timedelta(days=600)
        currencies = {sale["currency"] for sale in sales} | {yahoo_quote_currency(sale["ticker"]) for sale in sales}
        tickers = sorted({sale["ticker"] for sale in sales} | {"SPY"} | {f"{c}USD=X" for c in currencies if c != "USD"})
        prices = []
        for ticker in tickers:
            rows = db.execute(text("""
                select distinct on (b.date) b.date,b.open,b.high,b.low,b.close,b.volume,b.source,b.fetched_at
                from price_bars b join instruments i on i.id=b.instrument_id
                where i.ticker=:ticker and b.date>=:start and b.date<=:cutoff
                order by b.date,b.fetched_at desc nulls last,b.source,b.id
            """), {"ticker": ticker, "start": start, "cutoff": cutoff}).mappings()
            batch = [{"ticker": ticker, **dict(row)} for row in rows]
            prices.extend(batch)
            print(f"{ticker}: {len(batch)} saved bars", file=sys.stderr)
    return {"cutoff": cutoff, "exported_at": datetime.now(timezone.utc), "sales": sales, "buys": buys,
            "prices": prices, "sell_setup": get_app_settings().sell_rule_setup}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(export(args.limit), default=str))


if __name__ == "__main__":
    main()
