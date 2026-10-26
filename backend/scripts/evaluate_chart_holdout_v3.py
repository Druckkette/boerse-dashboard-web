"""Evaluate the frozen v3 source cases without hiding misses or excluded bases.

Run from backend: python -m scripts.evaluate_chart_holdout_v3
Use --module-source /path/to/chart_patterns_v2.py for the unchanged baseline.
This small, deliberately selected set measures source-case coverage and strict
depth exclusions. It cannot estimate population precision or trading returns.
"""

import argparse
from datetime import date
import gzip
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
from time import perf_counter

from app.domain import chart_patterns


FIXTURES = Path(__file__).parents[1] / "tests/fixtures/chart_patterns/holdout_v3"


def source_module(path=None):
    if path is None:
        return chart_patterns
    spec = importlib.util.spec_from_file_location("chart_patterns_baseline", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cases():
    return json.loads((FIXTURES / "manifest.json").read_text())["cases"]


def bars_for(case, module=chart_patterns):
    with gzip.open(FIXTURES / f"{case['id']}.json.gz", "rt") as stream:
        bars = [module.Bar(date.fromisoformat(row[0]), *row[1:]) for row in json.load(stream)]
    assert bars and max(bar.date for bar in bars) <= date.fromisoformat(case["as_of"])
    return bars


def matching(case, patterns):
    kinds = case.get("rejected_kinds", [case["kind"]])
    return [
        pattern for pattern in patterns
        if pattern.kind in kinds
        and case["base_from"] <= pattern.points[0].date <= case["base_to"]
        and case["detected_from"] <= pattern.detected_on <= case["detected_to"]
    ]


def evaluate(module=chart_patterns, parameters=None):
    parameters = parameters or module.PatternParameters()
    started = perf_counter()
    report = {
        "algorithm_version": module.ALGORITHM_VERSION,
        "module_sha256": hashlib.sha256(inspect.getsource(module).encode()).hexdigest(),
        "manifest_sha256": hashlib.sha256((FIXTURES / "manifest.json").read_bytes()).hexdigest(),
        "parameter_hash": parameters.fingerprint,
        "parameters": parameters.model_dump(),
        "price_source": "Yahoo Finance via yfinance, split-adjusted OHLC, no dividend adjustment",
        "retrieved_on": "2026-10-26",
        "limitation": "Selected source cases; no estimate of population precision or returns.",
        "cases": [],
    }
    for case in cases():
        if case.get("data_status") == "unavailable":
            report["cases"].append({
                **case,
                "eligible": False,
                "passed": False,
                "matched": None,
                "diagnostics": [case["data_note"]],
            })
            continue
        bars = bars_for(case, module)
        diagnostics = module.validate_bars(bars)
        patterns = module.detect_patterns(case["ticker"], bars, parameters)
        matches = matching(case, patterns)
        for found in matches:
            replay = next(p for p in module.detect_patterns(
                case["ticker"], [b for b in bars if str(b.date) <= found.detected_on], parameters
            ) if p.id == found.id)
            assert replay.points == found.points and replay.pivot == found.pivot
        report["cases"].append({
            **case,
            "prices_sha256": hashlib.sha256(gzip.decompress(
                (FIXTURES / f"{case['id']}.json.gz").read_bytes()
            )).hexdigest(),
            "bars": len(bars),
            "eligible": not diagnostics,
            "diagnostics": diagnostics,
            "matched": bool(matches),
            # Invalid data never count as a successful negative exclusion.
            "passed": not diagnostics and bool(matches) == (case["expected"] == "present"),
            "matches": [p.model_dump() for p in matches],
            "all_patterns": [p.model_dump() for p in patterns],
            "causal_replay_verified": bool(matches),
        })
    positive = [case for case in report["cases"]
                if case["eligible"] and case["expected"] == "present"]
    negative = [case for case in report["cases"]
                if case["eligible"] and case["expected"] == "absent"]
    report["unscorable_count"] = sum(not case["eligible"] for case in report["cases"])
    report["positive_count"] = len(positive)
    report["positive_matched"] = sum(case["passed"] for case in positive)
    report["negative_count"] = len(negative)
    report["negative_correctly_excluded"] = sum(case["passed"] for case in negative)
    report["elapsed_seconds"] = round(perf_counter() - started, 3)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(evaluate(source_module(args.module_source)), indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)
