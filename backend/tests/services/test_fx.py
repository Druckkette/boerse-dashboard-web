from datetime import date

from app.services import fx
from app.services.fx import FxRate


def test_yahoo_quote_currency_uses_listing_suffix() -> None:
    assert fx.yahoo_quote_currency("SIE.DE") == "EUR"
    assert fx.yahoo_quote_currency("1337.HK") == "HKD"
    assert fx.yahoo_quote_currency("NVDA") == "USD"


def test_non_euro_currency_rate_uses_cached_price_pair(monkeypatch) -> None:
    fx._cached_currency_usd.clear()
    monkeypatch.setattr(
        fx,
        "_latest_cached_fx_rate",
        lambda ticker, *, pair: FxRate(
            pair=pair,
            rate=0.128,
            as_of=date(2026, 7, 23),
            source=f"cache:{ticker}",
        ),
    )
    monkeypatch.setattr(
        fx,
        "_fetch_fx_rate",
        lambda ticker, *, pair: None,
    )

    rate = fx.get_currency_usd_rate("HKD")

    assert rate is not None
    assert rate.pair == "HKD/USD"
    assert rate.rate == 0.128
    assert rate.source == "cache:HKDUSD=X"


def test_currency_to_usd_returns_none_without_a_rate(monkeypatch) -> None:
    monkeypatch.setattr(fx, "get_currency_usd_rate", lambda currency: None)

    assert fx.currency_to_usd(100.0, "XYZ") is None
