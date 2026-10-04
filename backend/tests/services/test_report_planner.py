from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.services import report_planner as planner


def test_planner_covers_every_freshness_ticker_and_skips_etfs(monkeypatch):
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def scalars(self, query):
            return SimpleNamespace(all=lambda: [])

    queued = []
    monkeypatch.setattr(planner, 'SessionLocal', Session)
    monkeypatch.setattr(planner, '_tracked_fundamental_tickers', lambda db: ['EC', 'PNDRY', 'ARKK.L', 'ZPDH.DE'])
    monkeypatch.setattr(planner.portfolio, 'list_open_positions', lambda: [SimpleNamespace(ticker='CLS')])
    monkeypatch.setattr(planner.universes, 'list_universe_tickers', lambda **kwargs: ['NYT'])
    previous = SimpleNamespace(as_of=date.today(), metadata_json={}, beta=1.0, fiscal_period='2026 Q2')
    monkeypatch.setattr(planner.fundamentals, 'get_latest_fundamentals_for_tickers', lambda tickers: {t: previous for t in tickers})
    monkeypatch.setattr(planner.fundamentals, 'get_instrument_profiles_for_tickers', lambda tickers: {})
    monkeypatch.setattr(planner.fundamentals, '_missing_required_history_keys', lambda metadata: [])
    monkeypatch.setattr(planner, 'enqueue', lambda requests: queued.extend(requests) or len(requests))
    monkeypatch.setattr(planner, 'record_provider_event', lambda *args: None)

    planner.plan_report_work(include_sec13f=False)

    statements = {item.ticker: item for item in queued if item.data_group == 'statements'}
    assert set(statements) == {'CLS', 'EC', 'PNDRY', 'NYT'}
    assert statements['CLS'].priority == 10
    assert statements['EC'].priority == statements['PNDRY'].priority == 20
    assert statements['NYT'].priority == 60
    assert statements['EC'].due_at == datetime.combine(date.today(), datetime.min.time(), UTC) + timedelta(days=13)
