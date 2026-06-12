# Streamlit Feature Gap Analysis

Reference: `Druckkette/boerse-dashboard` (`app.py`, worker modules, scripts, tests).
Target: `Druckkette/boerse-dashboard-web`.

## Covered Or Mostly Covered

- Market overview: breadth, volatility, trend ampellogic, cached snapshots.
- Market data jobs: price refresh, breadth, relative strength, settings-aware ATR monitor.
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
- FMP/SEC fundamentals enrichment: worker-side quarterly EPS/revenue growth, acceleration flags,
  trailing EPS, ROE/margin fallback and source metadata, with optional `FMP_API_KEY`.
- Stock detail price chart now includes 21-EMA, 50-SMA, 200-SMA and volume context from the cached Price API.
- Stock detail chart context: candlestick bodies/wicks, colored volume, automatic 52W/high-volume/trend-loss markers and RS-vs-SPY subplot from cached price data.
- Trade-Republic import parity hardening: broker transaction IDs, decimal-comma prices,
  dividend/tax cash events, split rows and derivative redemption rows are covered by
  portfolio golden fixtures and curve regression tests.
- Sell detail diagnostics endpoint and UI with live metrics, strategy hub, next action and post-mortem checks.
- Market diagnostics endpoint and `/market` UI for the old `_tab_marktanalyse` daily checklist, Intermarket view and defensive/offensive sector rotation.
- Persistent Sell post-mortem notes/actions with Postgres table, API and non-blocking detail-page editing.
- Sell context chart annotations for stop, next tranche, full-exit levels and active signal markers.
- Settings data diagnostics for missing/stale price cache, Yahoo-symbol gaps and ISIN mapping status with direct worker-job actions.
- Basic Auth frontend gate for private NAS access plus same-origin `/api/v1` proxy to keep normal
  browser traffic behind the dashboard.
- Real SEC Form-13F worker path: downloads official quarterly data sets with `SEC_USER_AGENT`,
  caches ZIP files, maps CUSIPs to tickers and persists aggregate institutional trends.
- 13F CUSIP mapping workflow in `/stocks`: persisted manual overrides plus unmatched-CUSIP review
  from the latest worker result, without CSV file handling.
- Universe maintenance: Nasdaq-Trader parser, `refresh_universe` worker, persisted
  `us_common_stocks` members, `/market/universe` status API and Jobs-page refresh control.
- Universe symbol rescue: persisted Yahoo-symbol overrides for stored universe members,
  `/market/universe/mappings` review/update API and Jobs-page mapping workflow for failed
  price refreshes.
- Universe mapping parity hardening: stale manual overrides for renamed/delisted symbols
  are kept in storage but no longer counted in current mapping review results; class-share
  examples are covered by dedicated market fixtures.
- Settings-aware ATR monitor: scheduled runs respect the web setting, manual runs can still be
  triggered, and monitor results include ATR distance to the configured reference.

## Open Gaps

- No feature gap from the last tracked Streamlit-parity audit is currently open in this
  document. Next work should focus on end-to-end validation with a real depot export,
  real NAS data volumes and production hardening.
