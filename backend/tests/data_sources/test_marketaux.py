import json
import logging

import pytest
import requests

from app.data_sources import marketaux


class Response:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self.body = json.dumps(body if body is not None else {"data": []}).encode()
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, chunk_size):
        yield self.body


def test_required_api_parameters_and_language_filter(monkeypatch):
    calls = []
    monkeypatch.setattr(marketaux.requests, "get", lambda *a, **kw: calls.append((a, kw)) or Response())
    assert marketaux.fetch_news(symbol="NVDA", api_key="test-only-secret", languages="de,en", timeout=8) == []
    args, kwargs = calls[0]
    assert args == ("https://api.marketaux.com/v1/news/all",)
    assert kwargs["params"] == {
        "symbols": "NVDA", "filter_entities": "true", "must_have_entities": "true",
        "group_similar": "true", "limit": 3, "sort": "published_at",
        "api_token": "test-only-secret", "language": "de,en",
    }
    assert kwargs["allow_redirects"] is False and kwargs["timeout"] == (3.05, 8)
    marketaux.fetch_news(symbol="AAPL", api_key="test-only-secret", languages="", timeout=8)
    assert "language" not in calls[1][1]["params"]


@pytest.mark.parametrize("status,reason,retry", [
    (401, "not_configured", 3600), (403, "not_configured", 3600),
    (429, "limit_reached", 180), (402, "limit_reached", 180),
    (500, "unavailable", 300), (302, "unavailable", 300), (422, "unavailable", 300),
])
def test_errors_and_redirects_do_not_echo_provider_body_or_url(monkeypatch, status, reason, retry):
    monkeypatch.setattr(marketaux.requests, "get", lambda *a, **kw: Response(
        status=status, body={"error": "api_token=test-only-secret"}, headers={"Retry-After": "180"}))
    with pytest.raises(marketaux.MarketauxFailure) as failure:
        marketaux.fetch_news(symbol="AAPL", api_key="test-only-secret", languages="de,en", timeout=8)
    assert failure.value.reason == reason and failure.value.retry_seconds == retry
    assert "test-only-secret" not in str(failure.value)


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"data":null}', b'{"data":{}}', b'x' * 2_000_001])
def test_malformed_or_oversized_payloads_are_safe(monkeypatch, body):
    response = Response()
    response.body = body
    monkeypatch.setattr(marketaux.requests, "get", lambda *a, **kw: response)
    with pytest.raises(marketaux.MarketauxFailure):
        marketaux.fetch_news(symbol="TSLA", api_key="test-only-secret", languages="", timeout=8)


def test_network_exception_does_not_escape_or_log_credential(monkeypatch, caplog):
    def failed(*a, **kw):
        raise requests.Timeout("https://api.marketaux.com/?api_token=test-only-secret")
    monkeypatch.setattr(marketaux.requests, "get", failed)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(marketaux.MarketauxFailure) as failure:
            marketaux.fetch_news(symbol="NVDA", api_key="test-only-secret", languages="", timeout=8)
        logging.getLogger("urllib3.connectionpool").debug("GET /v1/news/all?api_token=%s&symbols=NVDA", "test-only-secret")
    assert "test-only-secret" not in str(failure.value) + caplog.text
    assert "[REDACTED]" in caplog.text


def test_retry_after_falls_back_to_conservative_one_day():
    assert marketaux._retry_after(None) == 86400
    assert marketaux._retry_after("bad") == 86400
    assert marketaux._retry_after("-1") == 60
    assert marketaux._retry_after("999999999") == 86400
