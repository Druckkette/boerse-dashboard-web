"""Actual PostgreSQL locks, durable reservation and shared caches; no provider I/O."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
import threading
import time

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core_config import Settings
from app.db.models import AppSetting, Instrument, UniverseSymbolMapping
from app.repositories import stock_news as repository
from app.services import stock_news as service


pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Disposable Postgres not configured")
TEST_TICKERS = ["TSTNEWSA", "TSTNEWSB", "TSTNEWSC"]


@pytest.fixture
def database(monkeypatch):
    url = os.environ["TEST_POSTGRES_URL"]
    assert make_url(url).database == "audit_tests", "Never run against an application database"
    # A two-connection pool also detects designs that hold one lock connection
    # while borrowing a second one for quota/cache writes.
    engine = create_engine(url, pool_size=2, max_overflow=0, pool_timeout=3)
    for model in (AppSetting, Instrument, UniverseSymbolMapping):
        model.__table__.create(engine, checkfirst=True)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(repository, "engine", engine)
    monkeypatch.setattr(repository, "SessionLocal", sessions)
    monkeypatch.setattr(service.runtime_settings.settings_repository, "SessionLocal", sessions)

    def clean():
        with sessions() as db:
            db.execute(delete(AppSetting).where(AppSetting.key.like("marketaux:%")))
            db.execute(delete(UniverseSymbolMapping).where(UniverseSymbolMapping.source_ticker.in_(TEST_TICKERS)))
            db.execute(delete(Instrument).where(Instrument.ticker.in_(TEST_TICKERS)))
            db.commit()

    clean()
    with sessions() as db:
        db.add_all([Instrument(ticker=ticker, yahoo_symbol=ticker, name=ticker,
                               exchange="NASDAQ", currency="USD") for ticker in TEST_TICKERS])
        db.commit()
    monkeypatch.setattr(service, "get_settings", lambda: Settings(marketaux_api_key="test-only-secret"))
    monkeypatch.setattr(service.runtime_settings, "get_settings", lambda: service.get_settings())
    monkeypatch.delenv("MARKETAUX_API_KEY", raising=False)
    yield engine, sessions
    clean()
    engine.dispose()


def provider_article(symbol):
    return {"uuid": symbol + "-one", "title": symbol + " quarterly earnings",
            "url": "https://example.org/" + symbol, "source": "example.org",
            "published_at": service.utc_now().isoformat(),
            "entities": [{"symbol": symbol, "name": symbol, "match_score": 30}]}


def test_concurrent_same_symbol_fetches_once_and_cache_survives_new_connections(database, monkeypatch):
    engine, sessions = database
    calls = []

    def fetch(**kw):
        calls.append(kw["symbol"])
        time.sleep(.1)
        return [provider_article(kw["symbol"])]

    monkeypatch.setattr(service, "fetch_news", fetch)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(service.get_stock_news, [TEST_TICKERS[0]] * 6))
    assert calls == [TEST_TICKERS[0]]
    assert sum(not result.cached for result in results) == 1
    assert all(result.articles[0].uuid == TEST_TICKERS[0] + "-one" for result in results)
    engine.dispose()
    assert service.get_stock_news(TEST_TICKERS[0]).cached
    assert len(calls) == 1
    with sessions() as db:
        assert len(db.get(AppSetting, repository.BUDGET_KEY).value_json["attempts"]) == 1
        assert db.scalar(text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=:ns"),
                         {"ns": repository.NAMESPACE}) == 0


def test_different_symbols_do_not_exhaust_pool_with_nested_quota_connections(database, monkeypatch):
    reached = threading.Barrier(2)

    def fetch(**kw):
        reached.wait(timeout=5)
        return [provider_article(kw["symbol"])]

    monkeypatch.setattr(service, "fetch_news", fetch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.get_stock_news, TEST_TICKERS[:2]))
    assert [result.ticker for result in results] == TEST_TICKERS[:2]
    assert all(result.status == "ok" for result in results)


def test_global_last_quota_slot_is_reserved_atomically_across_symbols(database, monkeypatch):
    _, sessions = database
    calls = []
    monkeypatch.setattr(service, "get_settings", lambda: Settings(marketaux_api_key="test-only-secret", marketaux_daily_limit=1))
    monkeypatch.setattr(service, "fetch_news", lambda **kw: calls.append(kw["symbol"]) or [provider_article(kw["symbol"])])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.get_stock_news, TEST_TICKERS[:2]))
    assert len(calls) == 1
    assert sorted(result.status for result in results) == ["limit_reached", "ok"]
    with sessions() as db:
        assert len(db.get(AppSetting, repository.BUDGET_KEY).value_json["attempts"]) == 1


def test_reservation_survives_failure_before_request_and_fresh_connection(database):
    engine, _ = database
    with pytest.raises(RuntimeError):
        with repository.locked_store("marketaux:test-crash") as store:
            assert store.reserve(limit=1, credential_id="test-key") == (True, "ok")
            raise RuntimeError("Simulated failure after durable reservation, before HTTP")
    engine.dispose()
    with repository.locked_store("marketaux:test-next") as store:
        assert store.reserve(limit=1, credential_id="test-key") == (False, "limit_reached")


def test_rolling_window_expires_only_attempts_older_than_twenty_four_hours(database):
    with repository.locked_store("marketaux:test-clock") as store:
        now = store.db.scalar(text("SELECT clock_timestamp()"))
        store.write(repository.BUDGET_KEY, {"attempts": [
            (now - timedelta(hours=25)).isoformat(), (now - timedelta(hours=23)).isoformat(),
        ]})
        assert store.reserve(limit=1, credential_id="test-key") == (False, "limit_reached")
        assert store.reserve(limit=2, credential_id="test-key") == (True, "ok")
        assert len(store.read(repository.BUDGET_KEY)["attempts"]) == 2


def test_existing_symbol_mapping_and_marketaux_override_are_used_without_suffix_stripping(database):
    _, sessions = database
    with sessions() as db:
        instrument = db.scalars(select(Instrument).where(Instrument.ticker == TEST_TICKERS[0])).one()
        instrument.yahoo_symbol = "2318.HK"
        instrument.exchange = "HKEX"
        db.add(UniverseSymbolMapping(universe_key="us_common_stocks", source_ticker=TEST_TICKERS[0],
                                    yahoo_symbol="RHM.DE", status="active", source="manual"))
        db.commit()
    identity = repository.resolve_symbol(TEST_TICKERS[0])
    assert identity.symbol == "RHM.DE" and not identity.us_listing
    with sessions() as db:
        instrument = db.scalars(select(Instrument).where(Instrument.ticker == TEST_TICKERS[0])).one()
        instrument.metadata_json = {"marketaux_symbol": "2318.HK"}
        db.commit()
    assert repository.resolve_symbol(TEST_TICKERS[0]).symbol == "2318.HK"
