"""Small bounded Marketaux client. Never propagate provider URLs or response errors."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import logging
import re

import requests


ENDPOINT = "https://api.marketaux.com/v1/news/all"
MAX_RESPONSE_BYTES = 2_000_000


class _RedactToken(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r"(?i)(api_token=)[^\s&\"'<>]+", r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


# urllib3 may log request paths when an operator enables DEBUG. Our exceptions
# contain only authored classifications; this also protects third-party debug paths.
for _logger in ("urllib3.connectionpool", "urllib3.util.retry", "requests"):
    logging.getLogger(_logger).addFilter(_RedactToken())


@dataclass
class MarketauxFailure(Exception):
    reason: str = "unavailable"
    retry_seconds: int = 300


def _retry_after(value: str | None) -> int:
    try:
        return max(60, min(86400, int(value or "")))
    except ValueError:
        try:
            until = parsedate_to_datetime(value or "")
            if until.tzinfo is None:
                until = until.replace(tzinfo=UTC)
            return max(60, min(86400, int((until - datetime.now(UTC)).total_seconds())))
        except (TypeError, ValueError, OverflowError):
            return 86400


def fetch_news(*, symbol: str, api_key: str, languages: str, timeout: float) -> list[dict]:
    params = {
        "symbols": symbol,
        "filter_entities": "true",
        "must_have_entities": "true",
        "group_similar": "true",
        "limit": 3,
        "sort": "published_at",
        "api_token": api_key,
    }
    if languages:
        params["language"] = languages
    try:
        # No automatic retry or redirect: each attempt consumes one durable quota
        # reservation, and credentials must never be forwarded to another host.
        with requests.get(
            ENDPOINT, params=params, timeout=(min(3.05, timeout), timeout),
            allow_redirects=False, stream=True,
            headers={"Accept": "application/json", "User-Agent": "boerse-dashboard-web"},
        ) as response:
            if response.status_code in (401, 403):
                raise MarketauxFailure("not_configured", 3600)
            if response.status_code in (402, 429):
                raise MarketauxFailure("limit_reached", _retry_after(response.headers.get("Retry-After")))
            if response.status_code != 200:
                raise MarketauxFailure()
            body = bytearray()
            for part in response.iter_content(chunk_size=65536):
                body.extend(part)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise MarketauxFailure()
            import json
            payload = json.loads(body)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise MarketauxFailure()
            return payload["data"]
    except MarketauxFailure:
        raise
    except (requests.RequestException, ValueError, TypeError, UnicodeError):
        raise MarketauxFailure() from None
