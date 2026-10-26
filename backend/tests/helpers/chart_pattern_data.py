import gzip
import json
from datetime import date
from pathlib import Path

from app.domain.chart_patterns import Bar

FIXTURES = Path(__file__).parents[1] / "fixtures" / "chart_patterns"


def historical_cases():
    return json.loads((FIXTURES / "manifest.json").read_text())


def historical_bars(case):
    with gzip.open(FIXTURES / case["file"], "rt") as stream:
        return [Bar(date.fromisoformat(row[0]), *row[1:]) for row in json.load(stream)]
