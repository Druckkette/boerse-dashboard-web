# Streamlit Feature Gap Analysis

Reference: `Druckkette/boerse-dashboard` (`app.py`, worker modules, scripts, tests).
Target: `Druckkette/boerse-dashboard-web`.

## Covered Or Mostly Covered

- Market overview: breadth, volatility, trend ampellogic, cached snapshots.
- Market data jobs: price refresh, breadth, relative strength, ATR monitor skeleton/partial implementation.
- Portfolio import: browser upload, parsed positions, Trade-Republic transaction preview/import, ISIN mapping, persisted open positions.
- Portfolio controls: manual position editor, sell booking, cash-flow log, depot curve from Trade-Republic transactions or open-position fallback, position-size calculator and persisted risk assumptions.
- Sell engine: migrated domain logic, metrics/evaluate endpoints, ranking, manual state, tranche log, snooze state.
- NAS/GHCR deployment: Docker Compose, GHCR workflows, update script.
- Jobs UI: manual start, status polling, configurable market-data bootstrap.

## Recently Added

- Sectors page migrated from Streamlit `_tab_sektoranalyse`.
- Backend endpoint: `GET /api/v1/market/sectors`.
- Cached SPDR sector ETF ranking for daily and weekly mode.
- Price-refresh preset `sector`; default `all` includes sector ETFs.
- Frontend page: `/sectors` with Top/Bottom 3, ranking table and ranking-history matrix.
- Depot curve endpoint and frontend panel for cached-position fallback.
- Position-size calculator with loss-budget and Beta-Balancer formulas.
- Trade-Republic transaction CSV import with web upload, ISIN-to-Yahoo mapping preview and persisted transactions/open positions.
- Transaction-based depot curve from saved Trade-Republic transactions with cached price bars and trade-price fallback.

## Open Gaps

- Stock assessment page parity:
  - Single-stock fundamental checks.
  - Technical checklist and chart behavior signs.
  - Combined 0-100 score from technical, fundamental, moving averages and chart behavior.
  - Earnings warning, institutional holder context, CMF, liquidity/dollar-volume filters.
  - Comparison/ranking table parity beyond current RS ranking.
- Portfolio parity:
  - S&P 500 comparison line for the transaction-based depot curve.
  - ISIN/Yahoo mapping maintenance page beyond import-time editing.
  - Broker-specific edge cases for dividends, taxes, split rows and derivatives need more golden fixtures.
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
