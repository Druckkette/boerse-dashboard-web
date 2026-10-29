from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import threading
import time

import pytest

from app.core_config import Settings
from app.data_sources.marketaux import MarketauxFailure
from app.repositories import stock_news as repository
from app.repositories.stock_news import SymbolIdentity
from app.services import stock_news as service


NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


def article(symbol="NVDA", *, title=None, uuid="one", minutes=10, score=25):
    company = {"NVDA": "NVIDIA", "AAPL": "Apple", "TSLA": "Tesla"}.get(symbol, symbol)
    return {
        "uuid": uuid, "title": title or f"{company} raises quarterly dividend", "description": "Provider description.",
        "url": f"https://example.org/{uuid}", "source": "example.org",
        "published_at": (NOW - timedelta(minutes=minutes)).isoformat(),
        "entities": [{"symbol": symbol, "name": "NVIDIA Corporation",
                      "exchange": {"RHM.DE": "XETRA", "2318.HK": "HKEX"}.get(symbol, "NASDAQ"),
                      "match_score": score, "sentiment_score": .3}],
    }


class DurableFake:
    """A shared store survives service/client reconstruction; PG is tested separately."""
    def __init__(self, clock):
        self.clock = clock
        self.rows = {}
        self.calls = []
        self.guards = {}
        self.guard = threading.RLock()
        self.blocked_until = None
        self.blocked_reason = None
        self.blocked_credential = None

    @contextmanager
    def lock(self, key, **kwargs):
        with self.guard:
            guard = self.guards.setdefault(key, threading.Lock())
        with guard:
            yield self

    def read(self, key):
        return deepcopy(self.rows.get(key, {}))

    def write(self, key, value):
        self.rows[key] = deepcopy(value)

    def reserve(self, *, limit, credential_id):
        with self.guard:
            now = self.clock[0]
            self.calls = [stamp for stamp in self.calls if stamp > now - timedelta(days=1)]
            if self.blocked_until and now < self.blocked_until and self.blocked_credential == credential_id:
                return False, self.blocked_reason
            if len(self.calls) >= limit:
                return False, "limit_reached"
            self.calls.append(now)
            return True, "ok"

    def block(self, *, reason, seconds, credential_id):
        self.blocked_until = self.clock[0] + timedelta(seconds=seconds)
        self.blocked_reason = reason
        self.blocked_credential = credential_id


@pytest.fixture
def setup(monkeypatch):
    clock = [NOW]
    durable = DurableFake(clock)
    settings = Settings(marketaux_api_key="test-only-secret", marketaux_daily_limit=2)
    identities = {ticker: SymbolIdentity(ticker, ticker, name, "NASDAQ", True)
                  for ticker, name in [("NVDA", "NVIDIA Corporation"), ("AAPL", "Apple Inc."),
                                       ("TSLA", "Tesla Inc.")]}
    monkeypatch.setattr(service, "utc_now", lambda: clock[0])
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service.runtime_settings, "_read_runtime_config", lambda: {})
    monkeypatch.setattr(service.runtime_settings, "get_settings", lambda: service.get_settings())
    monkeypatch.delenv("MARKETAUX_API_KEY", raising=False)
    monkeypatch.setattr(repository, "resolve_symbol", identities.get)
    monkeypatch.setattr(repository, "locked_store", durable.lock)
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return [article(kwargs["symbol"])]

    monkeypatch.setattr(service, "fetch_news", fetch)
    return clock, durable, settings, calls


def test_cache_survives_repeated_reads_and_expires_after_one_hour(setup):
    clock, store, _, calls = setup
    first = service.get_stock_news("nvda")
    assert first.status == "ok" and not first.cached and first.ticker == "NVDA"
    assert first.updated_at == NOW
    clock[0] += timedelta(minutes=59)
    second = service.get_stock_news("NVDA")
    assert second.cached and second.updated_at == first.updated_at
    assert len(calls) == len(store.calls) == 1
    clock[0] += timedelta(minutes=2)
    third = service.get_stock_news("NVDA")
    assert not third.cached and third.updated_at > first.updated_at
    assert len(calls) == len(store.calls) == 2


def test_empty_results_have_shorter_persistent_cache(setup, monkeypatch):
    clock, store, _, calls = setup
    monkeypatch.setattr(service, "fetch_news", lambda **kw: calls.append(kw) or [])
    assert service.get_stock_news("NVDA").status == "empty"
    clock[0] += timedelta(minutes=9)
    assert service.get_stock_news("NVDA").cached
    assert len(calls) == 1
    clock[0] += timedelta(minutes=2)
    assert not service.get_stock_news("NVDA").cached
    assert len(store.calls) == 2


def test_simultaneous_same_ticker_requests_use_one_external_call(setup, monkeypatch):
    _, store, _, calls = setup

    def delayed(**kw):
        calls.append(kw)
        time.sleep(.04)
        return [article()]

    monkeypatch.setattr(service, "fetch_news", delayed)
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(service.get_stock_news, ["NVDA"] * 8))
    assert len(calls) == len(store.calls) == 1
    assert sum(not response.cached for response in responses) == 1
    assert all(response.articles[0].uuid == "one" for response in responses)


def test_quota_is_rolling_shared_across_tickers_and_keeps_existing_data(setup):
    clock, store, _, calls = setup
    original = service.get_stock_news("NVDA")
    service.get_stock_news("AAPL")
    assert service.get_stock_news("TSLA").status == "limit_reached"
    clock[0] += timedelta(hours=2)
    limited = service.get_stock_news("NVDA")
    assert limited.status == "stale" and limited.articles == original.articles
    assert limited.updated_at == original.updated_at and len(calls) == 2
    clock[0] += timedelta(hours=22, seconds=1)
    assert service.get_stock_news("TSLA").status == "ok"
    assert len(calls) == 3 and len(store.calls) == 1


def test_changing_ticker_never_reuses_other_company_cache(setup):
    _, _, _, calls = setup
    assert service.get_stock_news("NVDA").articles[0].entities[0].symbol == "NVDA"
    assert service.get_stock_news("AAPL").articles[0].entities[0].symbol == "AAPL"
    assert service.get_stock_news("NVDA").cached
    assert [request["symbol"] for request in calls] == ["NVDA", "AAPL"]


@pytest.mark.parametrize("reason", ["not_configured", "limit_reached", "unavailable"])
def test_failed_attempt_counts_and_backoff_is_global_with_stale_fallback(setup, monkeypatch, reason):
    clock, store, _, calls = setup
    original = service.get_stock_news("NVDA")
    clock[0] += timedelta(hours=2)

    def failed(**kw):
        calls.append(kw)
        raise MarketauxFailure(reason, 600)

    monkeypatch.setattr(service, "fetch_news", failed)
    result = service.get_stock_news("NVDA")
    assert result.status == "stale" and result.articles == original.articles
    assert result.updated_at == original.updated_at
    assert "test-only-secret" not in result.model_dump_json()
    assert service.get_stock_news("NVDA").status == "stale"
    assert service.get_stock_news("AAPL").status == reason
    assert len(calls) == len(store.calls) == 2


def test_missing_key_serves_existing_cache_without_external_request(setup, monkeypatch):
    clock, store, _, calls = setup
    service.get_stock_news("NVDA")
    monkeypatch.setattr(service, "get_settings", lambda: Settings(marketaux_api_key=""))
    assert service.get_stock_news("NVDA").status == "ok"
    clock[0] += timedelta(hours=2)
    assert service.get_stock_news("NVDA").status == "stale"
    assert service.get_stock_news("AAPL").status == "not_configured"
    assert len(calls) == len(store.calls) == 1


def test_no_known_identity_or_invalid_ticker_never_spends_quota(setup):
    _, store, _, calls = setup
    for ticker in ("UNKNOWN", "../AAPL", "AAPL?api_token=fake", "A" * 33):
        assert service.get_stock_news(ticker).status == "unsupported"
    assert not calls and not store.calls


def test_storage_outage_fails_closed_without_provider_request(setup, monkeypatch):
    _, _, _, calls = setup

    def fail(*args, **kwargs):
        raise repository.NewsRepositoryUnavailable("private database detail")

    monkeypatch.setattr(repository, "locked_store", fail)
    response = service.get_stock_news("NVDA")
    assert response.status == "unavailable"
    assert "private database" not in response.model_dump_json()
    assert not calls


def test_language_change_invalidates_variant_and_empty_disables_filter(setup):
    _, _, settings, calls = setup
    service.get_stock_news("NVDA")
    settings.marketaux_languages = ""
    service.get_stock_news("NVDA")
    assert [request["languages"] for request in calls] == ["de,en", ""]


def test_provider_mapping_preserves_foreign_exchange_and_us_class_shares():
    assert service.provider_symbol(SymbolIdentity("BRK-B", "BRK-B", "Berkshire", "NYSE", True)) == "BRK.B"
    assert service.provider_symbol(SymbolIdentity("RHM.DE", "RHM.DE", "Rheinmetall", "XETRA")) == "RHM.DE"
    assert service.provider_symbol(SymbolIdentity("2318-HK", "2318.HK", "Ping An", "HK")) == "2318.HK"
    assert service.provider_symbol(SymbolIdentity("NA", "NA", "Nano Labs", "NASDAQ", True)) == "NA"


def test_article_projection_sorting_deduplication_and_three_item_limit():
    identity = SymbolIdentity("NVDA", "NVDA", "NVIDIA Corporation", "NASDAQ", True)
    rows = [
        article(uuid="old", title="NVIDIA opens new research laboratory", minutes=80),
        article(uuid="latest", title="NVIDIA announces chip supply agreement", minutes=1),
        article(uuid="duplicate-title", title="NVIDIA announces chip supply agreement!", minutes=2),
        article(uuid="earnings", title="NVIDIA quarterly earnings beat expectations", minutes=3),
        article(uuid="dividend", title="NVIDIA board approves quarterly dividend", minutes=4),
        article("AAPL", uuid="wrong-company", title="Apple releases new phone", minutes=0),
        {**article(uuid="bad-date"), "published_at": "not-a-date"},
        {**article(uuid="bad-url"), "url": "javascript:alert(1)"},
        {**article(uuid="bad-entities"), "entities": 123},
        {**article(uuid="bad-text"), "title": {"unexpected": "object"}},
    ]
    result = service.parse_articles(rows, identity, min_match_score=10, now=NOW)
    assert [item.uuid for item in result] == ["latest", "earnings", "dividend"]
    assert result[0].match_score == 25 and result[0].sentiment_score == .3
    assert all(item.entities[0].symbol == "NVDA" for item in result)


def test_incidental_mentions_and_wrong_listing_are_filtered_but_title_mentions_remain():
    identity = SymbolIdentity("RHM.DE", "RHM.DE", "Rheinmetall AG", "XETRA")
    rows = [article("RHM", uuid="wrong-exchange"), article("RHM.DE", uuid="incidental", score=1,
             title="Broad markets trade lower"), article("RHM.DE", uuid="direct", score=1,
             title="Rheinmetall announces new contract")]
    result = service.parse_articles(rows, identity, min_match_score=10, now=NOW)
    assert [item.uuid for item in result] == ["direct"]


def test_article_echoed_secret_and_nonfinite_scores_never_reach_browser():
    identity = SymbolIdentity("NVDA", "NVDA", "NVIDIA", "NASDAQ", True)
    bad = {**article(), "description": "echo test-only-secret"}
    valid = article(uuid="valid", title="NVIDIA shares rise", score=float("nan"))
    valid["entities"][0]["sentiment_score"] = float("inf")
    result = service.parse_articles([bad, valid], identity, min_match_score=10, now=NOW,
                                    api_key="test-only-secret")
    assert len(result) == 1 and result[0].uuid == "valid"
    assert result[0].match_score is None and result[0].sentiment_score is None


def test_settings_hide_secret_and_validate_language_codes():
    settings = Settings(marketaux_api_key="test-only-secret", marketaux_languages="en, de, en")
    assert "test-only-secret" not in repr(settings)
    assert settings.marketaux_languages == "de,en"
    assert Settings(marketaux_languages="").marketaux_languages == ""
    with pytest.raises(ValueError):
        Settings(marketaux_languages="en&api_token=bad")


def test_key_rotation_clears_auth_backoff_but_never_resets_consumed_quota(setup, monkeypatch):
    _, store, _, calls = setup

    def invalid(**kw):
        calls.append(kw)
        raise MarketauxFailure("not_configured", 3600)

    monkeypatch.setattr(service, "fetch_news", invalid)
    assert service.get_stock_news("NVDA").status == "not_configured"
    assert service.get_stock_news("AAPL").status == "not_configured"
    assert len(calls) == 1
    monkeypatch.setattr(service, "get_settings", lambda: Settings(
        marketaux_api_key="different-test-only-secret", marketaux_daily_limit=2))
    monkeypatch.setattr(service, "fetch_news", lambda **kw: calls.append(kw) or [article(kw["symbol"])])
    assert service.get_stock_news("AAPL").status == "ok"
    assert service.get_stock_news("TSLA").status == "limit_reached"
    assert len(calls) == len(store.calls) == 2


def test_duplicates_by_uuid_and_tracking_urls_are_removed():
    identity = SymbolIdentity("NVDA", "NVDA", "NVIDIA", "NASDAQ", True)
    first = article(uuid="same", title="NVIDIA expands its research center", minutes=1)
    duplicate_id = article(uuid="same", title="Chip supplier builds another factory", minutes=2)
    duplicate_id["description"] = "NVIDIA describes its expansion plan."
    duplicate_url = {**article(uuid="different", title="New data center architecture unveiled", minutes=3),
                     "url": first["url"] + "?utm_source=newsletter", "description": "NVIDIA presents its architecture."}
    result = service.parse_articles([duplicate_id, duplicate_url, first], identity, min_match_score=10, now=NOW)
    assert [item.uuid for item in result] == ["same"]


def test_saved_ui_key_changes_are_used_immediately_and_do_not_reset_quota(setup, monkeypatch):
    _, durable, _, calls = setup
    stored = {"MARKETAUX_API_KEY": "test-only-first-ui-key"}
    monkeypatch.setattr(service.runtime_settings, "_read_runtime_config", lambda: dict(stored))
    assert service.get_stock_news("NVDA").status == "ok"
    assert calls[-1]["api_key"] == "test-only-first-ui-key"
    stored["MARKETAUX_API_KEY"] = "test-only-second-ui-key"
    assert service.get_stock_news("AAPL").status == "ok"
    assert calls[-1]["api_key"] == "test-only-second-ui-key"
    stored.clear()
    assert service.get_stock_news("TSLA").status == "limit_reached"
    assert len(calls) == len(durable.calls) == 2
    assert service.get_stock_news("NVDA").cached


def test_removed_ui_key_stops_new_fetches_but_keeps_fresh_cached_articles(setup, monkeypatch):
    _, durable, _, calls = setup
    stored = {"MARKETAUX_API_KEY": "test-only-ui-key"}
    monkeypatch.setattr(service.runtime_settings, "_read_runtime_config", lambda: dict(stored))
    monkeypatch.setattr(service, "get_settings", lambda: Settings(marketaux_api_key=""))
    assert service.get_stock_news("NVDA").status == "ok"
    stored.clear()
    assert service.get_stock_news("AAPL").status == "not_configured"
    assert service.get_stock_news("NVDA").status == "ok"
    assert len(calls) == len(durable.calls) == 1


def test_other_company_press_release_is_rejected_despite_strong_body_match_score():
    identity = SymbolIdentity("NVDA", "NVDA", "NVIDIA Corporation", "NASDAQ", True)
    incidental = article(uuid="pasqal", title="Pasqal Announces Third-Quarter 2026 Business Update and Participation in Upcoming Investor Conferences", score=80)
    incidental["description"] = "Pasqal announced its third-quarter business update and investor conferences."
    incidental["entities"][0]["highlights"] = [{"highlighted_in": "main_text", "highlight": "Pasqal uses NVIDIA components."}]
    assert service.parse_articles([incidental], identity, min_match_score=10, now=NOW) == []


def test_direct_title_description_and_entity_title_highlight_are_accepted():
    identity = SymbolIdentity("NVDA", "NVDA", "NVIDIA Corporation", "NASDAQ", True)
    title = article(uuid="title", title="NVIDIA sets conference call for financial results", score=1, minutes=1)
    description = article(uuid="description", title="Quarterly chip outlook improves", minutes=2)
    description["description"] = "NVIDIA announces an expanded production outlook."
    highlight = article(uuid="highlight", title="Graphics leader introduces new product line", score=1, minutes=3)
    highlight["entities"][0]["highlights"] = [{"highlighted_in": "title", "highlight": "Graphics leader"}]
    wrong = article("AAPL", uuid="wrong", title="NVIDIA participates in industry event", minutes=0)
    result = service.parse_articles([wrong, highlight, description, title], identity, min_match_score=10, now=NOW)
    assert [row.uuid for row in result] == ["title", "description", "highlight"]


def test_near_company_names_and_generic_leading_words_do_not_qualify():
    apple = SymbolIdentity("AAPL", "AAPL", "Apple Inc.", "NASDAQ", True)
    lookalike = article("AAPL", title="Appleton company announces new facility", score=90)
    assert service.parse_articles([lookalike], apple, min_match_score=10, now=NOW) == []
    trade = SymbolIdentity("TTD", "TTD", "The Trade Desk, Inc.", "NASDAQ", True)
    generic = article("TTD", title="Trade policy changes affect global supply chains", score=90)
    assert service.parse_articles([generic], trade, min_match_score=10, now=NOW) == []
    direct = article("TTD", title="The Trade Desk announces quarterly revenue", score=90)
    assert len(service.parse_articles([direct], trade, min_match_score=10, now=NOW)) == 1


def test_news_quality_version_separates_previous_weak_cache_variants():
    import hashlib
    import json
    identity = SymbolIdentity("NVDA", "NVDA", "NVIDIA", "NASDAQ", True)
    settings = Settings()
    old_variant = json.dumps(["NVDA", settings.marketaux_languages, settings.marketaux_min_match_score, "NVIDIA", True])
    previous = "marketaux:news:v1:" + hashlib.sha256(old_variant.encode()).hexdigest()
    assert service.news_cache_key(identity, settings) != previous
    assert service.NEWS_QUALITY_VERSION == "company-intro-v3"


def test_provider_timeout_default_allows_observed_cold_queries_and_cache_never_exceeds_one_hour():
    assert Settings().marketaux_request_timeout_seconds == 15
    with pytest.raises(ValueError):
        Settings(marketaux_cache_ttl_seconds=3601)


@pytest.mark.parametrize("country,exchange,accepted", [
    ("ca", "TSX", False), (None, "TSX", False), ("us", "NASDAQ", True),
    (None, "NASDAQ", True), (None, None, True), ("unknown", "UNKNOWN", True),
])
def test_ambiguous_na_symbol_rejects_explicit_foreign_listing(country, exchange, accepted):
    identity = SymbolIdentity("NA", "NA", "Nano Labs Ltd", "NASDAQ", True)
    row = article("NA", title="Nano Labs announces new product")
    row["entities"][0].update(country=country, exchange=exchange)
    result = service.parse_articles([row], identity, min_match_score=10, now=NOW)
    assert bool(result) is accepted


def test_foreign_qualified_mapping_checks_country_and_cache_tracks_exchange():
    identity = SymbolIdentity("BABA", "9988.HK", "Alibaba Group", "NASDAQ", False)
    row = article("9988.HK", title="Alibaba announces quarterly results")
    row["entities"][0].update(country="hk", exchange="HKEX")
    assert service.parse_articles([row], identity, min_match_score=10, now=NOW)
    row["entities"][0]["country"] = "us"
    assert not service.parse_articles([row], identity, min_match_score=10, now=NOW)
    settings = Settings()
    other_venue = SymbolIdentity("BABA", "9988.HK", "Alibaba Group", "HKEX", False)
    assert service.news_cache_key(identity, settings) != service.news_cache_key(other_venue, settings)


@pytest.mark.parametrize("source,symbol,is_us", [("BABA", "9988.HK", False), ("BRK-B", "BRK-B", True)])
def test_resolver_foreign_override_wins_over_us_source_but_class_share_stays_us(monkeypatch, source, symbol, is_us):
    from types import SimpleNamespace

    class Session:
        def __enter__(self):
            self.rows = iter([SimpleNamespace(name="Company", yahoo_symbol=source, exchange="NYSE",
                                              metadata_json={"nasdaq_listing": {"exchange": "NYSE"}}),
                              SimpleNamespace(yahoo_symbol=symbol)])
            return self

        def __exit__(self, *args):
            pass

        def scalars(self, statement):
            return SimpleNamespace(first=lambda: next(self.rows))

    monkeypatch.setattr(repository, "SessionLocal", Session)
    identity = repository.resolve_symbol(source)
    assert identity.us_listing is is_us and identity.symbol == symbol
    assert service.provider_symbol(identity) == ("BRK.B" if is_us else "9988.HK")
