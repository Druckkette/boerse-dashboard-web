from copy import deepcopy

import pandas as pd
import pytest

from app.domain.sell import rules
from app.domain.sell.metrics import build_sell_decision_metrics_payload
from app.research.journal_exit_backtest import replay_position, session_times, utc
from app.research.rs_reentry_backtest import Account, replay_case, rs_decision, run, upward_crosses, value_at
from app.research.stock_backtest import native_exit, prepare_features
from app.services.market_calendar import _ticker_calendar


def account(mode="same_shares"):
    result = Account("rs_line", mode, 1.)
    buy = {"id": "buy", "date": "2024-01-02", "execution_at": "2024-01-02T15:00Z", "price": 100.}
    result.original_buy({"buy": buy, "shares": 10., "basis": 1001., "fee": 1.})
    return result


def test_same_shares_restores_quantity_and_subtracts_added_capital_from_profit():
    result = account()
    result.sell(10., 21, pd.Timestamp("2024-01-03"), utc("2024-01-03T14:30Z"), 100., "2024-01-02", "2024-01-02")
    result.rebuy(result.buckets.copy(), pd.Timestamp("2024-01-05"), utc("2024-01-05T14:30Z"), 110., "2024-01-04", "2024-01-04")
    assert result.shares == 10. and result.out_units == 0.
    value = value_at(result.events, utc("2024-01-05T21:00Z"), 110., 1., False)
    assert value["extra_capital_eur"] == pytest.approx(102.)
    assert value["pnl_eur"] == pytest.approx(-3.)  # original, sale and rebuy fees
    assert value["cash_eur"] == pytest.approx(result.cash)


def test_sale_cash_never_uses_external_money_and_preserves_remaining_tranche_cash():
    result = account("sale_cash")
    result.sell(5., 21, pd.Timestamp("2024-01-03"), utc("2024-01-03T14:30Z"), 100., "2024-01-02", "2024-01-02")
    result.sell(5., 50, pd.Timestamp("2024-01-04"), utc("2024-01-04T14:30Z"), 100., "2024-01-03", "2024-01-03")
    result.rebuy([result.buckets[0]], pd.Timestamp("2024-01-05"), utc("2024-01-05T14:30Z"), 110., "2024-01-04", "2024-01-04")
    assert result.shares == pytest.approx(498. / 110.)
    assert result.cash == pytest.approx(499.)
    assert result.out_units == 5.
    assert sum(e["extra_capital"] for e in result.events) == 0.


def test_multiple_tranches_on_same_up_cross_use_one_rebuy_fee():
    result = account()
    for day in ("2024-01-03", "2024-01-04"):
        result.sell(2.5, 21, pd.Timestamp(day), utc(day + "T14:30Z"), 100., "2024-01-02", "2024-01-02")
    result.rebuy(result.buckets.copy(), pd.Timestamp("2024-01-05"), utc("2024-01-05T14:30Z"), 100., "2024-01-04", "2024-01-04")
    assert result.shares == 10.
    assert len([e for e in result.events if e["kind"] == "reentry"]) == 1
    assert result.events[-1]["fee"] == 1.


def test_emergency_tranches_do_not_return_on_rs_crosses():
    result = account()
    result.sell(10., "emergency", pd.Timestamp("2024-01-03"), utc("2024-01-03T14:30Z"), 90., "2024-01-02", "2024-01-02")
    result.rebuy(result.buckets.copy(), pd.Timestamp("2024-01-05"), utc("2024-01-05T14:30Z"), 100., "2024-01-04", "2024-01-04")
    assert result.shares == 0. and result.out_units == 10.


def test_cross_uses_the_corresponding_average_and_two_final_closes():
    metrics = {"rs_data_complete": True, "rs_chart_history": [
        {"rs": .9, "rs_ma21": 1., "rs_ma50": 1.2, "rs_ema21": 1., "rs_ema34": 1.2, "rs_ema50": 1.3},
        {"rs": 1.1, "rs_ma21": 1., "rs_ma50": 1.2, "rs_ema21": 1., "rs_ema34": 1.2, "rs_ema50": 1.3}]}
    assert upward_crosses(metrics, "rs_line") == {21}
    assert upward_crosses(metrics, "rs_line_ema") == {21}
    assert upward_crosses({**metrics, "rs_data_complete": False}, "rs_line") == set()
    assert upward_crosses({**metrics, "rs_chart_history": metrics["rs_chart_history"][-1:]}, "rs_line") == set()


def frames():
    dates = _ticker_calendar("TEST").sessions_in_range("2023-01-03", "2024-06-01")[:235]
    close = [70. + n * 30. / 204 for n in range(205)] + [100., 97., 97., 97., 104., 105., 102., 102., 102., 109.] * 3
    stock = pd.DataFrame({"Open": close, "High": [v + .2 for v in close], "Low": [v - .2 for v in close],
                          "Close": close, "Volume": 1000000.}, index=dates)
    spy = stock.assign(Open=100., High=101., Low=99., Close=100.)
    setup = {**rules.normalize_sell_setup_payload({}, migrate_legacy=False), "emergency_stop_value": 50.}
    buy = {"id": "buy", "ticker": "TEST", "date": str(dates[204].date()), "execution_at": session_times("TEST", dates[204])[0].isoformat(),
           "price": float(stock.loc[dates[204], "Open"]), "shares": 10., "currency": "EUR", "tax": 0., "fees": 1.}
    acquisitions = [{"buy": buy, "shares": 10., "fee": 1., "basis": 1001.}]
    return stock, spy, setup, acquisitions


def test_rs_only_feature_pass_matches_full_native_engine():
    stock, spy, setup, acquisitions = frames()
    payload = build_sell_decision_metrics_payload(ticker="TEST", buy_date=acquisitions[0]["buy"]["date"], buy_price=100.,
        shares=1., price_frame=stock.iloc[:215], benchmark_frame=spy.iloc[:215], rs_completed_through=stock.index[214])
    for strategy in ("rs_line", "rs_line_ema"):
        for price in (100., 130.):
            current = {**payload, "buy_price": price}
            for sold in (0., 25., 60.):
                optimized, _, _ = rs_decision(payload, setup, strategy, price, sold, {})
                complete = native_exit(current, prepare_features(current, setup), {**setup, "strategy_key": strategy}, sold, {})
                assert optimized == complete


def test_repeated_cycles_full_exits_reentries_and_sell_only_control_match():
    stock, spy, setup, acquisitions = frames()
    factors = pd.Series(1., index=stock.index)
    accounts = replay_case(stock, spy, "TEST", acquisitions, setup, factors, stock.index[-1], 1.)
    old = replay_position(stock, spy, "TEST", acquisitions, setup, factors, stock.index[-1])
    for strategy in ("rs_line", "rs_line_ema"):
        control = accounts[strategy, "none"]
        assert [(e["fill_date"], e["shares"], e["price"]) for e in control.events if e["kind"] == "strategy"] == [
            (f["fill_date"], f["pct"] / 100. * 10., f["price"]) for f in old[strategy]]
        reentry = accounts[strategy, "same_shares"]
        assert len([e for e in reentry.events if e["kind"] == "reentry"]) >= 2
        assert all(utc(e["at"]).date().isoformat() > e["signal_date"] for e in reentry.events if e["kind"] != "original")
        assert reentry.shares <= 10. + 1e-8
        restored = []
        for event in reentry.events:
            if event["kind"] == "reentry":
                assert sum(m["reacquired_shares"] for m in event["matched_sales"]) == pytest.approx(event["shares"])
                for matched in event["matched_sales"]:
                    assert matched["reacquired_shares"] == matched["sold_shares"]
                    assert matched["cause"] in event["causes"]
                    assert matched["sold_at"] not in restored
                    restored.append(matched["sold_at"])


def test_future_prices_cannot_change_previous_cash_profit_or_funding():
    stock, spy, setup, acquisitions = frames()
    end_at = session_times("TEST", stock.index[215])[0] - pd.Timedelta(minutes=30)
    baseline = replay_case(stock, spy, "TEST", acquisitions, setup, pd.Series(1., index=stock.index), stock.index[-1], 1.)
    changed = stock.copy()
    changed.loc[changed.index > stock.index[215], ["Open", "High", "Low", "Close"]] *= 100.
    again = replay_case(changed, spy, "TEST", acquisitions, setup, pd.Series(1., index=stock.index), stock.index[-1], 1.)
    for key in baseline:
        assert value_at(baseline[key].events, end_at, 100., 1., True) == value_at(again[key].events, end_at, 100., 1., True)


def test_snapshot_excludes_orders_after_actual_sale_even_on_same_date():
    result = account()
    result.sell(10., 21, pd.Timestamp("2024-01-03"), utc("2024-01-03T14:30Z"), 90., "2024-01-02", "2024-01-02")
    before = value_at(result.events, utc("2024-01-03T12:00Z"), 100., 1., True)
    assert before["strategy_sells"] == 0 and before["remaining_shares"] == 10.
    assert before["pnl_eur"] == pytest.approx(-2.)


def test_input_missing_fifo_and_short_history_are_explicitly_excluded():
    stock, spy, setup, acquisitions = frames()
    buy = acquisitions[0]["buy"]
    prices = []
    for ticker, frame in (("TEST", stock), ("SPY", spy), ("EURUSD=X", spy.assign(Open=1., High=1., Low=1., Close=1.))):
        prices.extend({"ticker": ticker, "date": str(day.date()), **{k.lower(): v for k, v in row.items()}} for day, row in frame.iterrows())
    sale = {"id": "sale", "ticker": "TEST", "trade_date": str(stock.index[-1].date()), "execution_at": session_times("TEST", stock.index[-1])[0].isoformat(),
            "shares": 10., "price": 100., "currency": "EUR", "execution_fees": 1.,
            "portfolio_snapshot_json": {"unallocated_shares": 1., "allocations": [{"shares": 10., "cost_basis": 1001., "buy_transaction_id": "buy"}]}}
    data = {"prices": prices, "sales": [sale], "buys": [buy], "cutoff": str(stock.index[-1].date()), "sell_setup": setup}
    assert not run(data)["rows"] and len(run(data)["exclusions"]) == 1
    changed = deepcopy(data)
    changed["sales"][0]["portfolio_snapshot_json"]["unallocated_shares"] = 0.
    changed["prices"] = [p for p in prices if p["date"] >= buy["date"]]
    assert not run(changed)["rows"] and len(run(changed)["exclusions"]) == 1
