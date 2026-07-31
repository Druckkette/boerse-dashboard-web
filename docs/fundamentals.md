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

Revenue uses the same multi-period structure and thresholds, but without a trailing revenue sum criterion.

## Earnings-driven refresh

`earnings_events` stores the FMP stable `/earnings-calendar` response for the window from five days
ago through 120 days ahead. If the FMP key is missing, the plan limit is reached or FMP fails, the
same job automatically stores the official Nasdaq calendar for the rolling next 35 days instead.
The scheduler refreshes this calendar at 15:50 and 22:20 Europe/Berlin. Tickers with an event from
three days ago through tomorrow are forced to the front of the next incremental fundamentals
batch. This catches newly published quarterly data without downloading statements for the entire
universe twice per day. The per-ticker FMP stable `/earnings` call remains the fallback for a stock
detail refresh.

Quarterly revenue history is stored in `fundamental_snapshots.metadata_json.revenue_quarter_history`:

```json
[
  {
    "fiscal_period": "2026 Q1",
    "revenue_current_quarter": 142.0,
    "revenue_same_quarter_last_year": 100.0,
    "revenue_growth_yoy_pct": 42.0,
    "flag": null
  }
]
```

Annual revenue history is stored in `fundamental_snapshots.metadata_json.annual_revenue_history`:

```json
[
  {
    "fiscal_year": "2025",
    "revenue_current_year": 1350.0,
    "revenue_previous_year": 1000.0,
    "revenue_growth_yoy_pct": 35.0,
    "flag": null
  }
]
```

The quarterly revenue criterion is passed only if the latest three same-quarter YoY comparisons are all at least
+20%. The annual revenue criterion is passed only if the latest three full-year comparisons are all at least +20%.
The revenue acceleration bonus uses the latest three quarterly revenue growth rates.
