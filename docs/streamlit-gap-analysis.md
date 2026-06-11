# Streamlit Feature Gap Analysis

Reference: `Druckkette/boerse-dashboard` (`app.py`, worker modules, scripts, tests).
Target: `Druckkette/boerse-dashboard-web`.

## Covered Or Mostly Covered

- Market overview: breadth, volatility, trend ampellogic, cached snapshots.
- Market data jobs: price refresh, breadth, relative strength, ATR monitor skeleton/partial implementation.
- Portfolio import: browser upload, parsed positions, persisted open positions.
- Sell engine: migrated domain logic, metrics/evaluate endpoints, ranking, manual state, tranche log, snooze state.
- NAS/GHCR deployment: Docker Compose, GHCR workflows, update script.
- Jobs UI: manual start, status polling, configurable market-data bootstrap.

## Added In This Migration Step

- Sectors page migrated from Streamlit `_tab_sektoranalyse`.
- Backend endpoint: `GET /api/v1/market/sectors`.
- Cached SPDR sector ETF ranking for daily and weekly mode.
- Price-refresh preset `sector`; default `all` includes sector ETFs.
- Frontend page: `/sectors` with Top/Bottom 3, ranking table and ranking-history matrix.

## Open Gaps

- Stock assessment page parity:
  - Single-stock fundamental checks.
  - Technical checklist and chart behavior signs.
  - Combined 0-100 score from technical, fundamental, moving averages and chart behavior.
  - Earnings warning, institutional holder context, CMF, liquidity/dollar-volume filters.
  - Comparison/ranking table parity beyond current RS ranking.
- Portfolio parity:
  - Full manual position editor with stop %, pivot day, sell booking and cash-flow log.
  - Depot curve from Trade-Republic transaction export.
  - ISIN-to-Yahoo mapping editor.
  - Position-size calculator.
  - Portfolio risk settings persisted in `app_settings`.
- Sell parity:
  - Full strategy hub UI.
  - Post-mortem workflow.
  - Complete live-monitor diagnostics and chart context.
- Market parity:
  - Deep analysis checklist cards from old `_tab_marktanalyse`.
  - Intermarket block and sector rotation card integration into market overview.
  - Full universe maintenance/rescue/remap workflows.
- Technical settings parity:
  - Persistent settings service backed by Postgres `app_settings`.
  - Pushover configuration and test job.
  - Worker diagnostics for missing tickers and Yahoo mapping.
- Auth/private area:
  - Streamlit password gate equivalent for personal depot/settings.
  - Session handling suitable for NAS and later Hetzner.
- 13F/SEC parity:
  - Real 13F trend worker, CUSIP mapping workflows and frontend display.
