"""Deterministic pointed-V stress test; a synthetic check, not market precision.

The fixed family varies trough position and noise at unchanged 35% depth.
Every generated path is a piecewise-linear V before independent Gaussian noise.
"""

import argparse
import hashlib
import inspect
import json
from time import perf_counter

import numpy as np

from scripts.evaluate_chart_holdout_v3 import source_module
from tests.domain.test_chart_patterns import series


def evaluate(module):
    started = perf_counter()
    result = {
        "algorithm_version": module.ALGORITHM_VERSION,
        "module_sha256": hashlib.sha256(inspect.getsource(module).encode()).hexdigest(),
        "parameters": module.PatternParameters().model_dump(),
        "specification": "65 sessions, 35% depth, trough at20/26/32/39/45/49, noise0/.2/1/2/3/4/5, seeds0..9; prior60-session rise60to100; all Cup classifications counted as false positives.",
        "limitation": "Constructed stress cases; neither population precision nor random market holdout.",
        "cases_per_noise": 60,
        "noise_results": [],
    }
    for noise in (0, 0.2, 1, 2, 3, 4, 5):
        false_positives = []
        for bottom in (20, 26, 32, 39, 45, 49):
            for seed in range(10):
                prices = np.interp(np.arange(1, 66), [0, bottom, 65], [100, 65, 100])
                prices += np.random.default_rng(seed).normal(0, noise, 65)
                raw = series([*np.linspace(60, 100, 60), *prices])
                bars = [module.Bar(**bar.__dict__) for bar in raw]
                patterns = [
                    p for p in module.detect_patterns("V", bars) if p.kind.startswith("cup")
                ]
                if patterns:
                    false_positives.append(
                        {
                            "bottom": bottom,
                            "seed": seed,
                            "patterns": [
                                {
                                    "kind": p.kind,
                                    "left": p.points[0].date,
                                    "detected_on": p.detected_on,
                                    "warnings": p.warnings,
                                }
                                for p in patterns
                            ],
                        }
                    )
        result["noise_results"].append(
            {
                "noise_std_price_units": noise,
                "false_positive_count": len(false_positives),
                "false_positives": false_positives,
            }
        )
    result["elapsed_seconds"] = round(perf_counter() - started, 3)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-source")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.output, "w") as output:
        json.dump(evaluate(source_module(args.module_source)), output, indent=2, ensure_ascii=False)
        output.write("\n")
