from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import StringIO
import re

import requests


DEFAULT_RS_CSV_URL = (
    "https://raw.githubusercontent.com/Fred6725/rs-log/main/output/rs_stocks.csv"
)
DEFAULT_RS_CSV_COMMIT_URL = (
    "https://api.github.com/repos/Fred6725/rs-log/commits"
    "?path=output/rs_stocks.csv&per_page=1"
)


@dataclass(frozen=True)
class ExternalRsRating:
    ticker: str
    rating: int
    score: float
    as_of: date
    generated_at: str
    universe: str
    source: str


def fetch_external_rs_ratings(
    *,
    url: str = DEFAULT_RS_CSV_URL,
    timeout: int = 30,
) -> list[ExternalRsRating]:
    response = requests.get(url, timeout=timeout)
    if response.status_code != 200:
        body = str(response.text or "").strip()[:300]
        raise RuntimeError(
            f"RS CSV antwortet mit HTTP {response.status_code}"
            + (f": {body}" if body else "")
        )
    generated_at, as_of = _fetch_source_timestamp(timeout=timeout)
    return parse_external_rs_csv(
        response.text,
        default_as_of=as_of,
        default_generated_at=generated_at,
    )


def parse_external_rs_csv(
    content: str,
    *,
    default_as_of: date | None = None,
    default_generated_at: str = "",
) -> list[ExternalRsRating]:
    rows = list(csv.DictReader(StringIO(content)))
    parsed: list[ExternalRsRating] = []
    for row in rows:
        ticker = str(row.get("ticker") or row.get("Ticker") or "").strip().upper()
        as_of = _parse_date(row.get("as_of_date")) or default_as_of
        if not ticker or as_of is None:
            continue
        try:
            rating = max(
                1,
                min(99, int(float(row.get("rating") or row.get("Percentile") or 0))),
            )
            score = float(row.get("score") or row.get("Relative Strength") or 0)
        except (TypeError, ValueError):
            continue
        parsed.append(
            ExternalRsRating(
                ticker=ticker,
                rating=rating,
                score=score,
                as_of=as_of,
                generated_at=str(
                    row.get("generated_at_utc") or default_generated_at
                ).strip(),
                universe=str(row.get("universe") or "Fred6725/rs-log").strip(),
                source=str(row.get("source") or "github_fred_rs_log").strip(),
            )
        )
    if not parsed:
        raise RuntimeError("RS CSV enthält keine verwertbaren Ratings mit as_of_date.")
    return parsed


def _fetch_source_timestamp(*, timeout: int) -> tuple[str, date]:
    response = requests.get(DEFAULT_RS_CSV_COMMIT_URL, timeout=min(timeout, 15))
    if response.status_code != 200:
        raise RuntimeError(
            f"RS CSV Commit-Metadaten antworten mit HTTP {response.status_code}."
        )
    try:
        payload = response.json()
        row = payload[0]
        commit = row["commit"]
        generated_raw = str(commit["committer"]["date"])
        message = str(commit.get("message") or "")
        generated_at = datetime.fromisoformat(
            generated_raw.replace("Z", "+00:00")
        ).astimezone(UTC)
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("RS CSV Commit-Metadaten sind unvollständig.") from exc

    message_date = _date_from_update_message(message)
    source_date = _previous_weekday(message_date or generated_at.date())
    return generated_at.isoformat(), source_date


def _date_from_update_message(message: str) -> date | None:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message)
    return _parse_date(match.group(1)) if match else None


def _previous_weekday(value: date) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None
