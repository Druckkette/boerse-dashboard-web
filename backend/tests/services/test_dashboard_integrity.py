from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services import money, portfolio, settings, trade_journal
from app.services.portfolio_analysis import PriceBook, attribution
from app.services.signal_eligibility import sell_signal_eligibility
from app.schemas import SettingsPatch
from app.repositories.settings import SettingsRepositoryUnavailable


def bar(day, close):
    return SimpleNamespace(date=date.fromisoformat(day), close=close)


def test_fx_historical_conversion_uses_only_observations_before_execution(monkeypatch):
    monkeypatch.setattr(money.prices, "list_price_bars", lambda *a, **kw: [bar("2025-01-02", 1.2), bar("2025-01-03", 2)])
    rate = money.conversion("USD", "EUR", on=date(2025, 1, 3))
    assert rate.rate == pytest.approx(1 / 1.2)
    assert rate.as_of == date(2025, 1, 2)
    assert money.conversion("USD", "EUR", on=date(2025, 1, 2)) is None
    assert money.conversion("USD", "EUR", on=date(2025, 1, 10)) is None
    assert money.convert_amount(0, "JPY", "EUR", on=date(2025, 1, 2)) == 0


def test_manual_sale_allocates_buy_fees_and_keeps_native_currency():
    buy = SimpleNamespace(price=100, shares=10, currency="EUR", portfolio_snapshot_json={"fees": 10})
    assert trade_journal._manual_native_result(buy, price=120, shares=4, currency="EUR", fees=2, tax=3) == 71
    assert trade_journal._realized_pnl(buy, price=120, shares=4, currency="EUR", fees=2, tax=3, on=date(2025, 1, 3)) == (71, 20)
    with pytest.raises(ValueError, match="währung"):
        trade_journal._manual_native_result(buy, price=120, shares=4, currency="USD")
    with pytest.raises(ValueError, match="Kaufmenge"):
        trade_journal._manual_native_result(buy, price=120, shares=11, currency="EUR")


def test_failed_settings_write_and_read_cannot_report_success(monkeypatch):
    monkeypatch.setattr(settings.settings_repository, "read_settings", lambda: {})
    def unavailable(*args):
        raise SettingsRepositoryUnavailable("offline")
    monkeypatch.setattr(settings.settings_repository, "write_settings", unavailable)
    with pytest.raises(SettingsRepositoryUnavailable):
        settings.update_app_settings(SettingsPatch(atr_threshold=2))
    monkeypatch.setattr(settings.settings_repository, "read_settings", unavailable)
    with pytest.raises(SettingsRepositoryUnavailable):
        settings.update_app_settings(SettingsPatch(atr_threshold=2))


def test_missing_prices_are_not_backfilled_and_old_prices_expire():
    days = pd.date_range("2025-01-01", "2025-01-10")
    values = portfolio._align_price_series_to_calendar(pd.Series([100.], index=pd.to_datetime(["2025-01-03"])), days)
    assert pd.isna(values.loc["2025-01-02"])
    assert values.loc["2025-01-07"] == 100
    assert pd.isna(values.loc["2025-01-08"])
    assert portfolio._align_price_series_to_calendar(pd.Series(dtype=float), days).isna().all()


def test_attribution_reconciles_fee_income_cash_and_external_flows():
    start, end = date(2025, 1, 2), date(2025, 1, 3)
    book = PriceBook({"A": [bar("2025-01-02", 100), bar("2025-01-03", 110)]}, {"A": "USD"})
    def event(kind, day, shares, net, ticker="A", fees=0):
        return dict(id=kind, ticker=ticker, date=day, kind=kind, shares=shares, net=net, fees=fees, tax=0, currency="USD")
    ledger = {"events": [event("buy", start, 10, -1001, fees=1), event("sell", end, 5, 548, fees=2), event("dividend", end, 0, 3), event("customer_inbound", end, 0, 100, ticker="")], "cash_flows": [{"date": start, "amount": 2000, "currency": "USD", "kind": "deposit"}]}
    result = attribution(ledger, book, start=start, end=end, base="USD", positions=[SimpleNamespace(ticker="A", shares=5)])
    assert result["model"] == "executions"
    assert result["result"] == 101  # 100 price appreciation - 2 sale fees + 3 dividend
    assert result["external_cash_flow"] == 100
    row = result["rows"][0]
    assert row["price_effect"] + row["fx_effect"] + row["trading_and_interaction"] - row["costs"] == row["result"]
    assert result["ending_cash_value"] + row["ending_value"] - result["opening_cash_value"] - row["opening_value"] - 100 == result["result"]


def test_attribution_without_matching_executions_is_labeled_simulation():
    book = PriceBook({"A": [bar("2025-01-03", 110)]}, {"A": "USD"})
    result = attribution({"events": [], "cash_flows": []}, book, start=date(2025, 1, 2), end=date(2025, 1, 3), base="USD", positions=[SimpleNamespace(ticker="A", shares=5)])
    assert result["model"] == "current_holdings"
    assert result["result"] is None
    assert result["covered_count"] == 0
    assert book.value("A", 1, date(2025, 1, 6), "USD", exact=True) is None


def test_same_eligibility_for_confirmed_stale_future_and_limited_signals():
    now = datetime(2025, 1, 3, 22, tzinfo=UTC)
    row = dict(status="Verkaufen", pending_status="scharf", recommendation_pct=50, last_seen_date="2025-01-03", generated_at=now, data_quality_status="trusted")
    def evaluate(item):
        return sell_signal_eligibility(item, now=now, completed="2025-01-03", expected="2025-01-03")
    assert evaluate(row)["decision_eligible"]
    for patch in [{"generated_at": None}, {"last_seen_date": "2025-01-02"}, {"data_quality_status": "limited"}, {"generated_at": datetime(2025, 1, 4, tzinfo=UTC)}]:
        assert evaluate({**row, **patch})["decision_category"] == "data"
    assert evaluate({**row, "pending_status": "in_bestaetigung"})["decision_category"] == "observe"


def test_journal_mixed_currency_metrics_never_add_unconverted_amounts(monkeypatch):
    closed = [SimpleNamespace(status="closed", realized_pnl=100, currency="EUR", setup_tag="breakout", context_status="archived", r_multiple=2, first_entry_date="2025-01-02", last_exit_date="2025-01-03"), SimpleNamespace(status="closed", realized_pnl=-100, currency="USD", setup_tag="breakout", context_status="reconstructed", r_multiple=-1, first_entry_date="2025-01-02", last_exit_date="2025-01-03")]
    monkeypatch.setattr(trade_journal, "get_trade_journal_trades", lambda **kw: SimpleNamespace(trades=closed))
    result = trade_journal.get_trade_journal_analytics()
    assert result.net_result is None and result.currency is None
    assert {row["currency"]: row["net_result"] for row in result.by_currency} == {"EUR": 100, "USD": -100}
    archived = trade_journal.get_trade_journal_analytics(context="archived")
    assert archived.net_result == 100 and archived.currency == "EUR"


def test_unknown_security_in_ledger_prevents_complete_attribution():
    event = dict(id="unknown", ticker="", date=date(2025, 1, 3), kind="buy", shares=5, net=-100, fees=0, tax=0, currency="USD")
    result = attribution({"events": [event], "cash_flows": []}, PriceBook({}, {}), start=date(2025, 1, 2), end=date(2025, 1, 3), base="USD", positions=[])
    assert result["result"] is None
    assert result["total_count"] == 1 and result["covered_count"] == 0


def test_research_checksums_and_open_horizons_are_reproducible():
    from app.services.research_results import research_results
    result = research_results()
    assert len(result["manifest"]["input_sha256"]) == 64
    assert result["manifest"]["recommendation_events"] > 0
    open_horizons = [row for row in result["horizons"] if row["sessions"] == 63]
    assert all(row["observations"] == 0 and row["stock_net_pct"] is None for row in open_horizons)
    assert all(row["stock_net_pct"] is None or row["benchmark_net_pct"] is not None for row in result["horizons"])
