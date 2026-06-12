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
- S&P 500 benchmark line for the depot curve when `^GSPC` or `SPY` is present in the Price Cache.
- Persistent ISIN/Yahoo mapping maintenance in the portfolio import UI.
- Stock assessment ranking table using the same score components as the single-stock assessment.
- Pushover configuration status and test job via Settings; secrets stay in NAS/container environment.
- Stock assessment fundamental cache with web editing, backend scoring, earnings warning and institutional support context.
- Worker job `refresh_fundamentals` fills the same cache from yfinance without blocking stock detail requests.
- Stock detail price chart now includes 21-EMA, 50-SMA, 200-SMA and volume context from the cached Price API.
- Sell detail diagnostics endpoint and UI with live metrics, strategy hub, next action and post-mortem checks.
- Market diagnostics endpoint and `/market` UI for the old `_tab_marktanalyse` daily checklist, Intermarket view and defensive/offensive sector rotation.
- Persistent Sell post-mortem notes/actions with Postgres table, API and non-blocking detail-page editing.
- Sell context chart annotations for stop, next tranche, full-exit levels and active signal markers.

## Open Gaps

- Stock assessment page parity:
  - FMP/SEC enrichment for deeper quarterly/annual fundamental history and acceleration detection.
  - Deeper single-stock chart context such as annotated candlesticks and RS subplot.
- Portfolio parity:
  - Broker-specific edge cases for dividends, taxes, split rows and derivatives need more golden fixtures.
- Market parity:
  - Full universe maintenance/rescue/remap workflows.
- Technical settings parity:
  - Worker diagnostics for missing tickers and Yahoo mapping.
- Auth/private area:
  - Streamlit password gate equivalent for personal depot/settings.
  - Session handling suitable for NAS and later Hetzner.
- 13F/SEC parity:
  - Real 13F trend worker, CUSIP mapping workflows and frontend display.
