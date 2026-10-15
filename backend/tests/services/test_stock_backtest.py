from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.domain.sell import rules
from app.research.stock_backtest import next_executable_open, native_exit, prepare_features, replay_cohort
from app.domain.sell.metrics import build_sell_decision_metrics_payload


def frames():
    dates = pd.bdate_range("2024-01-02", periods=225)
    close = np.r_[np.linspace(80, 100, 205), np.linspace(100, 75, 20)]
    frame = pd.DataFrame({"Open": close + .2, "High": close + 1, "Low": close - 1,
                          "Close": close, "Volume": 1_000_000.}, index=dates)
    return frame, frame.assign(Open=100., High=101., Low=99., Close=100.)


def test_entry_waits_until_after_actual_publication_even_when_signal_date_is_old():
    frame, _ = frames()
    day = frame.index[200]
    after_open = f"{day.date()}T16:00:00Z"
    before_open = f"{day.date()}T10:00:00Z"
    assert next_executable_open(frame, after_open, str((day - timedelta(days=5)).date())) == frame.index[201]
    assert next_executable_open(frame, before_open, str((day - timedelta(days=5)).date())) == day


def test_offline_targets_and_confirmation_match_full_production_engine():
    frame, spy = frames()
    entry = frame.index[201]
    payload = build_sell_decision_metrics_payload(ticker="TEST", buy_date=entry,
        buy_price=float(frame.loc[entry, "Open"]), shares=1, price_frame=frame.iloc[:216],
        benchmark_frame=spy.iloc[:216], rs_completed_through=frame.index[215])
    setup = rules.normalize_sell_setup_payload({}, migrate_legacy=False)
    features = prepare_features(payload, setup)
    for key in rules.SELL_STRATEGY_LABELS:
        active = {**setup, "strategy_key": key}
        for sold in [0, 25, 60]:
            decision = native_exit(payload, features, active, sold, {})
            full = rules.evaluate_sell_decision(payload, {"sell_setup": active, "use_global_sell_setup": False},
                [{"ticker": "TEST", "date": str(entry.date()), "tranche_percent": sold}], {})
            assert decision["raw_pct"] == full["sell_now_percent"]
            assert decision["state"] == full["next_recommendation_state"]
            assert decision["status"] == full["pending_status"]


def test_replay_never_uses_future_candles_or_sells_before_signal():
    frame, spy = frames()
    setup = rules.normalize_sell_setup_payload({}, migrate_legacy=False)
    entry, end = frame.index[201], frame.index[218]
    baseline = replay_cohort(frame, spy, "TEST", entry, end, setup)
    changed = frame.copy()
    changed.loc[changed.index > end, ["Open", "High", "Low", "Close"]] *= 100
    assert replay_cohort(changed, spy, "TEST", entry, end, setup) == baseline
    for row in baseline:
        assert sum(fill["pct"] for fill in row["fills"]) <= 100
        assert all(date.fromisoformat(fill["fill_date"]) > date.fromisoformat(fill["signal_date"]) for fill in row["fills"])
        assert row["net_25bps_pct"] < row["net_10bps_pct"] < row["net_0bps_pct"]
