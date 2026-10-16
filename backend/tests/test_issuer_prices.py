from datetime import date
import pytest
from app.data_sources.issuer_prices import parse_issuer_history


def test_issuer_history_uses_product_bid_not_underlying_and_accepts_zero():
    source, bars = parse_issuer_history('TEST', {'product': {'Isin': 'TEST', 'Currency': 'EUR'}, 'history': [
        {'Date': '2026-01-02T00:00:00Z', 'Bid': 0, 'Ask': 2, 'UnderlyingPrice': 100},
        {'Date': '2026-01-03T00:00:00Z', 'Bid': 4},
    ]}, today=date(2026, 1, 2))
    assert source == 'societe_generale:EUR:bid'
    assert len(bars) == 1 and bars[0].close == 0
    assert bars[0].high is None and bars[0].volume is None


def test_vontobel_history_rejects_underlying_series_and_wrong_product():
    with pytest.raises(ValueError, match='matching issuer product'):
        parse_issuer_history('TEST', {'payload': {'series': [{'priceIdentifier': 'OTHER', 'isProduct': False, 'points': []}]}})


@pytest.mark.parametrize('currency,bid', [('USD', 1), ('EUR', -1), ('EUR', float('inf'))])
def test_issuer_history_validates_currency_and_values(currency, bid):
    with pytest.raises(ValueError):
        parse_issuer_history('TEST', {'product': {'Isin': 'TEST', 'Currency': currency}, 'history': [{'Date': '2026-01-02T00:00:00Z', 'Bid': bid}]})
