"""On-demand, quota-protected company news using the existing durable cache."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
import hashlib
import html
import json
import math
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core_config import get_settings
from app.data_sources.marketaux import MarketauxFailure, fetch_news
from app.repositories import stock_news as repository
from app.schemas_news import NewsArticle, NewsEntity, StockNewsResponse
from app.services import settings as runtime_settings


MESSAGES = {
    "not_configured": "Nachrichten sind derzeit nicht konfiguriert.",
    "limit_reached": "Das Nachrichten-Abruflimit ist erreicht. Gespeicherte Meldungen bleiben verfügbar.",
    "unavailable": "Nachrichten sind derzeit nicht erreichbar. Bitte später erneut versuchen.",
    "unsupported": "Für dieses Symbol ist keine eindeutige Unternehmenszuordnung verfügbar.",
}
NEWS_QUALITY_VERSION = "company-intro-v3"


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_date(value) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo else result.replace(tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value, *, sentiment=False) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        if not math.isfinite(number) or (sentiment and not -1 <= number <= 1):
            return None
        return number
    except (ValueError, TypeError, OverflowError):
        return None


def _text(value, limit=1000) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", value))).strip()[:limit]


def provider_symbol(identity: repository.SymbolIdentity) -> str:
    symbol = identity.symbol
    if identity.us_listing and re.fullmatch(r"[A-Z]{1,5}-[A-Z]", symbol):
        return symbol.replace("-", ".")
    return symbol


def _aliases(identity) -> set[str]:
    symbol = provider_symbol(identity)
    result = {symbol}
    if identity.us_listing and re.fullmatch(r"[A-Z]{1,5}\.[A-Z]", symbol):
        result.add(symbol.replace(".", "-"))
    return result


def _title_mentions_company(title: str, identity) -> bool:
    name = identity.name.split(" - ")[0]
    tokens = [word for word in re.findall(r"[\w]+", name.lower())
              if len(word) > 2 and word not in {
                  "corporation", "company", "limited", "common", "stock", "shares", "class",
                  "ordinary", "inc", "corp", "ltd", "holdings", "holding", "plc", "the",
              }]
    words = re.findall(r"[\w]+", title.casefold())
    # Match whole words, never a substring such as Apple in Appleton. For generic
    # leading words, require the company phrase rather than e.g. "Trade" alone.
    generic = {"advanced", "american", "bank", "capital", "central", "financial", "first",
               "global", "international", "micro", "national", "new", "trade", "united"}
    company = bool(tokens and (
        (tokens[0] not in generic and tokens[0] in words)
        or re.search(r"(?<!\w)" + re.escape(" ".join(tokens)) + r"(?!\w)", " ".join(words))
    ))
    symbols = any(re.search(
        (r"(?:\$" + re.escape(symbol) + r"(?!\w)|\(" + re.escape(symbol) + r"\))")
        if len(symbol) <= 2 else r"(?<![\w.])" + re.escape(symbol) + r"(?![\w.])",
        title, re.IGNORECASE,
    ) for symbol in _aliases(identity))
    return company or symbols


def news_cache_key(identity, settings) -> str:
    variant = json.dumps([NEWS_QUALITY_VERSION, provider_symbol(identity), settings.marketaux_languages,
                          settings.marketaux_min_match_score, identity.name, identity.us_listing,
                          identity.exchange.upper()])
    return "marketaux:news:v1:" + hashlib.sha256(variant.encode()).hexdigest()


def _listing_matches(entity: dict, identity) -> bool:
    expected = repository.foreign_listing_country(identity.symbol) or ("us" if identity.us_listing else None)
    if expected is None:
        return True
    country = str(entity.get("country") or "").strip().lower()
    country = {"uk": "gb", "usa": "us", "united states": "us", "canada": "ca",
               "germany": "de", "hong kong": "hk", "united kingdom": "gb"}.get(country, country)
    if re.fullmatch(r"[a-z]{2}", country) and country not in {"xx", "zz"}:
        return country == expected
    # Unknown/missing metadata is not a rejection. Only unmistakable exchange
    # contradictions are considered when no usable exchange-country is supplied.
    exchange = re.sub(r"[^A-Z0-9]", "", str(entity.get("exchange") or "").upper())
    venue_country = {
        "NASDAQ": "us", "NYSE": "us", "NYSEARCA": "us", "AMEX": "us", "BATS": "us",
        "TSX": "ca", "TSXV": "ca", "TORONTOSTOCKEXCHANGE": "ca",
        "LSE": "gb", "LONDONSTOCKEXCHANGE": "gb", "HKEX": "hk", "HKG": "hk",
        "XETRA": "de", "FRA": "de", "FRANKFURTSTOCKEXCHANGE": "de", "ASX": "au",
    }.get(exchange)
    return venue_country is None or venue_country == expected


def _article_url(value) -> str | None:
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password
                or any(key.lower() == "api_token" for key, _ in parse_qsl(parsed.query))):
            return None
        return value
    except ValueError:
        return None


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    query = [(key, val) for key, val in parse_qsl(parsed.query)
             if not key.lower().startswith("utm_") and key.lower() not in {"ref", "fbclid", "gclid"}]
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(query), ""))


def parse_articles(rows, identity, *, min_match_score: float, now: datetime, api_key="") -> list[NewsArticle]:
    aliases = _aliases(identity)
    candidates = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        # Provider responses are never returned raw. Reject echoed credentials
        # even in malformed article fields before projecting the public payload.
        if api_key and api_key in json.dumps(raw, ensure_ascii=False):
            continue
        title = _text(raw.get("title"))
        description = _text(raw.get("description"), 1500)
        url = _article_url(raw.get("url"))
        published = parse_date(raw.get("published_at"))
        uuid = _text(raw.get("uuid"), 128)
        if not title or not uuid or not url or not published or published > now + timedelta(minutes=5):
            continue
        raw_entities = raw.get("entities")
        if not isinstance(raw_entities, list):
            continue
        matches = [entity for entity in raw_entities
                   if isinstance(entity, dict) and str(entity.get("symbol", "")).upper() in aliases
                   and _listing_matches(entity, identity)]
        if not matches:
            continue
        entities = []
        direct_title = _title_mentions_company(title, identity)
        direct_description = _title_mentions_company(description, identity)
        for entity in matches:
            score = _number(entity.get("match_score"))
            highlights = entity.get("highlights")
            title_highlight = isinstance(highlights, list) and any(
                isinstance(highlight, dict) and highlight.get("highlighted_in") == "title"
                and _text(highlight.get("highlight"))
                for highlight in highlights)
            # A strong body-only entity score can still be incidental. In
            # particular, another company's press release must not fill a slot.
            if not (direct_title or direct_description or title_highlight):
                continue
            if (score is not None and score < min_match_score
                    and not title_highlight and not direct_title):
                continue
            entities.append(NewsEntity(
                symbol=str(entity["symbol"]).upper(), name=_text(entity.get("name"), 255),
                exchange=_text(entity.get("exchange"), 80) or None, match_score=score,
                sentiment_score=_number(entity.get("sentiment_score"), sentiment=True),
            ))
        if not entities:
            continue
        best = max(entities, key=lambda item: item.match_score if item.match_score is not None else -math.inf)
        candidates.append(NewsArticle(
            uuid=uuid, title=title, description=description or None,
            url=url, source=_text(raw.get("source"), 255) or urlsplit(url).hostname or "",
            published_at=published, entities=entities, match_score=best.match_score,
            sentiment_score=best.sentiment_score,
        ))
    candidates.sort(key=lambda article: (article.published_at, article.uuid), reverse=True)
    result = []
    for article in candidates:
        normalized = " ".join(re.findall(r"\w+", article.title.casefold()))
        if any(article.uuid == old.uuid or _canonical_url(article.url) == _canonical_url(old.url)
               or SequenceMatcher(None, normalized, " ".join(re.findall(r"\w+", old.title.casefold()))).ratio() >= .9
               for old in result):
            continue
        result.append(article)
        if len(result) == 3:
            break
    return result


def _response(ticker: str, state: dict, *, reason: str | None = None, cached: bool = True):
    if reason is not None and reason not in MESSAGES:
        reason = "unavailable"
    try:
        articles = [NewsArticle.model_validate(article) for article in state.get("articles", [])][:3]
    except (ValueError, TypeError):
        articles = []
    return StockNewsResponse(
        ticker=ticker, articles=articles, updated_at=parse_date(state.get("updated_at")),
        status=("stale" if articles else reason) if reason else ("ok" if articles else "empty"),
        cached=cached, message=MESSAGES.get(reason),
    )


def get_stock_news(ticker: str) -> StockNewsResponse:
    clean = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.=_^\-]{0,31}", clean):
        return _response(clean[:32], {}, reason="unsupported")
    settings = get_settings()
    # Runtime UI edits are durable and effective immediately across processes.
    # This key is never mirrored to the shared frontend runtime-env volume.
    api_key = runtime_settings.get_runtime_config_value("MARKETAUX_API_KEY")
    state = {}
    try:
        identity = repository.resolve_symbol(clean)
        if identity is None or not re.fullmatch(r"[A-Z0-9][A-Z0-9.=_^\-]{0,31}", identity.symbol):
            return _response(clean, {}, reason="unsupported")
        cache_key = news_cache_key(identity, settings)
        with repository.locked_store(cache_key) as store:
            state = store.read(cache_key)
            now = utc_now()
            updated_at = parse_date(state.get("updated_at"))
            ttl = settings.marketaux_cache_ttl_seconds if state.get("articles") else settings.marketaux_empty_ttl_seconds
            if updated_at and timedelta(0) <= now - updated_at <= timedelta(seconds=ttl):
                return _response(clean, state)
            if not api_key:
                return _response(clean, state, reason="not_configured")
            retry_at = parse_date(state.get("retry_at"))
            credential_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            if retry_at and retry_at > now and state.get("credential_id") == credential_id:
                return _response(clean, state, reason=state.get("failure_reason", "unavailable"))
            admitted, reason = store.reserve(limit=settings.marketaux_daily_limit, credential_id=credential_id)
            if not admitted:
                return _response(clean, state, reason=reason)
            try:
                rows = fetch_news(symbol=provider_symbol(identity), api_key=api_key,
                                  languages=settings.marketaux_languages,
                                  timeout=settings.marketaux_request_timeout_seconds)
                articles = parse_articles(rows, identity, min_match_score=settings.marketaux_min_match_score,
                                          now=utc_now(), api_key=api_key)
            except MarketauxFailure as failure:
                seconds = max(settings.marketaux_failure_backoff_seconds, failure.retry_seconds)
                state.update(retry_at=(utc_now() + timedelta(seconds=seconds)).isoformat(),
                             failure_reason=failure.reason, credential_id=credential_id)
                store.write(cache_key, state)
                store.block(reason=failure.reason, seconds=seconds, credential_id=credential_id)
                return _response(clean, state, reason=failure.reason)
            state = {"articles": [article.model_dump(mode="json") for article in articles],
                     "updated_at": utc_now().isoformat()}
            store.write(cache_key, state)
            return _response(clean, state, cached=False)
    except repository.NewsRepositoryUnavailable:
        # No durable reservation means no provider request. Never fall back to a
        # process-local counter, which would reset on NAS/container restart.
        return _response(clean, state, reason="unavailable")
