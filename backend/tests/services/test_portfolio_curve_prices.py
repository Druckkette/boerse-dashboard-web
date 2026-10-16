from datetime import date
from types import SimpleNamespace

from app.services.portfolio_curve_prices import curve_price_requirements


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
