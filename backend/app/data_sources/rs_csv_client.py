from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from io import StringIO

import requests


DEFAULT_RS_CSV_URL = (
    "https://raw.githubusercontent.com/Druckkette/boerse-dashboard/main/output/rs_stocks.csv"
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
    return parse_external_rs_csv(response.text)


def parse_external_rs_csv(content: str) -> list[ExternalRsRating]:
    rows = list(csv.DictReader(StringIO(content)))
    parsed: list[ExternalRsRating] = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        as_of = _parse_date(row.get("as_of_date"))
        if not ticker or as_of is None:
            continue
        try:
            rating = max(1, min(99, int(float(row.get("rating") or 0))))
            score = float(row.get("score") or 0)
        except (TypeError, ValueError):
            continue
        parsed.append(
            ExternalRsRating(
                ticker=ticker,
                rating=rating,
                score=score,
                as_of=as_of,
                generated_at=str(row.get("generated_at_utc") or "").strip(),
                universe=str(row.get("universe") or "").strip(),
                source=str(row.get("source") or "external_csv").strip(),
            )
        )
    if not parsed:
        raise RuntimeError("RS CSV enthält keine verwertbaren Ratings mit as_of_date.")
    return parsed


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except ValueError:
        return None
