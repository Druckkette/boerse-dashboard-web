# Private comparison of recent journal sales

The research CLI compares the latest journal sell executions with the eight existing sell engines. This is a retrospective counterfactual, not a fitted or out-of-sample strategy recommendation. Private inputs and results belong in a protected NAS directory and the ignored `output/journal-exits-*/` local directory. Never commit journal exports or personalized results.

## Reproduce

Inside the deployed backend, export saved data without downloading quotes:

```sh
python -m app.research.export_journal_exit_backtest --limit 20 > /protected/path/input.json
```

Run locally or in the backend with the same source revision:

```sh
python -m app.research.journal_exit_backtest input.json results-pooled.json
python -m app.research.journal_exit_backtest input.json results-lots.json --lot-wise
```

Export includes the current global strategy thresholds, immutable purchase executions, selected FIFO allocations, and saved historical OHLC/FX bars. It excludes journal notes, questionnaires, credentials, unrelated positions and live market downloads. Sales are ordered by execution date and imported UTC execution timestamp, then creation timestamp and ID for deterministic ties.

## Method

- Evaluate exactly the quantities allocated to each selected sale. Add purchases at their actual execution time. The primary model pools the selected acquisition shares, using their remaining FIFO weighted entry price; an exit followed by an original later purchase starts a new holding cycle. The optional independent-lot model exposes sensitivity to pooling. Neither model uses later purchases in earlier entry prices, reinvests exit cash, or recreates the whole portfolio. Holdings outside the selected FIFO slices can change a real combined position's signals.
- Reuse native feature detection, strategy targets, the universal emergency rule and confirmation state. Cumulative tranche targets apply to the quantity acquired in the current model holding cycle; fills cannot exceed acquired shares. Targets are converted to exact quantities, then consumed FIFO.
- Read only candles through the signal session. Execute a confirmed close signal at the next actual exchange open. Purchases after the exchange close cannot use that close as a signal. Earlier foreign exchange closes cannot see the same day's later SPY close. Daily opening prices approximate execution on the primary listing; European broker fills can differ. No intraday stop execution is inferred.
- Infer quote currencies using the app's existing listing suffix mapping, not `Instrument.currency`, which can contain the broker's EUR currency. Convert stock history using a constant FX factor available at each decision, as in the native engine. Use strictly prior daily FX closes for decisions, fills and terminal marks, at most four calendar days old; no current or same-day FX close substitutes missing history.
- Require complete FIFO cost basis, matching quantities, known execution times, at least 200 earlier stock candles, sufficient benchmark history and no missing stock sessions during replay. Exclude incomplete cases explicitly rather than fabricate prices, purchases or missing pre-IPO history. Review source data for corporate actions before interpreting an individual case.
- `actual_sale`: ignore model fills later than the actual execution timestamp. Liquidate unsold shares at the actual broker execution price. Thus, no prior strategy exit means exactly the actual result. This deliberately forces a common end, even for a strategy that would normally continue holding.
- `extended_hold`: continue the unchanged rules to one common stored valuation session, keeping proceeds in cash. Remaining shares are marked at that session's converted close. These amounts include unrealized P&L and exclude a future liquidation fee. The common date is bounded by the least recent selected instrument's saved data and the export cutoff; the report must state it.
- Include the journal's allocated purchase fees and charge the actual execution's per-order fee once per modeled sell date, combining same-day modeled fills. This assumes proportional/fractional execution without a minimum tradable quantity. Compare before tax: remove allocated purchase tax from basis and actual sale tax from the reference result. Journal after-tax P&L remains a separate field; hypothetical tax depends on broader account offsets and is not inferred.
- No dividends, interest on cash, slippage, bid/ask spread, liquidity impact, tax optimization or replacement investments. No annualization. Cash is not reused across cases, and sums are the P&L of disjoint sold shares, not a self-financing portfolio backtest. Report sensitivity to pooling and concentration in a few large trades.

Meaningful tests cover execution timing, foreign versus US closing times, strictly prior FX, missing data, future-price invariance at the actual sale horizon, purchase timing and holding-cycle reset, and prevention of repeated acquisition allocation. The shared native engine equivalence tests cover the eight strategies and confirmation states.
