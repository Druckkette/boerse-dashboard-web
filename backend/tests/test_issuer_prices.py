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


def test_fixed_redemption_requires_matching_identity_and_explicit_final_fixing():
    from app.data_sources.issuer_product import vontobel_redemption
    payload = {"data": {"isin": "TEST", "currency": "EUR", "isEndOfLifeComplete": True},
        "disclaimers": [{"repaymentPrice": 3.91, "currency": "EUR", "repaymentDate": "2026-02-13T00:00:00"}],
        "lifeCycle": [{"type": 7, "occurrence": "2026-02-06T22:10:00"}]}
    result = vontobel_redemption("TEST", payload)
    assert result["amount"] == 3.91
    assert result["valuation_date"] == "2026-02-06"
    assert result["payment_date"] == "2026-02-13"
    with pytest.raises(ValueError, match="identity"):
        vontobel_redemption("OTHER", payload)
    payload["lifeCycle"] = []
    assert vontobel_redemption("TEST", payload) is None


def test_sg_final_bid_uses_quote_date_and_rejects_intraday_or_future_snapshots():
    from datetime import UTC, datetime
    from app.data_sources.issuer_product import sg_final_bid
    product = {"Currency": "EUR"}
    fields = [{"Name": "Bid", "Value": 0.001, "Suffix": " EUR"},
              {"Name": "TimeStamp", "Value": "2026-10-16T19:57:10.297"}]
    close = sg_final_bid(product, fields, now=datetime(2026, 10, 16, 21, tzinfo=UTC))
    assert close.date == date(2026, 10, 16)
    assert close.close == 0.001
    assert sg_final_bid(product, fields, now=datetime(2026, 10, 16, 19, tzinfo=UTC)) is None
    # The same old observed quote remains on October 16, never October 19.
    assert sg_final_bid(product, fields, now=datetime(2026, 10, 19, 21, tzinfo=UTC)).date == date(2026, 10, 16)
    fields[1]["Value"] = "2026-10-16T10:00:00"
    assert sg_final_bid(product, fields, now=datetime(2026, 10, 16, 21, tzinfo=UTC)) is None
