"""Private journal counterfactuals; input/output must never be published to GitHub.

Selected acquisition shares are pooled only after their actual purchase time.
Independent lots are an optional sensitivity check. Neither model reallocates cash.
Signals use production rules and confirmation state, executed at the next open.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import sys

import pandas as pd

from app.domain.sell.metrics import build_sell_decision_metrics_payload
from app.domain.sell import rules
from app.research.stock_backtest import STRATEGIES, native_exit, prepare_features, price_frames
from app.services.fx import yahoo_quote_currency
from app.services.historical_sell import HistoricalDataMissing
from app.services.market_calendar import _ticker_calendar


def utc(value):
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


@lru_cache(maxsize=16384)
def session_times(ticker: str, day: pd.Timestamp):
    calendar = _ticker_calendar(ticker)
    if not calendar.is_session(day):
        raise HistoricalDataMissing(f"{ticker}: gespeicherter Kurs an Nicht-Handelstag {day.date()}")
    return calendar.session_open(day), calendar.session_close(day)


def currency_factors(frames, ticker, currency, dates):
    """Use strictly earlier daily FX closes, including for next-morning fills."""
    def rate(code):
        if code == "USD":
            return pd.Series(1., index=dates)
        pair = f"{code}USD=X"
        if pair not in frames:
            raise HistoricalDataMissing(f"{pair}: historische FX-Daten fehlen")
        quotes = frames[pair]["Close"].where(lambda s: (s > 0) & (s < float("inf"))).dropna()
        indexer = quotes.index.get_indexer(dates - pd.Timedelta(days=1), method="pad", tolerance=pd.Timedelta(days=3))
        if (indexer < 0).any():
            raise HistoricalDataMissing(f"{pair}: vorheriger FX-Schlusskurs fehlt oder ist älter als vier Kalendertage")
        return pd.Series(quotes.iloc[indexer].to_numpy(), index=dates)
    return rate(yahoo_quote_currency(ticker)) / rate(currency)


def replay_lot(frame, spy, ticker, buy, setup, factors, end):
    """Return unit-share fills for every strategy, without tax or order fees."""
    entry = pd.Timestamp(buy["date"])
    if not buy.get("execution_at"):
        raise HistoricalDataMissing("Ausführungszeit des Kaufs fehlt")
    if not math.isfinite(float(buy["price"] or 0)) or buy["price"] <= 0:
        raise HistoricalDataMissing("Kaufpreis fehlt")
    if (frame.index < entry).sum() < 200:
        raise HistoricalDataMissing("Weniger als 200 echte Kurstage vor dem Kauf; kein vollständiger Acht-Strategien-Vergleich")
    dates = frame.index[(frame.index >= entry) & (frame.index <= end)]
    expected = _ticker_calendar(ticker).sessions_in_range(entry, end)
    if not len(dates) or len(expected.difference(dates)):
        raise HistoricalDataMissing(f"{ticker}: Kurslücke im Haltezeitraum")
    bought_at = utc(buy["execution_at"])
    states = {key: {"sold": 0., "state": {}, "pending": None, "fills": []} for key in STRATEGIES}
    for day in dates:
        opened, closed = session_times(ticker, day)
        live = []
        for key, account in states.items():
            pending = account["pending"]
            if pending:
                if opened <= bought_at:
                    raise HistoricalDataMissing("Modellverkauf vor dem tatsächlichen Kauf")
                pct = min(pending["pct"], 100 - account["sold"])
                account["sold"] += pct
                account["fills"].append({"signal_date": pending["signal_date"],
                    "fill_date": str(day.date()), "fill_at": opened.isoformat(), "pct": pct,
                    "price": float(frame.loc[day, "Open"] * factors.loc[day])})
                account["pending"] = None
            if account["sold"] < 100:
                live.append(key)
        if not live or closed <= bought_at or day == dates[-1]:
            continue
        # Match the app's constant conversion of the whole price frame, using only
        # the FX rate available then. Keep native listing trends and EUR cost basis.
        history = frame.loc[:day].copy()
        history[["Open", "High", "Low", "Close"]] *= factors.loc[day]
        # A Hong Kong / European close must not see that day's later US close.
        available = [d for d in spy.index if session_times("SPY", d)[1] <= closed]
        benchmark = spy.loc[available]
        if len(benchmark) < 200:
            raise HistoricalDataMissing("Benchmark-Historie vor Signal unvollständig")
        common = history.index.intersection(benchmark.index)
        payload = build_sell_decision_metrics_payload(ticker=ticker, buy_date=entry,
            buy_price=float(buy["price"]), shares=1., price_frame=history,
            benchmark_frame=benchmark, currency=buy["currency"], rs_completed_through=common[-1])
        if not payload.get("ok"):
            raise HistoricalDataMissing(str(payload.get("error", "Bewertung nicht verfügbar")))
        if not payload.get("metrics", {}).get("rs_data_complete"):
            raise HistoricalDataMissing("RS-Benchmark-Historie am Signalzeitpunkt unvollständig")
        features = prepare_features(payload, setup)
        for key in live:
            account = states[key]
            decision = native_exit(payload, features, {**setup, "strategy_key": key}, account["sold"], account["state"])
            account["state"] = decision["state"]
            if decision["pct"]:
                account["pending"] = {"pct": decision["pct"], "signal_date": str(day.date())}
    return {key: account["fills"] for key, account in states.items()}


def replay_position(frame, spy, ticker, acquisitions, setup, factors, end):
    """Pool only the selected sold shares, respecting purchase/add execution times.

    Proportional tranches refer to acquisitions in the current holding cycle.
    Native cumulative targets are converted into exact quantities; FIFO determines
    the entry basis of the remaining position. A new buy after a full exit starts
    a fresh cycle. Original purchases still occur, without reinvesting exit cash.
    """
    acquisitions = sorted(acquisitions, key=lambda a: utc(a["buy"]["execution_at"]))
    first = pd.Timestamp(acquisitions[0]["buy"]["date"])
    total = sum(a["shares"] for a in acquisitions)
    if (frame.index < first).sum() < 200:
        raise HistoricalDataMissing("Weniger als 200 echte Kurstage vor dem Kauf; kein vollständiger Acht-Strategien-Vergleich")
    dates = frame.index[(frame.index >= first) & (frame.index <= end)]
    if len(_ticker_calendar(ticker).sessions_in_range(first, end).difference(dates)):
        raise HistoricalDataMissing(f"{ticker}: Kurslücke im Haltezeitraum")
    states = {key: {"lots": [], "added": 0., "sold": 0., "next_buy": 0,
                    "state": {}, "pending": None, "fills": []} for key in STRATEGIES}

    def add_buys(account, as_of):
        while account["next_buy"] < len(acquisitions):
            acquisition = acquisitions[account["next_buy"]]
            if utc(acquisition["buy"]["execution_at"]) > as_of:
                break
            if not account["lots"]:
                account.update(added=0., sold=0., state={}, pending=None)
            account["added"] += acquisition["shares"]
            account["lots"].append({"remaining": acquisition["shares"], **acquisition["buy"]})
            account["next_buy"] += 1

    for day in dates:
        opened, closed = session_times(ticker, day)
        history = None
        benchmark = spy.loc[[d for d in spy.index if session_times("SPY", d)[1] <= closed]]
        prepared = {}
        for key, account in states.items():
            add_buys(account, opened)
            pending = account["pending"]
            if pending:
                quantity = min(pending["shares"], sum(lot["remaining"] for lot in account["lots"]))
                left = quantity
                for lot in account["lots"]:
                    consumed = min(left, lot["remaining"])
                    lot["remaining"] -= consumed
                    left -= consumed
                account["lots"] = [lot for lot in account["lots"] if lot["remaining"] > 1e-8]
                account["sold"] += quantity
                account["fills"].append({"signal_date": pending["signal_date"], "fill_date": str(day.date()),
                    "fill_at": opened.isoformat(), "pct": quantity / total * 100.,
                    "price": float(frame.loc[day, "Open"] * factors.loc[day])})
                account["pending"] = None
            add_buys(account, closed)
            if not account["lots"] or day == dates[-1]:
                continue
            quantity = sum(lot["remaining"] for lot in account["lots"])
            average = sum(lot["price"] * lot["remaining"] for lot in account["lots"]) / quantity
            entry = min(lot["date"] for lot in account["lots"])
            signature = (entry, round(average, 10))
            if signature not in prepared:
                if history is None:
                    history = frame.loc[:day].copy()
                    history[["Open", "High", "Low", "Close"]] *= factors.loc[day]
                if len(benchmark) < 200:
                    raise HistoricalDataMissing("Benchmark-Historie vor Signal unvollständig")
                common = history.index.intersection(benchmark.index)
                payload = build_sell_decision_metrics_payload(ticker=ticker, buy_date=entry, buy_price=average,
                    shares=1., price_frame=history, benchmark_frame=benchmark,
                    currency=acquisitions[0]["buy"]["currency"], rs_completed_through=common[-1])
                if not payload.get("ok"):
                    raise HistoricalDataMissing(str(payload.get("error", "Bewertung nicht verfügbar")))
                if not payload.get("metrics", {}).get("rs_data_complete"):
                    raise HistoricalDataMissing("RS-Benchmark-Historie am Signalzeitpunkt unvollständig")
                prepared[signature] = (payload, prepare_features(payload, setup))
            payload, features = prepared[signature]
            decision = native_exit(payload, features, {**setup, "strategy_key": key},
                                   100. * account["sold"] / account["added"], account["state"])
            account["state"] = decision["state"]
            if decision["pct"]:
                quantity = min(quantity, max(0., decision["target_pct"] / 100. * account["added"] - account["sold"]))
                account["pending"] = {"shares": quantity, "signal_date": str(day.date())}
    return {key: account["fills"] for key, account in states.items()}


def sale_value(sale, lot_results, key, end_at, terminal_price):
    """Aggregate disjoint allocated shares; one modeled broker order per date."""
    cash, remaining = 0., 0.
    order_dates = set()
    fills = []
    for allocation, result in lot_results:
        quantity = float(allocation["shares"])
        sold = 0.
        for fill in result[key]:
            if utc(fill["fill_at"]) > end_at:
                continue
            part = quantity * fill["pct"] / 100
            sold += part
            cash += part * fill["price"]
            order_dates.add(fill["fill_date"])
            fills.append({**fill, "shares": part, "buy_transaction_id": allocation["buy_transaction_id"]})
        if sold > quantity + 1e-8:
            raise ValueError("Verkaufte Stückzahl übersteigt Kaufzuordnung")
        remaining += max(0., quantity - sold)
    return cash + remaining * terminal_price, remaining, order_dates, fills


def run(data, *, progress=None, lot_wise=False):
    frames = price_frames(data)
    # A shared valuation date avoids silently comparing a stale ETF with a newer stock.
    selected = {s["ticker"] for s in data["sales"]}
    end = min(pd.Timestamp(data["cutoff"]), *(frames[t].index[-1] for t in selected if t in frames))
    buys = {b["id"]: b for b in data["buys"]}
    setup = rules.normalize_sell_setup_payload(data["sell_setup"], migrate_legacy=False)
    cache, reserved, exclusions, rows = {}, {}, [], []
    for number, sale in enumerate(data["sales"], 1):
        if progress:
            progress(f"{number}/{len(data['sales'])}: {sale['ticker']}")
        try:
            if sale["currency"] != "EUR":
                raise HistoricalDataMissing("Summenvergleich unterstützt derzeit nur EUR-Ausführungen")
            if any(not math.isfinite(float(sale.get(k) or 0)) or float(sale.get(k) or 0) <= 0 for k in ["price", "shares"]):
                raise HistoricalDataMissing("Verkaufspreis oder Stückzahl fehlt")
            portfolio = sale["portfolio_snapshot_json"]
            allocations = portfolio.get("allocations", [])
            if portfolio.get("unallocated_shares") or not allocations or any(a["cost_basis"] is None for a in allocations):
                raise HistoricalDataMissing("Kaufzuordnung / Einstandsbasis unvollständig")
            if any(not math.isfinite(float(a[k])) or float(a[k]) <= 0 for a in allocations for k in ["shares", "cost_basis"]):
                raise HistoricalDataMissing("Ungültige FIFO-Stückzahl oder Einstandsbasis")
            if abs(sum(a["shares"] for a in allocations) - sale["shares"]) > 1e-6:
                raise HistoricalDataMissing("FIFO-Stückzahl stimmt nicht mit Verkauf überein")
            if not sale.get("execution_at"):
                raise HistoricalDataMissing("Ausführungszeit des Verkaufs fehlt")
            frame = frames.get(sale["ticker"])
            if frame is None:
                raise HistoricalDataMissing("Historische Kurse fehlen")
            first_buy = min(pd.Timestamp(a["buy_date"]) for a in allocations)
            factor_dates = frame.index[(frame.index >= first_buy) & (frame.index <= end)]
            factors = currency_factors(frames, sale["ticker"], sale["currency"], factor_dates)
            lots, acquisitions, allocated = [], [], {}
            basis = 0.
            for allocation in allocations:
                buy_id = allocation["buy_transaction_id"]
                buy = buys.get(buy_id)
                if not buy or buy["currency"] != sale["currency"] or buy["ticker"] != sale["ticker"]:
                    raise HistoricalDataMissing("Kauftransaktion fehlt oder passt nicht zur Zuordnung")
                if not buy.get("execution_at") or not math.isfinite(float(buy.get("price") or 0)) or buy["price"] <= 0:
                    raise HistoricalDataMissing("Kaufpreis oder Ausführungszeit fehlt")
                if utc(buy["execution_at"]) > utc(sale["execution_at"]):
                    raise HistoricalDataMissing("Kauf liegt nach dem Verkauf")
                allocated[buy_id] = allocated.get(buy_id, 0.) + allocation["shares"]
                used = reserved.get(buy_id, 0.) + allocated[buy_id]
                if used > buy["shares"] + 1e-6:
                    raise HistoricalDataMissing("Kaufanteil würde mehrfach gezählt")
                # Commit quantity reservations only after the entire case is validated.
                if lot_wise and buy_id not in cache:
                    cache[buy_id] = replay_lot(frame, frames["SPY"], sale["ticker"], buy, setup, factors, end)
                buy_tax = abs(float(buy.get("tax") or 0)) * allocation["shares"] / buy["shares"]
                basis += allocation["cost_basis"] - buy_tax
                acquisitions.append({"buy": buy, "shares": allocation["shares"]})
                if lot_wise:
                    lots.append((allocation, cache[buy_id]))
            if not lot_wise:
                modeled = replay_position(frame, frames["SPY"], sale["ticker"], acquisitions, setup, factors, end)
                lots = [({"shares": sale["shares"], "buy_transaction_id": "pooled_selected_acquisitions"}, modeled)]
            actual_fee = abs(float(sale.get("execution_fees") or portfolio.get("fees") or 0.))
            actual_pnl = sale["price"] * sale["shares"] - actual_fee - basis
            case_rows = []
            for horizon in ["actual_sale", "extended_hold"]:
                end_at = utc(sale["execution_at"]) if horizon == "actual_sale" else session_times(sale["ticker"], end)[1]
                terminal = sale["price"] if horizon == "actual_sale" else float(frame.loc[end, "Close"] * factors.loc[end])
                for key in STRATEGIES:
                    value, remaining, dates, fills = sale_value(sale, lots, key, end_at, terminal)
                    # In the equal-horizon model, unsold shares leave at the actual
                    # broker execution price. Extended residuals remain unliquidated.
                    # The actual-time terminal liquidation is a separate order,
                    # even if a partial model exit already filled at that day's open.
                    orders = len(dates) + int(horizon == "actual_sale" and remaining > 1e-8)
                    fees = actual_fee * orders
                    modeled_pnl = value - fees - basis
                    case_rows.append({"sale_id": sale["id"], "ticker": sale["ticker"], "sale_date": sale["trade_date"],
                        "horizon": horizon, "strategy": key, "basis_eur": basis,
                        "actual_pnl_pre_tax_eur": actual_pnl, "journal_pnl_after_tax_eur": sale["realized_pnl"],
                        "modeled_pnl_pre_tax_eur": modeled_pnl, "delta_eur": modeled_pnl - actual_pnl,
                        "remaining_shares": remaining, "orders": orders, "modeled_exit_fees_eur": fees,
                        "model_end": sale["trade_date"] if horizon == "actual_sale" else str(end.date()), "fills": fills})
            rows.extend(case_rows)
            for allocation in allocations:
                buy_id = allocation["buy_transaction_id"]
                reserved[buy_id] = reserved.get(buy_id, 0.) + allocation["shares"]
        except (HistoricalDataMissing, KeyError, IndexError) as exc:
            exclusions.append({"sale_id": sale["id"], "ticker": sale["ticker"], "sale_date": sale["trade_date"], "reason": str(exc)})
    summaries = []
    for horizon in ["actual_sale", "extended_hold"]:
        for key in STRATEGIES:
            part = [r for r in rows if r["horizon"] == horizon and r["strategy"] == key]
            summaries.append({"horizon": horizon, "strategy": key, "label": rules.SELL_STRATEGY_LABELS[key],
                "sales": len(part), "actual_pnl_pre_tax_eur": sum(r["actual_pnl_pre_tax_eur"] for r in part),
                "modeled_pnl_pre_tax_eur": sum(r["modeled_pnl_pre_tax_eur"] for r in part),
                "delta_eur": sum(r["delta_eur"] for r in part),
                "improved": sum(r["delta_eur"] > .01 for r in part), "worse": sum(r["delta_eur"] < -.01 for r in part),
                "open_cases": sum(r["remaining_shares"] > 1e-8 for r in part) if horizon == "extended_hold" else 0})
    return {"selected_sales": len(data["sales"]), "market_cutoff": data["cutoff"], "valuation_date": str(end.date()),
        "method": ("Independent FIFO lots" if lot_wise else "Pooled selected FIFO shares, actual purchase times, remaining FIFO weighted entry, new cycle after flat") + "; native daily rules; next exchange open; prior-day FX; no tax; actual per-order fee; no reinvestment",
        "sell_setup": setup, "summaries": summaries, "rows": rows, "exclusions": exclusions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lot-wise", action="store_true", help="Sensitivity check: evaluate acquisition lots independently")
    args = parser.parse_args()
    result = run(json.loads(args.input.read_text()), lot_wise=args.lot_wise,
                 progress=lambda message: print(message, file=sys.stderr, flush=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    for horizon in ["actual_sale", "extended_hold"]:
        for row in sorted((r for r in result["summaries"] if r["horizon"] == horizon), key=lambda r: r["delta_eur"], reverse=True):
            print(horizon, row["strategy"], row["sales"], round(row["delta_eur"], 2))
    print("Excluded:", result["exclusions"])


if __name__ == "__main__":
    main()
