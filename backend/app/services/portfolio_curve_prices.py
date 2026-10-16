"""Maintain curve inputs inside the existing market refresh, without request-time I/O."""
from collections import defaultdict
from datetime import date, datetime, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo

import requests

from app.data_sources.issuer_prices import parse_issuer_history
from app.data_sources.issuer_product import sg_final_bid, vontobel_redemption
from app.repositories import portfolio, prices
from app.services.prices import PriceRefreshSymbol, refresh_price_cache_for_symbols


def curve_price_requirements(transactions, today: date) -> tuple[dict[str, date], set[str]]:
    # Replay the full ledger, including positions bought in earlier years.
    from app.services.portfolio import _stored_transaction_sort_key, _signed_share_delta, yahoo_quote_currency
    from app.domain.portfolio.trade_republic import normalize_transaction_type, SHARE_DECREASE_TYPES
    start = date(today.year, 1, 1)
    balances = defaultdict(float)
    symbols: dict[str, date] = {"EURUSD=X": today, "^GSPC": today, "SPY": today}
    issuers = set()
    for row in sorted(transactions, key=_stored_transaction_sort_key):
        if row.date > today:
            continue
        key = row.isin or row.ticker
        previous = balances[key]
        typ = normalize_transaction_type(row.transaction_type)
        if typ == "split":
            balances[key] += float((row.raw_json or {}).get("shares", row.shares) or 0)
        elif typ in SHARE_DECREASE_TYPES and not row.shares and row.asset_class.upper() == "DERIVATIVE":
            balances[key] = 0
        else:
            balances[key] += _signed_share_delta(typ, row.shares)
        if row.date >= start and (previous > 1e-9 or balances[key] > 1e-9):
            if row.asset_class.upper() == "DERIVATIVE" and row.isin:
                issuers.add(row.isin)
            elif row.ticker:
                symbols[row.ticker] = max(symbols.get(row.ticker, start), row.date)
        if row.currency and row.currency.upper() != "USD":
            symbols[f"{row.currency.upper()}USD=X"] = today
    for row in transactions:
        key = row.isin or row.ticker
        if balances[key] > 1e-9:
            if row.asset_class.upper() == "DERIVATIVE" and row.isin:
                issuers.add(row.isin)
            elif row.ticker:
                symbols[row.ticker] = today
    for ticker in list(symbols):
        if ticker.endswith("=X"):
            continue
        currency = yahoo_quote_currency(ticker)
        if currency != "USD":
            symbols[f"{currency}USD=X"] = today
    return symbols, issuers


def refresh_portfolio_curve_prices() -> dict:
    """Failures stay explicit; no guessed quotes and no additional scheduled job."""
    result = {"ok": True, "listed": [], "issuers": [], "errors": []}
    try:
        today = datetime.now(ZoneInfo("Europe/Berlin")).date()
        symbols, issuers = curve_price_requirements(portfolio.list_trade_republic_transactions(), today)
        start = date(today.year, 1, 1) - timedelta(days=10)
        cache = prices.list_price_bars_for_tickers(symbols, start_date=start)
        required = []
        for ticker, last_needed in symbols.items():
            bars = cache.get(ticker, [])
            if last_needed < today and bars and max(bar.date for bar in bars) >= last_needed:
                continue
            required.append(PriceRefreshSymbol(ticker=ticker))
        if required:
            # Full current-year coverage also refreshes Yahoo's split-adjusted
            # history as a consistent vintage. This is a small portfolio batch.
            result["listed"] = refresh_price_cache_for_symbols(required, range_key="1y", incremental=False,
                timeout=20, batch_size=25)
        if issuers:
            _refresh_issuers(sorted(issuers), today, result)
        result["ok"] = not result["errors"] and all(item.get("ok") for item in result["listed"])
    except Exception as exc:
        result["ok"] = False
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def _refresh_issuers(isins: list[str], today: date, result: dict) -> None:
    # The ordinary issuer website exposes its chart to a browser. No stealth,
    # proxy, CAPTCHA handling or access-control bypass is used.
    from playwright.sync_api import sync_playwright
    metadata = prices.list_instrument_metadata(isins)
    with sync_playwright() as runtime:
        browser = None
        try:
            for isin in isins:
                if metadata.get(isin, {}).get("fixed_redemption"):
                    continue
                source = metadata.get(isin, {}).get("issuer_history_source", "")
                try:
                    final_bid = None
                    if isin.startswith(("DE000V", "DE000BD")) or "vontobel" in source:
                        if browser is None:
                            browser = runtime.chromium.launch(headless=True)
                        page = browser.new_page()
                        page.set_default_timeout(25000)
                        try:
                            page.goto(f"https://markets.vontobel.com/de-de/produkte/hebel/faktor-optionsscheine/{isin}", wait_until="domcontentloaded")
                            data = page.locator("#__NEXT_DATA__").evaluate("el => JSON.parse(el.textContent).props.pageProps.additionalData")
                            redemption = vontobel_redemption(isin, data)
                            response = page.evaluate("""async isin => {
                                const r = await fetch('/api/v1/charts/products/' + isin + '/detail/5?c=de-de');
                                if (!r.ok) throw new Error('Issuer history HTTP ' + r.status);
                                return await r.json();
                            }""", isin)
                        finally:
                            page.close()
                    elif isin.startswith(("DE000FD", "DE000FE", "DE000S")) or "societe_generale" in source:
                        response = requests.get("https://www.sg-zertifikate.de/EmcWebApi/api/Products", params={"code": isin[5:11]}, timeout=20)
                        response.raise_for_status()
                        product = response.json()
                        response = requests.get("https://www.sg-zertifikate.de/EmcWebApi/api/Prices/History", params={"productId": product["Id"]}, timeout=20)
                        response.raise_for_status()
                        response = {"product": product, "history": response.json()}
                        properties = requests.get(f"https://www.sg-zertifikate.de/EmcWebApi/api/Products/AllProperties/{product['Id']}", timeout=20)
                        properties.raise_for_status()
                        final_bid = sg_final_bid(product, properties.json(), now=datetime.now(ZoneInfo("Europe/Berlin")))
                        redemption = None
                    else:
                        raise ValueError("No verified issuer history source is configured")
                    source, bars = parse_issuer_history(isin, response, today=today)
                    if final_bid and final_bid.date <= today and (not bars or final_bid.date > bars[-1].date):
                        bars.append(final_bid)
                    count = prices.upsert_price_bars(isin, bars, source=source)
                    evidence = {"issuer_history_source": source,
                        "issuer_history_sha256": hashlib.sha256(json.dumps(response, sort_keys=True).encode()).hexdigest(),
                        "issuer_checked_at": datetime.now(ZoneInfo("Europe/Berlin")).isoformat()}
                    if final_bid:
                        evidence["issuer_final_bid"] = {"date": final_bid.date.isoformat(), "bid": final_bid.close,
                            "timestamp": next(row["Value"] for row in properties.json() if row.get("Name") == "TimeStamp"),
                            "source_url": properties.url}
                    if redemption:
                        evidence["fixed_redemption"] = redemption
                    prices.save_instrument_metadata(isin, evidence)
                    result["issuers"].append({"isin": isin, "records_written": count, "source": source})
                except Exception as exc:
                    result["errors"].append(f"{isin}: {type(exc).__name__}: {exc}")
        finally:
            if browser:
                browser.close()
