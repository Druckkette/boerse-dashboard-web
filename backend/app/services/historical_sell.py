"""Reuse the sell engine on pre-sale data, never today's portfolio or manual inputs."""
from datetime import date, timedelta
import logging

import pandas as pd
from sqlalchemy import select
from app.db.models import Instrument, PriceBar
from app.domain.sell.metrics import build_sell_decision_metrics_payload
from app.domain.sell.rules import evaluate_sell_decision
from app.services.fx import yahoo_quote_currency
from app.domain.sell.service import _json_safe

logger = logging.getLogger(__name__)
ASSESSMENT_VERSION = 2
FX_MAX_AGE_DAYS = 4


class HistoricalDataMissing(ValueError):
    pass


def align_historical_fx(fx, dates, currency):
    """Only prior real quotes, bounded across weekends/holidays; never backfill from future."""
    target = pd.DatetimeIndex(pd.to_datetime(dates))
    quotes = pd.Series(pd.to_numeric(fx.Close, errors="coerce").to_numpy(),
                       index=pd.to_datetime(fx.index)).sort_index()
    quotes = quotes[~quotes.index.duplicated(keep="last")]
    quotes = quotes.where((quotes > 0) & (quotes < float("inf"))).dropna()
    indexer = quotes.index.get_indexer(target, method="pad", tolerance=pd.Timedelta(days=FX_MAX_AGE_DAYS))
    if (indexer < 0).any():
        missing = target[indexer < 0]
        raise HistoricalDataMissing(f"{currency}: kein vorheriger FX-Kurs innerhalb von {FX_MAX_AGE_DAYS} Tagen "
                                    f"für {len(missing)} Kurstage (erster: {missing[0].date()}).")
    used = quotes.index[indexer]
    carried = [{"date": day.date().isoformat(), "quote_date": source.date().isoformat()}
               for day, source in zip(target, used) if day != source]
    return pd.Series(quotes.iloc[indexer].to_numpy(), index=dates), carried



def assess_historical_sale(db, event):
    metadata = {"assessment_version": ASSESSMENT_VERSION, "method": "Bestehende Sell-Engine, heutige Standardregeln auf historischen Daten",
                "trade_date": event["date"], "cutoff": "Nur Schlusskurse vor dem Verkaufstag; keine damaligen Intraday-Daten"}
    allocations = event["allocations"]
    if event["unallocated"] or not allocations or any(a["cost_basis"] is None for a in allocations):
        return {**metadata, "status": "missing", "message": "Keine vollständige Kaufzuordnung / Einstandsbasis vorhanden."}
    try:
        end = date.fromisoformat(event["date"])
        start = min(date.fromisoformat(a["buy_date"]) for a in allocations) - timedelta(days=550)
        def frame(ticker, extra_days=0):
            bars = list(db.scalars(select(PriceBar).join(Instrument, PriceBar.instrument_id == Instrument.id)
                .where(Instrument.ticker == ticker, PriceBar.date >= start - timedelta(days=extra_days), PriceBar.date < end)
                .order_by(PriceBar.date)))
            return pd.DataFrame([{"Date": b.date, "Open": b.open, "High": b.high, "Low": b.low,
                                  "Close": b.close, "Volume": b.volume} for b in bars]).set_index("Date") if bars else pd.DataFrame()
        prices, benchmark = frame(event["ticker"]), frame("SPY")
        if len(prices) < 200 or len(benchmark) < 200:
            return {**metadata, "status": "missing", "message": "Weniger als 200 historische Kurs-/Benchmark-Tage gespeichert."}
        quote_currency = yahoo_quote_currency(event["ticker"])
        buy_price = sum(a["cost_basis"] for a in allocations) / event["shares"]
        if quote_currency != event["currency"]:
            metadata["fx_policy"] = f"Letzter gespeicherter Kurs am oder vor dem Kurstag, höchstens {FX_MAX_AGE_DAYS} Kalendertage alt."
            metadata["fx_carried_quotes"] = {}
            # Historical as-of alignment accommodates different exchange/FX holidays.
            def fx_series(currency):
                if currency == "USD":
                    return pd.Series(1.0, index=prices.index)
                fx = frame(f"{currency}USD=X", extra_days=FX_MAX_AGE_DAYS)
                if fx.empty:
                    raise HistoricalDataMissing(f"{currency}: historische FX-Kurse fehlen.")
                series, carried = align_historical_fx(fx, prices.index, currency)
                if carried:
                    metadata["fx_carried_quotes"][currency] = carried
                return series
            ratio = fx_series(quote_currency) / fx_series(event["currency"])
            for column in ("Open", "High", "Low", "Close"):
                prices[column] *= ratio
        payload = build_sell_decision_metrics_payload(ticker=event["ticker"],
            buy_date=min(a["buy_date"] for a in allocations), buy_price=buy_price, shares=event["shares"],
            price_frame=prices, benchmark_frame=benchmark, currency=event["currency"])
        if payload.get("error") or payload.get("ok") is False:
            return {**metadata, "status": "missing", "message": "Historische Bewertungsdaten unvollständig."}
        evaluation = evaluate_sell_decision(payload)
        return {**metadata, "status": "available", "as_of": str(prices.index[-1]), "evaluation": _json_safe(evaluation)}
    except HistoricalDataMissing as exc:
        logger.info("Historical sell data missing for %s: %s", event["ticker"], exc)
        return {**metadata, "status": "missing", "reason_code": "historical_fx_missing", "message": str(exc)}
    except Exception as exc:
        logger.exception("Historical sell assessment unavailable for %s: %s", event["ticker"], type(exc).__name__)
        return {**metadata, "status": "missing", "reason_code": "assessment_error", "message": "Historische Bewertung fehlgeschlagen; Details stehen im Serverprotokoll."}
