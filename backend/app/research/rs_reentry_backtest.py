"""Private, causal RS-tranche reentries on the same journal acquisitions.

Native RS exits and emergency rules remain in force. Only RS-caused exits may
return on a fresh upward cross of their own average. Original purchases remain
external contributions; reentries use sale cash, with explicit additional cash
when restoring the same number of shares. No live orders or settings writes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import sys

import pandas as pd

from app.domain.sell import rules
from app.domain.sell.metrics import build_sell_decision_metrics_payload
from app.research.journal_exit_backtest import currency_factors, session_times, utc
from app.research.stock_backtest import native_exit, price_frames
from app.services.historical_sell import HistoricalDataMissing
from app.services.market_calendar import _ticker_calendar

RS_STRATEGIES = ("rs_line", "rs_line_ema")
MODES = ("none", "same_shares", "sale_cash")
EPS = 1e-8


def upward_crosses(metrics, strategy):
    """Crosses use two final common closes, never a future/intraday close."""
    history = metrics.get("rs_chart_history", [])
    if not metrics.get("rs_data_complete") or len(history) < 2:
        return set()
    previous, current = history[-2:]
    result = set()
    for period in ((21, 50) if strategy == "rs_line" else (21, 34, 50)):
        key = f"rs_ma{period}" if strategy == "rs_line" else f"rs_ema{period}"
        values = [previous.get("rs"), previous.get(key), current.get("rs"), current.get(key)]
        if all(v is not None and math.isfinite(float(v)) for v in values):
            if previous["rs"] <= previous[key] and current["rs"] > current[key]:
                result.add(period)
    return result


def rs_decision(payload, setup, strategy, buy_price, sold_pct, state):
    """Only RS recommendations plus native emergency features affect RS targets."""
    current = {**payload, "buy_price": buy_price}
    active = {**setup, "strategy_key": strategy}
    manual = {"sell_setup": active, "use_global_sell_setup": False}
    metrics = current["metrics"]
    features = rules._detect_emergency_features(current, manual, active, metrics, buy_price)
    features = rules._apply_feature_availability(features, current, active, metrics, manual)
    by_id = {feature.id: feature for feature in features}
    emergency = any(f.active and f.category == "emergency" for f in features)
    decision = native_exit(current, by_id, active, sold_pct, state)
    if emergency:
        cause = "emergency"
    else:
        recs = rules._strategy_recommendations(strategy, active, by_id, metrics)
        if strategy == "rs_line":
            cause = 50 if any(r.active and r.id == "rs_line_tranche_3" for r in recs) else 21
        else:
            cause = max((int(r.id.rsplit("_", 1)[-1]) for r in recs
                         if r.active and r.id.startswith("rs_ema_")), default=21)
    return decision, cause, emergency


@dataclass
class Account:
    strategy: str
    mode: str
    fee: float
    lots: list = field(default_factory=list)
    buckets: list = field(default_factory=list)
    events: list = field(default_factory=list)
    cash: float = 0.
    base_units: float = 0.
    state: dict = field(default_factory=dict)
    pending_sell: dict | None = None
    pending_buy: dict | None = None
    next_buy: int = 0
    last_rs_date: str = ""

    @property
    def shares(self):
        return sum(lot["shares"] for lot in self.lots)

    @property
    def held_units(self):
        return sum(lot["units"] for lot in self.lots)

    @property
    def out_units(self):
        return sum(bucket["units"] for bucket in self.buckets)

    @property
    def average(self):
        return sum(lot["shares"] * lot["price"] for lot in self.lots) / self.shares if self.shares > EPS else 0.

    def original_buy(self, acquisition):
        buy, quantity = acquisition["buy"], acquisition["shares"]
        if self.mode == "none" and self.shares <= EPS:
            # Match the pre-existing sell-only replay's fresh original holding cycle.
            self.base_units = 0.
            self.buckets = []
            self.state = {}
        self.base_units += quantity
        self.lots.append({"shares": quantity, "units": quantity, "price": buy["price"], "date": buy["date"]})
        self.events.append({"at": utc(buy["execution_at"]).isoformat(), "side": "buy", "kind": "original",
            "shares": quantity, "price": buy["price"], "fee": acquisition["fee"],
            "contribution": acquisition["basis"], "extra_capital": 0., "source_buy_id": buy["id"]})
        self.check()

    def sell(self, units, cause, day, at, price, signal_date, rs_date):
        units = min(units, self.held_units)
        if units <= EPS:
            return
        remaining, quantity = units, 0.
        for lot in self.lots:
            consumed = min(remaining, lot["units"])
            part = lot["shares"] * consumed / lot["units"]
            quantity += part
            lot["shares"] -= part
            lot["units"] -= consumed
            remaining -= consumed
            if remaining <= EPS:
                break
        self.lots = [lot for lot in self.lots if lot["units"] > EPS]
        proceeds = quantity * price - self.fee
        self.cash += proceeds
        self.buckets.append({"units": units, "shares": quantity, "budget": proceeds, "cause": cause,
                             "sold_at": at.isoformat(), "signal_date": signal_date})
        self.events.append({"at": at.isoformat(), "side": "sell", "kind": "strategy", "cause": cause,
            "shares": quantity, "price": price, "fee": self.fee, "contribution": 0., "extra_capital": 0.,
            "signal_date": signal_date, "rs_date": rs_date, "fill_date": str(day.date()), "units": units})
        self.check()

    def rebuy(self, selected, day, at, price, signal_date, rs_date):
        selected = [bucket for bucket in selected if any(bucket is existing for existing in self.buckets)
                    and bucket["cause"] != "emergency"]
        if not selected:
            return
        units = sum(bucket["units"] for bucket in selected)
        if self.mode == "same_shares":
            quantity = sum(bucket["shares"] for bucket in selected)
            required = quantity * price + self.fee
            extra = max(0., required - self.cash)
        elif self.mode == "sale_cash":
            budget = sum(bucket["budget"] for bucket in selected)
            if budget <= self.fee + EPS:
                return
            quantity = (budget - self.fee) / price
            required, extra = budget, 0.
        else:
            return
        self.cash += extra - required
        self.lots.append({"shares": quantity, "units": units, "price": price, "date": str(day.date())})
        causes = sorted({bucket["cause"] for bucket in selected})
        self.buckets = [bucket for bucket in self.buckets if not any(bucket is sold for sold in selected)]
        self.events.append({"at": at.isoformat(), "side": "buy", "kind": "reentry", "causes": causes,
            "shares": quantity, "price": price, "fee": self.fee, "contribution": extra, "extra_capital": extra,
            "signal_date": signal_date, "rs_date": rs_date, "fill_date": str(day.date()), "units": units,
            "matched_sales": [{"sold_at": bucket["sold_at"], "cause": bucket["cause"],
                "sold_shares": bucket["shares"], "sale_budget_eur": bucket["budget"],
                "reacquired_shares": bucket["shares"] if self.mode == "same_shares" else
                    quantity * bucket["budget"] / sum(b["budget"] for b in selected)} for bucket in selected]})
        self.check()

    def check(self):
        assert self.cash >= -EPS, "Negative cash / unrecorded financing"
        assert abs(self.held_units + self.out_units - self.base_units) <= max(EPS, self.base_units * 1e-8)
        assert all(lot["shares"] >= -EPS and lot["units"] >= -EPS for lot in self.lots)


def replay_case(frame, spy, ticker, acquisitions, setup, factors, end, fee):
    first = min(pd.Timestamp(a["buy"]["date"]) for a in acquisitions)
    if (frame.index < first).sum() < 200:
        raise HistoricalDataMissing("Weniger als 200 echte Kurstage vor dem Kauf")
    dates = frame.index[(frame.index >= first) & (frame.index <= end)]
    if len(_ticker_calendar(ticker).sessions_in_range(first, end).difference(dates)):
        raise HistoricalDataMissing("Kurslücke im Haltezeitraum")
    acquisitions = sorted(acquisitions, key=lambda a: utc(a["buy"]["execution_at"]))
    accounts = {(key, mode): Account(key, mode, fee) for key in RS_STRATEGIES for mode in MODES}
    for day in dates:
        opened, closed = session_times(ticker, day)
        for account in accounts.values():
            for until in (opened, closed):
                while account.next_buy < len(acquisitions) and utc(acquisitions[account.next_buy]["buy"]["execution_at"]) <= until:
                    account.original_buy(acquisitions[account.next_buy])
                    account.next_buy += 1
                if until == opened:
                    if account.pending_sell:
                        account.sell(day=day, at=opened, price=float(frame.loc[day, "Open"] * factors.loc[day]), **account.pending_sell)
                        account.pending_sell = None
                    if account.pending_buy:
                        pending = account.pending_buy
                        account.rebuy(pending["buckets"], day, opened, float(frame.loc[day, "Open"] * factors.loc[day]),
                                      pending["signal_date"], pending["rs_date"])
                        account.pending_buy = None
        if day == dates[-1] or all(a.base_units <= EPS for a in accounts.values()):
            continue
        history = frame.loc[:day].copy()
        history[["Open", "High", "Low", "Close"]] *= factors.loc[day]
        benchmark = spy.loc[[d for d in spy.index if session_times("SPY", d)[1] <= closed]]
        if len(benchmark) < 200:
            raise HistoricalDataMissing("Benchmark-Historie unvollständig")
        common = history.index.intersection(benchmark.index)
        payload = build_sell_decision_metrics_payload(ticker=ticker, buy_date=first,
            buy_price=acquisitions[0]["buy"]["price"], shares=1., price_frame=history,
            benchmark_frame=benchmark, currency=acquisitions[0]["buy"]["currency"], rs_completed_through=common[-1])
        if not payload.get("ok") or not payload.get("metrics", {}).get("rs_data_complete"):
            raise HistoricalDataMissing("RS-Benchmark-Historie am Signalzeitpunkt unvollständig")
        metrics = payload["metrics"]
        rs_date = metrics["rs_as_of"]
        for account in accounts.values():
            if account.base_units <= EPS:
                continue
            fresh = rs_date != account.last_rs_date
            crossed = upward_crosses(metrics, account.strategy) if fresh else set()
            account.last_rs_date = rs_date
            emergency = False
            if account.shares > EPS:
                decision, cause, emergency = rs_decision(payload, setup, account.strategy, account.average,
                    100. * account.out_units / account.base_units, account.state)
                account.state = decision["state"]
                if decision["pct"]:
                    units = min(account.held_units, max(0., decision["target_pct"] / 100. * account.base_units - account.out_units))
                    account.pending_sell = {"units": units, "cause": cause, "signal_date": str(day.date()), "rs_date": rs_date}
            if account.mode != "none" and not emergency:
                selected = [bucket for bucket in account.buckets if bucket["cause"] in crossed]
                if selected:
                    account.pending_buy = {"buckets": selected, "signal_date": str(day.date()), "rs_date": rs_date}
    return accounts


def value_at(events, end_at, price, fee, liquidate):
    cash = quantity = contributed = extra = costs = 0.
    buys = sells = 0
    included = []
    for event in sorted(events, key=lambda e: utc(e["at"])):
        if utc(event["at"]) > end_at:
            continue
        sign = 1. if event["side"] == "buy" else -1.
        contributed += event["contribution"]
        extra += event["extra_capital"]
        cash += event["contribution"] - sign * event["shares"] * event["price"] - event["fee"]
        quantity += sign * event["shares"]
        costs += event["fee"]
        buys += int(event["kind"] == "reentry")
        sells += int(event["kind"] == "strategy")
        assert cash >= -1e-6 and quantity >= -1e-6
        included.append(event)
    terminal_fee = fee if liquidate and quantity > EPS else 0.
    return {"pnl_eur": cash + quantity * price - terminal_fee - contributed,
            "extra_capital_eur": extra, "total_contributions_eur": contributed, "cash_eur": cash,
            "remaining_shares": max(0., quantity), "fees_eur": costs + terminal_fee,
            "reentries": buys, "strategy_sells": sells, "events": included}


def run(data, *, progress=None):
    frames = price_frames(data)
    tickers = {sale["ticker"] for sale in data["sales"]}
    end = min(pd.Timestamp(data["cutoff"]), *(frames[t].index[-1] for t in tickers if t in frames))
    buys = {buy["id"]: buy for buy in data["buys"]}
    setup = rules.normalize_sell_setup_payload(data["sell_setup"], migrate_legacy=False)
    rows, exclusions, reserved = [], [], {}
    for number, sale in enumerate(data["sales"], 1):
        if progress:
            progress(f"{number}/{len(data['sales'])}: {sale['ticker']}")
        try:
            allocations = sale["portfolio_snapshot_json"].get("allocations", [])
            if sale["currency"] != "EUR" or not sale.get("execution_at"):
                raise HistoricalDataMissing("EUR-Ausführung oder Ausführungszeit fehlt")
            if sale["portfolio_snapshot_json"].get("unallocated_shares") or not allocations or any(a["cost_basis"] is None for a in allocations):
                raise HistoricalDataMissing("Kaufzuordnung / Einstandsbasis unvollständig")
            if abs(sum(a["shares"] for a in allocations) - sale["shares"]) > 1e-6:
                raise HistoricalDataMissing("FIFO-Stückzahl stimmt nicht")
            acquisitions, allocated = [], {}
            for allocation in allocations:
                buy = buys[allocation["buy_transaction_id"]]
                if buy["ticker"] != sale["ticker"] or buy["currency"] != sale["currency"] or not buy.get("execution_at"):
                    raise HistoricalDataMissing("Kauftransaktion unvollständig")
                if utc(buy["execution_at"]) > utc(sale["execution_at"]):
                    raise HistoricalDataMissing("Kauf liegt nach Verkauf")
                quantity = float(allocation["shares"])
                if any(not math.isfinite(float(v)) or float(v) <= 0 for v in (quantity, buy["shares"], buy["price"], allocation["cost_basis"], sale["price"])):
                    raise HistoricalDataMissing("Ungültige Preise, Stückzahlen oder Einstandsbasis")
                allocated[buy["id"]] = allocated.get(buy["id"], 0.) + quantity
                if reserved.get(buy["id"], 0.) + allocated[buy["id"]] > buy["shares"] + EPS:
                    raise HistoricalDataMissing("Kaufanteil würde mehrfach gezählt")
                basis = allocation["cost_basis"] - abs(float(buy.get("tax") or 0)) * quantity / buy["shares"]
                buy_fee = basis - quantity * buy["price"]
                if buy_fee < -1e-5:
                    raise HistoricalDataMissing("Kostenbasis passt nicht zum Kauf; Kapitalmaßnahme prüfen")
                acquisitions.append({"buy": buy, "shares": quantity, "basis": basis, "fee": max(0., buy_fee)})
            frame = frames[sale["ticker"]]
            first = min(pd.Timestamp(a["buy"]["date"]) for a in acquisitions)
            factors = currency_factors(frames, sale["ticker"], sale["currency"], frame.index[(frame.index >= first) & (frame.index <= end)])
            fee = abs(float(sale.get("execution_fees") or sale["portfolio_snapshot_json"].get("fees") or 0.))
            accounts = replay_case(frame, frames["SPY"], sale["ticker"], acquisitions, setup, factors, end, fee)
            actual = sale["shares"] * sale["price"] - fee - sum(a["basis"] for a in acquisitions)
            case_rows = []
            for horizon in ("actual_sale", "extended_hold"):
                end_at = utc(sale["execution_at"]) if horizon == "actual_sale" else session_times(sale["ticker"], end)[1]
                price = sale["price"] if horizon == "actual_sale" else float(frame.loc[end, "Close"] * factors.loc[end])
                for (strategy, mode), account in accounts.items():
                    result = value_at(account.events, end_at, price, fee, horizon == "actual_sale")
                    case_rows.append({"sale_id": sale["id"], "ticker": sale["ticker"], "sale_date": sale["trade_date"],
                        "strategy": strategy, "mode": mode, "horizon": horizon, "model_end": str(end_at.date()),
                        "actual_pnl_pre_tax_eur": actual, "delta_actual_eur": result["pnl_eur"] - actual, **result})
            for row in case_rows:
                reference = next(r for r in case_rows if r["horizon"] == row["horizon"] and r["strategy"] == row["strategy"] and r["mode"] == "none")
                row["delta_sell_only_eur"] = row["pnl_eur"] - reference["pnl_eur"]
            rows.extend(case_rows)
            for buy_id, quantity in allocated.items():
                reserved[buy_id] = reserved.get(buy_id, 0.) + quantity
        except (HistoricalDataMissing, KeyError, IndexError) as exc:
            exclusions.append({"sale_id": sale["id"], "ticker": sale["ticker"], "sale_date": sale["trade_date"], "reason": str(exc)})
    summaries = []
    for horizon in ("actual_sale", "extended_hold"):
        for strategy in RS_STRATEGIES:
            for mode in MODES:
                part = [r for r in rows if (r["horizon"], r["strategy"], r["mode"]) == (horizon, strategy, mode)]
                summaries.append({"horizon": horizon, "strategy": strategy, "mode": mode, "cases": len(part),
                    **{key: sum(r[key] for r in part) for key in ("pnl_eur", "actual_pnl_pre_tax_eur", "delta_actual_eur",
                        "delta_sell_only_eur", "extra_capital_eur", "total_contributions_eur", "fees_eur", "reentries", "strategy_sells")},
                    "improved_vs_sell_only": sum(r["delta_sell_only_eur"] > .01 for r in part),
                    "worse_vs_sell_only": sum(r["delta_sell_only_eur"] < -.01 for r in part),
                    "open_cases": sum(r["remaining_shares"] > EPS for r in part) if horizon == "extended_hold" else 0})
    return {"selected_sales": len(data["sales"]), "market_cutoff": data["cutoff"], "valuation_date": str(end.date()),
        "primary_mode": "same_shares", "sell_setup": setup, "summaries": summaries, "rows": rows, "exclusions": exclusions,
        "method": "Native RS exits; cause-matched fresh final-close upward crosses; next exchange open; full-position exits monitored for reentry; same-share primary with explicit external funding; sale-cash sensitivity; emergency-sale tranches excluded from reentry; pretax P&L net of all contributions and fees"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = run(json.loads(args.input.read_text()), progress=lambda s: print(s, file=sys.stderr, flush=True))
    result["input_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    for row in result["summaries"]:
        print(row["horizon"], row["strategy"], row["mode"], row["cases"], round(row["pnl_eur"], 2),
              "extra capital", round(row["extra_capital_eur"], 2), "reentries", row["reentries"])
    print("Excluded:", result["exclusions"])


if __name__ == "__main__":
    main()
