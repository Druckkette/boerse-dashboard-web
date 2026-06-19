# Fundamentals Metadata

Fundamental snapshots keep backward-compatible scalar fields such as `quarterly_eps_growth_pct`.
The EPS quarter rule no longer uses that scalar field as the deciding criterion.

The last three EPS quarters are stored in `fundamental_snapshots.metadata_json.eps_quarter_history`.
Worker-enriched snapshots also keep the same structure under `metadata_json.enrichment.eps_quarter_history`.

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
