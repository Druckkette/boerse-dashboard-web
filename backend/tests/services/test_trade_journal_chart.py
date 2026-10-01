from datetime import date, timedelta
from types import SimpleNamespace

from app.services import trade_journal_chart as chart


def entry(day=date(2026, 9, 22), *, kind="sell", entry_id="sale", **values):
    return SimpleNamespace(id=entry_id, ticker="LPG", trade_date=day, entry_type=kind,
                           price=47.98, currency="EUR", shares=80, portfolio_snapshot_json={}, **values)


def bar(day, close=100.0):
    return SimpleNamespace(date=day, open=close, high=close + 1, low=close - 1, close=close,
                           adj_close=close, volume=1000)


def test_chart_stops_at_sale_and_keeps_original_quote_currency(monkeypatch):
    sale = entry()
    buy = entry(date(2026, 9, 17), kind="buy", entry_id="buy")
    future_buy = entry(date(2026, 9, 23), kind="buy", entry_id="future-buy")
    queries = []

    def prices(ticker, **kwargs):
        queries.append((ticker, kwargs))
        return [bar(date(2026, 9, 17)), bar(date(2026, 9, 21)),
                bar(date(2026, 9, 22)), bar(date(2026, 9, 23))]

    monkeypatch.setattr(chart.repository, "historical_price_bars", prices)
    result = chart.historical_chart(sale, [buy, sale, future_buy], {"data_as_of": "2026-09-21"})

    assert queries[0][1]["end_date"] == sale.trade_date
    assert result.currency == "USD"
    assert result.assessment_as_of == "2026-09-21"
    assert result.last_date == "2026-09-22"
    assert [point.date for point in result.points] == ["2026-09-17", "2026-09-21", "2026-09-22"]
    assert [marker.entry_id for marker in result.markers] == ["buy", "sale"]
    assert result.markers[1].currency == "EUR"
    assert result.markers[1].selected


def test_chart_moving_averages_use_warmup_and_deduplicate_sessions(monkeypatch):
    sale = entry()
    days = [sale.trade_date - timedelta(days=300 - index) for index in range(301)]
    bars = [bar(day, index + 1.0) for index, day in enumerate(days)]
    monkeypatch.setattr(chart.repository, "historical_price_bars", lambda *args, **kwargs: [bars[0], bar(days[0], 9999), *bars[1:]])

    result = chart.historical_chart(sale, [sale], {})

    assert result.first_date == (sale.trade_date - timedelta(days=186)).isoformat()
    assert len(result.points) == 187
    assert result.points[0].sma50 is not None
    assert result.points[0].sma200 is None
    assert result.points[-1].sma200 == sum(range(102, 302)) / 200
    assert result.points[-1].sma10 == sum(range(292, 302)) / 10


def test_chart_includes_long_held_buy_and_fifo_buy_without_related_entry(monkeypatch):
    sale = entry()
    sale.portfolio_snapshot_json = {"allocations": [{"buy_date": "2024-01-03", "shares": 80}]}
    monkeypatch.setattr(chart.repository, "historical_price_bars", lambda *args, **kwargs: [bar(date(2024, 1, 3)), bar(sale.trade_date)])

    result = chart.historical_chart(sale, [sale], {})

    assert result.first_date == "2024-01-03"
    assert result.markers[0].date == "2024-01-03"
    assert result.markers[0].entry_type == "buy"
    assert result.markers[0].price is None


def test_buy_chart_never_includes_its_later_sale(monkeypatch):
    buy = entry(date(2026, 9, 17), kind="buy", entry_id="buy")
    sale = entry()
    monkeypatch.setattr(chart.repository, "historical_price_bars", lambda *args, **kwargs: [bar(buy.trade_date), bar(sale.trade_date)])

    result = chart.historical_chart(buy, [buy, sale], {})

    assert result.assessment_as_of == "2026-09-16"
    assert result.last_date == "2026-09-17"
    assert len(result.markers) == 1


def test_chart_respects_stale_snapshot_and_prior_session_for_future_snapshot(monkeypatch):
    monkeypatch.setattr(chart.repository, "historical_price_bars", lambda *args, **kwargs: [])
    assert chart.historical_chart(entry(), [], {"data_as_of": "2026-09-18"}).assessment_as_of == "2026-09-18"
    assert chart.historical_chart(entry(), [], {"data_as_of": "2026-10-01"}).assessment_as_of == "2026-09-21"
    assert chart.historical_chart(entry(), [], {"data_as_of": "invalid"}).assessment_as_of == "2026-09-21"


def test_missing_chart_preserves_execution_markers(monkeypatch):
    monkeypatch.setattr(chart.repository, "historical_price_bars", lambda *args, **kwargs: [])
    result = chart.historical_chart(entry(), [entry()], {})
    assert result.points == []
    assert result.last_date is None
    assert result.markers[0].date == "2026-09-22"
    assert result.markers[0].price == 47.98
