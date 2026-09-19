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


def assess_historical_sale(db, event):
    metadata = {"method": "Bestehende Sell-Engine, heutige Standardregeln auf historischen Daten",
                "trade_date": event["date"], "cutoff": "Nur Schlusskurse vor dem Verkaufstag; keine damaligen Intraday-Daten"}
    allocations = event["allocations"]
    if event["unallocated"] or not allocations or any(a["cost_basis"] is None for a in allocations):
        return {**metadata, "status": "missing", "message": "Keine vollständige Kaufzuordnung / Einstandsbasis vorhanden."}
    try:
        end = date.fromisoformat(event["date"])
        start = min(date.fromisoformat(a["buy_date"]) for a in allocations) - timedelta(days=550)
        def frame(ticker):
            bars = list(db.scalars(select(PriceBar).join(Instrument, PriceBar.instrument_id == Instrument.id)
                .where(Instrument.ticker == ticker, PriceBar.date >= start, PriceBar.date < end)
                .order_by(PriceBar.date)))
            return pd.DataFrame([{"Date": b.date, "Open": b.open, "High": b.high, "Low": b.low,
                                  "Close": b.close, "Volume": b.volume} for b in bars]).set_index("Date") if bars else pd.DataFrame()
        prices, benchmark = frame(event["ticker"]), frame("SPY")
        if len(prices) < 200 or len(benchmark) < 200:
            return {**metadata, "status": "missing", "message": "Weniger als 200 historische Kurs-/Benchmark-Tage gespeichert."}
        quote_currency = yahoo_quote_currency(event["ticker"])
        buy_price = sum(a["cost_basis"] for a in allocations) / event["shares"]
        if quote_currency != event["currency"]:
            # Use historical per-day FX for OHLC; conversion must not use a current rate.
            def fx_series(currency):
                if currency == "USD":
                    return pd.Series(1.0, index=prices.index)
                fx = frame(f"{currency}USD=X")
                if fx.empty:
                    raise ValueError("Historische FX-Kurse fehlen")
                series = fx.Close.reindex(prices.index)
                if series.isna().any() or (series <= 0).any():
                    raise ValueError("Historische FX-Reihe unvollständig")
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
    except Exception as exc:
        logger.warning("Historical sell assessment unavailable for %s: %s", event["ticker"], type(exc).__name__)
        return {**metadata, "status": "missing", "message": "Historische Daten oder Währungsumrechnung nicht vollständig verfügbar."}
