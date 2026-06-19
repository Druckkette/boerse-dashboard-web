# Fundamentals Metadata

Fundamental snapshots keep backward-compatible scalar fields such as `quarterly_eps_growth_pct`.
The EPS quarter rule no longer uses that scalar field as the deciding criterion.

The last three EPS quarters are stored in `fundamental_snapshots.metadata_json.eps_quarter_history`.
The last three full-year EPS comparisons are stored in `fundamental_snapshots.metadata_json.annual_eps_history`.
Worker-enriched snapshots also keep the same structures under `metadata_json.enrichment`.

Schema, ordered latest quarter first:

```json
[
  {
    "fiscal_period": "2026 Q1",
    "eps_current_quarter": 2.4,
    "eps_same_quarter_last_year": 1.5,
    "eps_growth_yoy_pct": 60.0,
    "flag": null
  }
]
```

`eps_growth_yoy_pct` is derived from:

```text
(eps_current_quarter / eps_same_quarter_last_year - 1) * 100
```

If fewer than three valid quarter comparisons are available, or if any same-quarter prior-year EPS value is missing,
zero or negative, the three-quarter EPS criterion is not passed.

Annual EPS history schema, ordered latest complete fiscal year first:

```json
[
  {
    "fiscal_year": "2025",
    "eps_current_year": 7.2,
    "eps_previous_year": 5.2,
    "eps_growth_yoy_pct": 38.5,
    "flag": null
  }
]
```

Annual EPS is derived from the sum of the four quarterly EPS values for each complete fiscal year.
The annual EPS criterion is passed only if the last three complete fiscal years each show at least +20% YoY growth.

The separate `trailing_eps` field is the sum of the latest four quarterly EPS values. It must be greater than zero.
The EPS acceleration bonus uses the last three quarterly YoY growth rates and is passed when the rates accelerate
from older to newer quarters.
