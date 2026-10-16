"""Import verified issuer histories and refresh listed instruments used by the TR ledger.

python -m app.services.repair_portfolio_curve_prices --issuer-dir /private/histories --refresh-listed
Only price-cache and instrument metadata are updated; broker financial rows are never written.
"""
import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from app.data_sources.issuer_prices import parse_issuer_history
from app.db.models import Instrument
from app.db.session import SessionLocal
from app.repositories import portfolio, prices
from app.services.fx import yahoo_quote_currency
from app.services.prices import PriceRefreshSymbol, refresh_price_cache_for_symbols


def repair(*, issuer_dir: Path | None = None, refresh_listed: bool = False) -> dict:
    imported = []
    if issuer_dir:
        pending = []
        for path in sorted(issuer_dir.glob("issuer-history-*.json")):
            isin = path.stem.removeprefix("issuer-history-").upper()
            if len(isin) != 12 or not isin.isalnum():
                raise ValueError("Invalid issuer-history filename")
            raw = path.read_bytes()
            source, bars = parse_issuer_history(isin, json.loads(raw))
            pending.append((isin, source, bars, hashlib.sha256(raw).hexdigest()))
        # Validate the entire batch before any observations are written.
        for isin, source, bars, digest in pending:
            written = prices.upsert_price_bars(isin, bars, source=source)
            with SessionLocal() as db:
                instrument = db.scalars(select(Instrument).where(Instrument.ticker == isin)).first()
                if instrument is not None:
                    instrument.isin, instrument.currency, instrument.asset_class = isin, "EUR", "derivative"
                    instrument.metadata_json = {**(instrument.metadata_json or {}), "issuer_history_sha256": digest, "issuer_history_source": source}
                    db.commit()
            imported.append({"isin": isin, "source": source, "written": written})
    refresh = []
    if refresh_listed:
        transactions = portfolio.list_trade_republic_transactions()
        symbols = {row.ticker for row in transactions if row.ticker}
        currencies = {row.currency.upper() for row in transactions}
        currencies.update(yahoo_quote_currency(symbol) for symbol in symbols)
        symbols.update(f"{currency}USD=X" for currency in currencies if currency != "USD")
        symbols.update({"^GSPC", "SPY"})
        refresh = refresh_price_cache_for_symbols([PriceRefreshSymbol(ticker=symbol) for symbol in sorted(symbols)], range_key="1y", incremental=False, timeout=20)
    return {"issuer_histories": imported, "listed_refresh": refresh}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer-dir", type=Path)
    parser.add_argument("--refresh-listed", action="store_true")
    args = parser.parse_args()
    print(json.dumps(repair(issuer_dir=args.issuer_dir, refresh_listed=args.refresh_listed)), flush=True)
