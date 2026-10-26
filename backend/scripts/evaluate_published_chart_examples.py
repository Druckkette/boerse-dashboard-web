"""Reproduce the published-example comparison, including missed source labels.

Run from backend: python -m scripts.evaluate_published_chart_examples
The cases were selected before the first evaluation. Custom parameters are a
separate sensitivity check, never counted toward the unchanged-default result.
"""

from datetime import date
import gzip
import hashlib
import inspect
import json
from pathlib import Path

from app.domain import chart_patterns as module
from app.domain.chart_patterns import Bar, PatternParameters, detect_patterns, validate_bars


FIXTURES = Path(__file__).parents[1] / "tests/fixtures/chart_patterns/published"


def cases():
    return json.loads((FIXTURES / "manifest.json").read_text())["cases"]


def bars_for(case):
    with gzip.open(FIXTURES / f"{case['id']}.json.gz", "rt") as stream:
        bars = [Bar(date.fromisoformat(r[0]), *r[1:]) for r in json.load(stream)]
    assert max(b.date for b in bars) <= date.fromisoformat(case["as_of"])
    return bars


def matching(case, patterns):
    return [
        p for p in patterns
        if p.kind == case["kind"]
        and case["base_from"] <= p.points[0].date <= case["base_to"]
        and case["detected_from"] <= p.detected_on <= case["detected_to"]
    ]


def evaluate(parameters=None):
    parameters = parameters or PatternParameters()
    report = {
        "algorithm_version": module.ALGORITHM_VERSION,
        "module_sha256": hashlib.sha256(inspect.getsource(module).encode()).hexdigest(),
        "parameter_hash": parameters.fingerprint,
        "parameters": parameters.model_dump(),
        "price_source": "Yahoo Finance via yfinance, split-adjusted OHLC, no dividend adjustment",
        "retrieved_on": "2026-10-26",
        "cases": [],
    }
    for case in cases():
        bars = bars_for(case)
        patterns = detect_patterns(case["ticker"], bars, parameters)
        matches = matching(case, patterns)
        for found in matches:
            replay = next(p for p in detect_patterns(
                case["ticker"], [b for b in bars if str(b.date) <= found.detected_on], parameters
            ) if p.id == found.id)
            assert replay.points == found.points and replay.pivot == found.pivot
        report["cases"].append({
            **case,
            "prices_sha256": hashlib.sha256(gzip.decompress(
                (FIXTURES / f"{case['id']}.json.gz").read_bytes()
            )).hexdigest(),
            "bars": len(bars),
            "diagnostics": validate_bars(bars),
            "matched": bool(matches),
            "matches": [p.model_dump() for p in matches],
            "all_patterns": [p.model_dump() for p in patterns],
            "causal_replay_verified": bool(matches),
        })
    report["matched_count"] = sum(c["matched"] for c in report["cases"])
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, ensure_ascii=False))
