from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.schemas import PortfolioPosition
from app.services import portfolio


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 7, 8, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(portfolio, 'datetime', Clock)
    return Clock


def row():
    return SimpleNamespace(ticker='AAPL', current_price=110., shares=10., current_price_source='price_cache')


def bar(day, close, fetched=None):
    return SimpleNamespace(date=date.fromisoformat(day), close=close, fetched_at=fetched)


def position(**kwargs):
    return PortfolioPosition(ticker='AAPL', name='Apple', shares=10, entry_price=80, current_price=110,
                             market_value=1100, pnl_pct=37.5, weight_pct=100, status='ok', currency='USD', **kwargs)


@pytest.mark.parametrize('scale', [1, 10])
def test_daily_change_keeps_display_currency_and_quote_units_consistent(scale):
    result = portfolio._position_daily_change(row(), [bar('2026-10-05', 100 * scale), bar('2026-10-06', 110 * scale)])
    assert result['daily_pnl_abs'] == pytest.approx(100)
    assert result['daily_pnl_pct'] == pytest.approx(10)
    assert result['previous_close'] == pytest.approx(100)
    assert result['previous_close_date'] == '2026-10-05'
    assert result['price_as_of'] == '2026-10-06'


@pytest.mark.parametrize('points', [[], [bar('2026-10-06', 110)], [bar('2026-10-02', 100), bar('2026-10-06', 110)],
                                    [bar('2026-10-02', 100), bar('2026-10-05', 110)],
                                    [bar('2026-10-05', 0), bar('2026-10-06', 110)],
                                    [bar('2026-10-05', float('nan')), bar('2026-10-06', 110)],
                                    [bar('2026-10-05', 100, datetime(2026, 10, 5, 15, tzinfo=UTC)), bar('2026-10-06', 110)]])
def test_missing_stale_invalid_or_unfinished_reference_is_not_zero(points):
    assert portfolio._position_daily_change(row(), points) == {}


def test_import_entry_price_is_not_a_market_quote():
    item = row()
    item.current_price_source = 'position_entry'
    assert portfolio._position_daily_change(item, [bar('2026-10-05', 100), bar('2026-10-06', 110)]) == {}


def test_london_bank_holiday_uses_friday_reference(fixed_clock):
    fixed_clock.current = datetime(2026, 9, 2, 8, tzinfo=UTC)
    item = row()
    item.ticker = 'ARKK.L'
    result = portfolio._position_daily_change(item, [bar('2026-08-28', 100), bar('2026-09-01', 110)])
    assert result['previous_close_date'] == '2026-08-28'
    assert result['daily_pnl_abs'] == pytest.approx(100)


def test_portfolio_change_uses_weighted_prior_position_value():
    a = position(previous_close=100, daily_pnl_abs=100, daily_pnl_pct=10, price_as_of='2026-10-06')
    b = a.model_copy(update={'ticker': 'MSFT', 'shares': 20, 'previous_close': 200, 'daily_pnl_abs': -200, 'daily_pnl_pct': -5})
    kpi = portfolio._portfolio_daily_change_kpi([a, b], 'USD')
    assert kpi.value == '-100.00 USD'
    assert '-2.00%' in kpi.detail
    assert kpi.tone == 'bad'


def test_incomplete_or_mixed_currency_portfolio_does_not_show_partial_total():
    a = position(previous_close=100, daily_pnl_abs=100, daily_pnl_pct=10, price_as_of='2026-10-06')
    assert portfolio._portfolio_daily_change_kpi([a, position()], 'USD').value == 'n/a'
    assert portfolio._portfolio_daily_change_kpi([a, a.model_copy(update={'currency': 'EUR'})], 'EUR').value == 'n/a'
