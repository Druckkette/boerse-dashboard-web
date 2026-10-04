# Independent Powertrend (powertrend_v2)

Powertrend is an index-specific technical supplement enabled by the IBD option. MarketPhase is never an input to activation, pressure, recovery or termination. The normal market rules remain trend_ampel_v3.

Only complete, confirmed daily OHLC observations advance the state. Stored price history is replayed chronologically before chart-window slicing; changing the display window or restarting the service therefore does not reset either date. Incomplete observations preserve the last state and dates.

- OFF → ON: low above EMA21 for ≥10 sessions, EMA21 above SMA50 for ≥5 sessions, SMA50 rising versus the preceding session, and close ≥ preceding close, simultaneously.
- ON → UNDER_PRESSURE: ≥3 consecutive closes below EMA21, or close < SMA50 − 0.5 × ATR21. No market-phase or volume condition.
- UNDER_PRESSURE → ON: all four activation criteria again, simultaneously. One good day is insufficient. The original activation date remains; pressure_since is cleared.
- ON / UNDER_PRESSURE → OFF: EMA21 < SMA50. Both dates are cleared. Equality does not terminate the trend. A later new activation requires the four criteria again and gets a new date.

The daily engine point carries powertrend_state, powertrend_formally_active, powertrend_start_date and powertrend_pressure_since. MarketTrendAmpel JSON metrics persist all four fields plus powertrend_ruleset_version. The market API exposes pressure_since and ruleset_version inside powertrend. Captured journal contexts include the API fields; historical reconstruction includes the market metrics and the Powertrend version in its ruleset hash. No schema migration is required for these additive JSON fields. Existing captured contexts remain historical records; newly computed/reconstructed contexts use v2.

The home page shows the separate Powertrend state and both dates for each available index. Stale or incomplete index data is marked explicitly and does not present a Powertrend badge as current.

UI badges and cards accept only the Powertrend object, with no normal market-phase input. ON is green, UNDER_PRESSURE amber, OFF neutral. Current counters are displayed separately from the original activation date.

Regression data: Yahoo (^GSPC) OHLCV from the NAS Price Cache, exported 2026-10-04, fixture tests/fixtures/market/powertrend/sp500_2026.json. It reproduces activation on 2026-08-19 and persistent pressure since 2026-09-10, including a later 1/10 streak. Synthetic state-transition tests separately cover full recovery and formal termination.
