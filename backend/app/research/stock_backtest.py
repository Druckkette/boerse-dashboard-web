"""Replay archived recommendations and compare the existing sell engines offline.

Input is an explicit NAS export. Current fundamentals are never projected into
past recommendation dates. Supplementary exit cohorts use a fixed hash sample
of today's universe and therefore retain survivorship bias.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd

from app.domain.sell import rules
from app.domain.sell.metrics import build_sell_decision_metrics_payload


STRATEGIES = tuple(rules.SELL_STRATEGY_LABELS)


def prepare_features(payload: dict, setup: dict) -> dict:
    """One native feature pass; feature detection does not depend on strategy_key."""
    metrics, _, buy_price, _ = rules._extract_inputs(payload)
    manual = {"sell_setup": setup, "use_global_sell_setup": False}
    features = [*rules._detect_emergency_features(payload, manual, setup, metrics, buy_price),
                *rules._detect_offensive_features(payload, setup, metrics, buy_price),
                *rules._detect_defensive_features(payload, manual, setup, metrics)]
    features = rules._apply_feature_availability(features, payload, setup, metrics, manual)
    return {feature.id: feature for feature in features}


def native_exit(payload: dict, features: dict, setup: dict, sold: float, state: dict) -> dict:
    """Use the exact production target and confirmation functions, without UI output."""
    key = setup["strategy_key"]
    metrics, ticker, _, _ = rules._extract_inputs(payload)
    recommendations = rules._strategy_recommendations(key, setup, features, metrics)
    emergency = any(f.active and f.category == "emergency" for f in features.values())
    target = 100 if emergency else int(rules._build_strategy_result(key, recommendations)["recommendation_percent"])
    sell_now = math.floor(max(0, min(100, target - sold)))
    status, next_state = rules._compute_recommendation_status(
        sell_now=sell_now, has_killer=emergency, as_of_date=payload["as_of"],
        prior_state=state, confirmed_signal=key in {"rs_line", "rs_line_ema"}, ticker=ticker)
    return {"pct": sell_now if status == "scharf" else 0, "status": status,
            "state": next_state, "raw_pct": sell_now, "target_pct": target}


def price_frames(data: dict) -> dict[str, pd.DataFrame]:
    table = pd.DataFrame(data["prices"])
    table["date"] = pd.to_datetime(table["date"])
    frames = {}
    for ticker, rows in table.groupby("ticker", sort=True):
        frame = rows.set_index("date").sort_index()
        frame = frame.loc[~frame.index.duplicated(keep="last"), ["open", "high", "low", "close", "volume"]]
        frame = frame.apply(pd.to_numeric, errors="coerce").rename(columns=str.title)
        # No fabricated candles or forward-filled stock prices.
        frames[ticker] = frame.dropna(subset=["Open", "High", "Low", "Close"])
    return frames


def next_executable_open(frame: pd.DataFrame, generated_at: str, signal_day: str):
    generated = pd.Timestamp(generated_at).tz_convert("America/New_York")
    after = frame[frame.index > pd.Timestamp(signal_day)]
    for day, row in after.iterrows():
        market_open = pd.Timestamp(day.date()).tz_localize("America/New_York") + pd.Timedelta(hours=9, minutes=30)
        if market_open > generated and row.Open > 0:
            return day
    return None


def recommendation_events(data: dict, frames: dict) -> list[dict]:
    events = []
    spy = frames["SPY"]
    for row in data["opportunities"]:
        if row["rank"] > 3:
            continue
        frame = frames.get(row["ticker"])
        event = {k: row[k] for k in ["ticker", "as_of", "rank", "generated_at", "daily_opportunity_score"]}
        entry = next_executable_open(frame, row["generated_at"], row["as_of"]) if frame is not None else None
        event["entry_date"] = str(entry.date()) if entry is not None else None
        if entry is None or entry not in spy.index:
            event["status"] = "pending_or_missing_entry"
            events.append(event)
            continue
        event["status"] = "entered"
        loc = frame.index.get_loc(entry)
        entry_price = float(frame.loc[entry, "Open"])
        event["entry_price"] = entry_price
        event["available_sessions"] = len(frame) - loc
        for horizon in [1, 5, 10, 20, 63]:
            if loc + horizon - 1 >= len(frame):
                continue
            end = frame.index[loc + horizon - 1]
            if end not in spy.index:
                continue
            stock_return = frame.loc[end, "Close"] / entry_price - 1
            benchmark_return = spy.loc[end, "Close"] / spy.loc[entry, "Open"] - 1
            event[f"return_{horizon}d_pct"] = float(stock_return * 100)
            event[f"spy_{horizon}d_pct"] = float(benchmark_return * 100)
            event[f"excess_{horizon}d_pp"] = float((stock_return - benchmark_return) * 100)
            for bps in [0, 10, 25]:
                event[f"net_{horizon}d_{bps}bps_pct"] = float(((1 + stock_return) * (1 - bps / 10000) / (1 + bps / 10000) - 1) * 100)
        events.append(event)
    return events


def replay_cohort(frame: pd.DataFrame, spy: pd.DataFrame, ticker: str, entry: pd.Timestamp,
                  end: pd.Timestamp, setup: dict, *, validate: bool = False) -> list[dict]:
    dates = frame.index[(frame.index >= entry) & (frame.index <= end)]
    if len(dates) < 2 or (frame.index < entry).sum() < 200:
        return []
    entry_price = float(frame.loc[entry, "Open"])
    if entry_price <= 0 or entry not in spy.index or dates[-1] not in spy.index:
        return []
    states = {key: {"sold": 0, "cash": 0., "state": {}, "pending": None, "fills": [], "equity": [], "invalid_days": 0} for key in STRATEGIES}
    for day in dates:
        live = []
        for key, account in states.items():
            pending = account["pending"]
            if pending:
                pct = min(pending["pct"], 100 - account["sold"])
                fill_price = float(frame.loc[day, "Open"])
                account["cash"] += pct / 100 * fill_price / entry_price
                account["sold"] += pct
                account["fills"].append({"signal_date": pending["signal_date"], "fill_date": str(day.date()), "pct": pct, "price": fill_price})
                account["pending"] = None
            account["equity"].append(account["cash"] + (1 - account["sold"] / 100) * float(frame.loc[day, "Close"]) / entry_price)
            if account["sold"] < 100:
                live.append(key)
        if not live or day == dates[-1]:
            continue
        payload = build_sell_decision_metrics_payload(
            ticker=ticker, buy_date=entry, buy_price=entry_price, shares=1,
            price_frame=frame[frame.index <= day], benchmark_frame=spy[spy.index <= day],
            rs_completed_through=day)
        if not payload.get("ok"):
            for key in live:
                states[key]["invalid_days"] += 1
            continue
        features = prepare_features(payload, setup)
        for key in live:
            account = states[key]
            active_setup = {**setup, "strategy_key": key}
            decision = native_exit(payload, features, active_setup, account["sold"], account["state"])
            if validate:
                original = rules.evaluate_sell_decision(payload,
                    {"sell_setup": active_setup, "use_global_sell_setup": False},
                    [{"ticker": ticker, "date": str(entry.date()), "tranche_percent": account["sold"]}], account["state"])
                assert decision["raw_pct"] == original["sell_now_percent"]
                assert decision["status"] == original["pending_status"]
                assert decision["state"] == original["next_recommendation_state"]
            account["state"] = decision["state"]
            if decision["pct"] > 0:
                account["pending"] = {"pct": decision["pct"], "signal_date": str(day.date())}
    buy_hold = float(frame.loc[dates[-1], "Close"]) / entry_price - 1
    benchmark = float(spy.loc[dates[-1], "Close"]) / float(spy.loc[entry, "Open"]) - 1
    rows = []
    for key, account in states.items():
        equity = np.array([1., *account["equity"]])
        final = float(equity[-1])
        row = {"ticker": ticker, "strategy": key, "entry": str(entry.date()), "end": str(dates[-1].date()),
               "sessions": len(dates), "gross_return_pct": (final - 1) * 100,
               "buy_hold_pct": buy_hold * 100, "spy_pct": benchmark * 100,
               "excess_buy_hold_pp": (final - 1 - buy_hold) * 100,
               "max_drawdown_pct": float((equity / np.maximum.accumulate(equity) - 1).min() * 100),
               "sold_pct": account["sold"], "fills": account["fills"], "invalid_days": account["invalid_days"]}
        # A common 1-bps/10-bps/25-bps proportional fee at every buy/sale.
        # Remaining shares are liquidated at the final close for comparable horizons.
        for bps in [0, 10, 25]:
            cost = bps / 10000
            row[f"net_{bps}bps_pct"] = ((final * (1 - cost) / (1 + cost)) - 1) * 100
        rows.append(row)
    return rows


def _run_ticker(args):
    ticker, frame, spy, setup, cohort_specs = args
    rows = []
    for kind, entry, end in cohort_specs:
        result = replay_cohort(frame, spy, ticker, entry, end, setup)
        rows.extend({**row, "sample": kind} for row in result)
    return rows


def build_cohort_jobs(data: dict, frames: dict, events: list[dict]):
    spy = frames["SPY"]
    jobs = []
    for ticker, frame in frames.items():
        if ticker in {"SPY", "QQQ"}:
            continue
        specs = []
        # Real recommendation entries, one independent holding per saved ticker/day.
        for event in events:
            if event["ticker"] == ticker and event.get("entry_date"):
                entry = pd.Timestamp(event["entry_date"])
                if entry in frame.index:
                    specs.append(("archived_top3", entry, frame.index[-1]))
        if ticker in data["sample_tickers"]:
            # Fixed six-month entry grid; no optimization on price or later returns.
            for year in range(frame.index[0].year, frame.index[-1].year + 1):
                for month in [1, 7]:
                    eligible = frame.index[(frame.index.year == year) & (frame.index.month == month)]
                    if len(eligible):
                        entry = eligible[0]
                        loc = frame.index.get_loc(entry)
                        if loc >= 200 and loc + 125 < len(frame):
                            end = frame.index[loc + 125]
                            # Large gaps require a separate missing-data treatment.
                            calendar = spy.index[(spy.index >= entry) & (spy.index <= end)]
                            if len(calendar.difference(frame.index)) == 0:
                                specs.append(("fixed_universe_sample", entry, end))
        if specs:
            jobs.append((ticker, frame, spy, data["sell_setup"], specs))
    return jobs


def summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    result = []
    for (sample, key), group in df.groupby(["sample", "strategy"]):
        result.append({"sample": sample, "strategy": key, "cohorts": len(group), "tickers": group.ticker.nunique(),
                       "first_entry": group.entry.min(), "last_end": group.end.max(),
                       "mean_net_10bps_pct": group.net_10bps_pct.mean(),
                       "median_net_10bps_pct": group.net_10bps_pct.median(),
                       "win_rate_pct": float((group.net_10bps_pct > 0).mean() * 100),
                       "mean_excess_buy_hold_pp": group.excess_buy_hold_pp.mean(),
                       "mean_buy_hold_pct": group.buy_hold_pct.mean(),
                       "mean_spy_pct": group.spy_pct.mean(),
                       "mean_max_drawdown_pct": group.max_drawdown_pct.mean(),
                       "worst_cohort_pct": group.net_10bps_pct.min(),
                       "mean_net_25bps_pct": group.net_25bps_pct.mean(),
                       "invalid_days": int(group.invalid_days.sum())})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = json.loads(args.input.read_text())
    frames = price_frames(data)
    events = recommendation_events(data, frames)
    jobs = build_cohort_jobs(data, frames, events)
    # Establish equivalence with full production evaluations before the larger run.
    validation = next(job for job in jobs if len(job[1]) >= 1000)
    ticker, frame, spy, setup, _ = validation
    replay_cohort(frame, spy, ticker, frame.index[500], frame.index[510], setup, validate=True)
    pd.DataFrame(events).to_csv(args.output / "recommendation-events.csv", index=False)
    total = sum(len(job[-1]) for job in jobs)
    print(json.dumps({"tickers": len(jobs), "cohorts": total, "strategies": len(STRATEGIES), "cutoff": data["cutoff"]}), flush=True)
    rows = []
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_run_ticker, job): job[0] for job in jobs}
        from concurrent.futures import as_completed
        for future in as_completed(futures):
            result = future.result()
            rows.extend(result)
            (args.output / "progress.json").write_text(json.dumps({"rows": len(rows), "last_ticker": futures[future], "elapsed_seconds": time.monotonic()-started}))
            print(f"{futures[future]}: {len(result)} results; {len(rows)} total", flush=True)
    pd.DataFrame([{k: v for k, v in row.items() if k != "fills"} for row in rows]).to_csv(args.output / "sell-cohorts.csv", index=False)
    (args.output / "sell-fills.json").write_text(json.dumps(rows, allow_nan=False))
    result = {"cutoff": data["cutoff"], "generated_at": datetime.now().isoformat(),
              "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
              "recommendation_events": len(events), "sell_summary": summary(rows),
              "elapsed_seconds": time.monotonic()-started,
              "limitations": ["Stored recommendations start 2026-09-22; no fabricated historical fundamentals.",
                              "Exit-only sample is deterministic from today's universe and has survivorship bias.",
                              "Price returns exclude dividends, taxes, FX and intraday stop fills.",
                              "Cohorts overlap and are not an investable compounded portfolio.",
                              "Current configured rules are replayed unchanged; parameters were not optimized."]}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    pd.DataFrame(result["sell_summary"]).to_csv(args.output / "sell-summary.csv", index=False)
    print("Completed", flush=True)


if __name__ == "__main__":
    main()
