from copy import deepcopy

import pandas as pd
import pytest

from app.domain.sell import rules
from app.research.journal_exit_backtest import currency_factors, replay_lot, replay_position, run, sale_value, session_times, utc
from app.services.historical_sell import HistoricalDataMissing
from app.services.market_calendar import _ticker_calendar


def fixture_data():
    dates = _ticker_calendar("TEST").sessions_in_range("2024-01-02", "2025-03-01")[:225]
    close = [100.] * 205 + [85.] * 20
    stock = pd.DataFrame({"Open": close, "High": [p+1 for p in close], "Low": [p-1 for p in close],
                          "Close": close, "Volume": 1000000.}, index=dates)
    spy = stock.assign(Open=100., High=101., Low=99., Close=100.)
    entry, sold = dates[204], dates[210]
    buy = {"id": "buy", "ticker": "TEST", "date": str(entry.date()), "execution_at": session_times("TEST", entry)[0].isoformat(),
           "price": 100., "shares": 10., "currency": "EUR", "fees": 1., "tax": 0.}
    sale = {"id": "sale", "ticker": "TEST", "trade_date": str(sold.date()),
            "execution_at": (session_times("TEST", sold)[0]+pd.Timedelta(minutes=30)).isoformat(), "price": 85.,
            "shares": 10., "currency": "EUR", "execution_fees": -1., "realized_pnl": -152.,
            "portfolio_snapshot_json": {"fees": -1., "unallocated_shares": 0., "allocations": [
                {"buy_transaction_id": "buy", "buy_date": buy["date"], "shares": 10., "cost_basis": 1001.}]}}
    prices = []
    for ticker, frame in [("TEST", stock), ("SPY", spy), ("EURUSD=X", spy.assign(Open=1., High=1., Low=1., Close=1.))]:
        prices.extend({"ticker": ticker, "date": str(day.date()), **{k.lower(): float(v) for k, v in row.items()}} for day, row in frame.iterrows())
    return {"cutoff": str(dates[-1].date()), "sales": [sale], "buys": [buy], "prices": prices,
            "sell_setup": rules.normalize_sell_setup_payload({}, migrate_legacy=False)}, stock, spy


def test_fx_uses_strictly_prior_quotes_and_rejects_stale_history():
    fx = pd.DataFrame({"Close": [2., 1000.]}, index=pd.to_datetime(["2024-06-07", "2024-06-10"]))
    frames = {"EURUSD=X": fx}
    assert currency_factors(frames, "TEST", "EUR", pd.to_datetime(["2024-06-10"])).iloc[0] == .5
    friday_only = {"EURUSD=X": fx.iloc[:1]}
    assert currency_factors(friday_only, "TEST", "EUR", pd.to_datetime(["2024-06-11"])).iloc[0] == .5
    with pytest.raises(HistoricalDataMissing):
        currency_factors(friday_only, "TEST", "EUR", pd.to_datetime(["2024-06-12"]))


def test_actual_horizon_does_not_change_when_future_prices_change():
    data, _, _ = fixture_data()
    result = run(data)
    assert not result["exclusions"]
    changed = deepcopy(data)
    for bar in changed["prices"]:
        if bar["ticker"] == "TEST" and bar["date"] > data["sales"][0]["trade_date"]:
            for key in ["open", "high", "low", "close"]:
                bar[key] *= 100
    rerun = run(changed)
    assert [r for r in result["rows"] if r["horizon"] == "actual_sale"] == [r for r in rerun["rows"] if r["horizon"] == "actual_sale"]
    for row in result["rows"]:
        assert all(utc(f["fill_at"]).date().isoformat() > f["signal_date"] for f in row["fills"])
        assert sum(f["shares"] for f in row["fills"]) <= 10. + 1e-8


def test_purchase_after_close_cannot_use_that_close_as_a_signal():
    data, stock, spy = fixture_data()
    buy = data["buys"][0]
    day = pd.Timestamp(buy["date"])
    buy["execution_at"] = (session_times("TEST", day)[1]+pd.Timedelta(minutes=5)).isoformat()
    stock.loc[stock.index >= day, ["Open", "High", "Low", "Close"]] *= .5
    result = replay_lot(stock, spy, "TEST", buy, data["sell_setup"], pd.Series(1., index=stock.index), stock.index[-1])
    assert result["custom"]
    assert result["custom"][0]["signal_date"] > buy["date"]


def test_same_day_earlier_us_open_after_a_later_sale_is_not_counted():
    sale = {"shares": 10.}
    allocation = {"shares": 10., "buy_transaction_id": "buy"}
    fills = {"custom": [{"fill_date": "2024-06-10", "fill_at": "2024-06-10T13:30:00Z",
                           "signal_date": "2024-06-07", "pct": 100., "price": 90.}]}
    value, left, orders, _ = sale_value(sale, [(allocation, fills)], "custom", utc("2024-06-10T12:00Z"), 80.)
    assert (value, left, orders) == (800., 10., set())


def test_missing_fifo_and_short_history_are_excluded_without_substitution():
    data, _, _ = fixture_data()
    data["sales"][0]["portfolio_snapshot_json"]["unallocated_shares"] = 1.
    result = run(data)
    assert len(result["exclusions"]) == 1 and not result["rows"]
    data, _, _ = fixture_data()
    data["prices"] = [p for p in data["prices"] if p["date"] >= data["buys"][0]["date"]]
    result = run(data)
    assert len(result["exclusions"]) == 1 and not result["rows"]


def test_acquisition_shares_cannot_be_reused_across_sales():
    data, _, _ = fixture_data()
    data["sales"].append({**deepcopy(data["sales"][0]), "id": "duplicate"})
    result = run(data)
    assert len(result["rows"]) == 16
    assert len(result["exclusions"]) == 1


def test_foreign_close_cannot_see_later_us_close(monkeypatch):
    import app.research.journal_exit_backtest as module
    dates = _ticker_calendar("TEST.HK").sessions_in_range("2023-01-03", "2024-06-28")
    us_dates = _ticker_calendar("SPY").sessions_in_range("2023-01-03", "2024-06-28")
    frame = pd.DataFrame({"Open": 100., "High": 101., "Low": 99., "Close": 100., "Volume": 1000000.}, index=dates)
    spy = frame.reindex(us_dates).fillna(100.)
    real = module.build_sell_decision_metrics_payload
    seen = []
    def capture(**kwargs):
        seen.append((kwargs["price_frame"].index[-1], kwargs["benchmark_frame"].index[-1]))
        return real(**kwargs)
    monkeypatch.setattr(module, "build_sell_decision_metrics_payload", capture)
    entry = dates[-5]
    buy = {"date": str(entry.date()), "execution_at": session_times("TEST.HK", entry)[0].isoformat(), "price": 100., "currency": "HKD"}
    replay_lot(frame, spy, "TEST.HK", buy, rules.normalize_sell_setup_payload({}, migrate_legacy=False), pd.Series(1., index=dates), dates[-1])
    assert seen and all(us_day < hk_day for hk_day, us_day in seen)


def test_pooled_entry_does_not_include_future_purchases(monkeypatch):
    import app.research.journal_exit_backtest as module
    data, stock, spy = fixture_data()
    first = data["buys"][0]
    later_day = stock.index[210]
    later = {**first, "id": "later", "date": str(later_day.date()), "price": 200.,
             "execution_at": (session_times("TEST", later_day)[1] + pd.Timedelta(minutes=5)).isoformat()}
    real = module.build_sell_decision_metrics_payload
    seen = []
    def capture(**kwargs):
        seen.append((kwargs["price_frame"].index[-1], kwargs["buy_price"]))
        return real(**kwargs)
    monkeypatch.setattr(module, "build_sell_decision_metrics_payload", capture)
    monkeypatch.setattr(module, "native_exit", lambda *a: {"pct": 0, "state": {}, "target_pct": 0})
    replay_position(stock, spy, "TEST", [{"buy": first, "shares": 5.}, {"buy": later, "shares": 5.}],
                    data["sell_setup"], pd.Series(1., index=stock.index), stock.index[-1])
    assert seen
    assert all(price == 100. for day, price in seen if day <= later_day)
    assert all(price == 150. for day, price in seen if day > later_day)


def test_pooled_exit_then_later_purchase_starts_a_new_cycle(monkeypatch):
    import app.research.journal_exit_backtest as module
    data, stock, spy = fixture_data()
    first = data["buys"][0]
    entry = pd.Timestamp(first["date"])
    first["execution_at"] = (session_times("TEST", entry)[1] + pd.Timedelta(minutes=5)).isoformat()
    later_day = stock.index[210]
    later = {**first, "id": "later", "date": str(later_day.date()), "price": 200.,
             "execution_at": (session_times("TEST", later_day)[1] + pd.Timedelta(minutes=5)).isoformat()}
    monkeypatch.setattr(module, "native_exit", lambda *a: {"pct": 100, "state": {}, "target_pct": 100})
    result = replay_position(stock, spy, "TEST", [{"buy": first, "shares": 5.}, {"buy": later, "shares": 5.}],
                             data["sell_setup"], pd.Series(1., index=stock.index), stock.index[-1])
    for fills in result.values():
        assert len(fills) == 2 and sum(f["pct"] for f in fills) == 100.
        assert fills[0]["signal_date"] > first["date"]
        assert fills[1]["signal_date"] > later["date"]


def test_partial_open_fill_and_actual_time_liquidation_pay_two_order_fees(monkeypatch):
    import app.research.journal_exit_backtest as module
    data, stock, _ = fixture_data()
    sold = stock.index[205]
    data["sales"][0].update(trade_date=str(sold.date()),
        execution_at=(session_times("TEST", sold)[0] + pd.Timedelta(minutes=30)).isoformat())
    def first_tranche(payload, features, setup, sold_pct, state):
        return {"pct": max(0., 25. - sold_pct), "state": {}, "target_pct": 25.}
    monkeypatch.setattr(module, "native_exit", first_tranche)
    result = run(data)
    assert not result["exclusions"]
    for row in result["rows"]:
        if row["horizon"] == "actual_sale":
            assert row["orders"] == 2
            assert row["modeled_exit_fees_eur"] == 2.
