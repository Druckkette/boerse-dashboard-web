from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.services.portfolio_curve_prices import curve_price_requirements


@pytest.fixture(autouse=True)
def fixed_refresh_year(monkeypatch):
    from app.services import portfolio_curve_prices as service
    monkeypatch.setattr(service, "datetime", SimpleNamespace(now=lambda tz: datetime(2026, 10, 16, tzinfo=tz)))
    monkeypatch.setattr(service.archive, "archive_cached_inputs", lambda keys: 0)


def transaction(day, kind, quantity, ticker="TEST", isin="TEST", asset="STOCK"):
    return SimpleNamespace(date=date.fromisoformat(day), transaction_type=kind, shares=quantity,
        ticker=ticker, isin=isin, asset_class=asset, currency="EUR", raw_json={"event_ts": day}, price=100)


def test_refresh_keeps_prior_year_holdings_and_current_year_closed_history():
    rows = [transaction("2025-01-01", "buy", 2, "OLD", "OLD"),
        transaction("2025-02-01", "sell", 2, "OLD", "OLD"),
        transaction("2025-04-01", "buy", 3, "2318.HK", "HK"),
        transaction("2026-05-01", "buy", 2), transaction("2026-06-01", "sell", 2),
        transaction("2026-07-01", "buy", 3, "", "DERIV", "DERIVATIVE")]
    symbols, issuers = curve_price_requirements(rows, date(2026, 10, 16))
    assert "OLD" not in symbols
    assert symbols["2318.HK"] == date(2026, 10, 16)
    assert symbols["TEST"] == date(2026, 6, 1)
    assert "HKDUSD=X" in symbols
    assert "EURUSD=X" in symbols
    assert issuers == {"DERIV"}
    symbols, issuers = curve_price_requirements(rows, date(2027, 1, 1))
    assert "TEST" not in symbols
    assert symbols["2318.HK"] == date(2027, 1, 1)
    assert issuers == {"DERIV"}


def test_existing_basis_uses_incremental_refresh_and_missing_basis_is_repaired(monkeypatch):
    from app.services import portfolio_curve_prices as service
    rows = [transaction("2025-05-01", "buy", 1, "OLD", "OLD"), transaction("2026-01-02", "buy", 1, "NEW", "NEW")]
    monkeypatch.setattr(service.portfolio, "list_trade_republic_transactions", lambda: rows)
    monkeypatch.setattr(service, "curve_price_requirements", lambda rows, today: ({"OLD": today, "NEW": today}, set()))
    monkeypatch.setattr(service.prices, "list_price_bars_for_tickers", lambda *a, **k: {
        "OLD": [SimpleNamespace(date=date(2025, 12, 31))], "NEW": [SimpleNamespace(date=date(2026, 6, 1))]})
    calls = []
    def refresh(symbols, **kwargs):
        calls.append(([symbol.ticker for symbol in symbols], kwargs["incremental"]))
        return [{"ok": True} for symbol in symbols]
    monkeypatch.setattr(service, "refresh_price_cache_for_symbols", refresh)
    assert service.refresh_portfolio_curve_prices()["ok"]
    assert calls == [(["NEW"], False), (["OLD"], True)]


def test_complete_closed_position_needs_no_repeated_download(monkeypatch):
    from app.services import portfolio_curve_prices as service
    monkeypatch.setattr(service.portfolio, "list_trade_republic_transactions", lambda: [transaction("2026-01-02", "buy", 1)])
    monkeypatch.setattr(service, "curve_price_requirements", lambda rows, today: ({"TEST": date(2026, 6, 1)}, set()))
    monkeypatch.setattr(service.prices, "list_price_bars_for_tickers", lambda *a, **k: {"TEST": [SimpleNamespace(date=date(2026, 1, 2)), SimpleNamespace(date=date(2026, 6, 1))]})
    monkeypatch.setattr(service, "refresh_price_cache_for_symbols", lambda *a, **k: pytest.fail("Closed history is already covered"))
    assert service.refresh_portfolio_curve_prices()["ok"]


def test_archive_write_errors_remain_explicit_even_if_prices_are_current(monkeypatch):
    from app.services import portfolio_curve_prices as service
    monkeypatch.setattr(service.portfolio, "list_trade_republic_transactions", lambda: [])
    monkeypatch.setattr(service, "curve_price_requirements", lambda rows, today: ({"TEST": today}, set()))
    monkeypatch.setattr(service.prices, "list_price_bars_for_tickers", lambda *a, **k: {})
    monkeypatch.setattr(service, "refresh_price_cache_for_symbols", lambda *a, **k: [{"ok":True}])
    def broken(keys):
        raise RuntimeError("archive offline")
    monkeypatch.setattr(service.archive, "archive_cached_inputs", broken)
    result = service.refresh_portfolio_curve_prices()
    assert not result["ok"] and not result["archive_ok"]
    assert all(error.startswith("Archive:") for error in result["errors"])
