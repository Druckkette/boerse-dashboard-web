# Private RS-tranche reentry research

This extends the journal exit comparison, using the same frozen acquisitions, price histories, global settings, exclusions, FX policy and two valuation horizons. It never places orders or modifies live strategy settings.

```sh
python -m app.research.rs_reentry_backtest /protected/input-reconciled.json /protected/results-rs-reentry.json
```

Inputs and personalized results remain private under ignored `output/journal-exits-*/` directories and a protected NAS backup. The result records the input SHA-256. A documented, source-verified split normalization may be supplied in the research input; it does not change the journal's original executions.

## Rules

- Sell signals reuse the native RS strategy targets, confirmations and emergency feature. Only RS and emergency features affect these two strategy targets; an equivalence test compares the optimized pass with the full native feature pass.
- SMA: the first two targets (normally 25% + 25%) depend on the 21-SMA of the **RS line**, including the second stage's three-close confirmation. Both return on an upward RS/21-SMA cross. A full remaining-position exit caused by the 50-SMA returns on an upward RS/50-SMA cross.
- EMA: the existing global 21/34/50-EMA cumulative targets apply. With default core/step parameters, they are 60/80/100%, including the flexible portion. An incremental exit is assigned to the deepest active average responsible for the native target. Its sold shares return only on an upward cross of that same average.
- An upward cross requires previous RS at or below its average and current RS strictly above it, on two final common stock/benchmark closes. A stale RS date cannot generate repeated crosses. Merely being above an average does not trigger a buy. Foreign closing times cannot see a later US close.
- Signals execute at the next real primary-exchange open. Sell and rebuy events record signal session, RS session, execution time, quantity, fees and matched prior sale tranches. Signals continue to be observed after a full RS exit, permitting repeated exit/reentry cycles.
- The existing emergency rule remains active (normally 7% below remaining weighted entry). A tranche sold because of an emergency is not automatically repurchased on an RS cross. Earlier RS-caused exits retain their own cross eligibility. An active emergency suppresses new reentry signals that session. Rebuys establish new entry prices for subsequent emergency checks.
- Original manual purchases occur only at their actual times, with allocated original purchase fees. They are funded with their original external cash; hypothetical exit cash is not silently used to replace their planned contribution. Only the FIFO shares assigned to each selected sale are modeled, not other holdings or a whole self-financing portfolio.
- Native cumulative sell targets use original acquisition units, with current RS-sold units reduced again when repurchased. In the same-share primary variant, units and physical shares agree. For sale-cash sensitivity, units track restored tranche exposure while physical quantities vary. Later original acquisitions increase the base only when executed. The sell-only control starts a fresh holding cycle on an original purchase after a full exit, matching the preceding journal replay. Reentry variants retain still-open sold-tranche claims across a flat position so that those tranches can return.

## Capital and costs

The primary `same_shares` variant restores exactly the aggregate physical shares sold by the matching tranche(s). Available cash from that **individual sale case** funds the order first. If insufficient, explicit additional capital covers the shortfall, including the order fee. Remaining cash stays in that case; cash is not shared across stocks. Every original and additional contribution is subtracted from ending equity when calculating P&L. Injected cash is not profit and no unreported margin balance is permitted. Report additional contributions alongside P&L; their sum across independent cases is not a minimum capital requirement for a real combined portfolio.

The `sale_cash` sensitivity reinvests only the matched tranches' net proceeds, including the rebuy fee. It can restore fewer shares at higher prices or more at lower prices; it never injects additional cash. If the reserved proceeds cannot cover a fee, no buy is executed.

One modeled order fee applies per direction/open within each case, including when several tranches cross back simultaneously. The actual-time terminal liquidation is a separate fee, even after a partial sale at the same day's open. Original buy fees remain allocated to selected shares. Fractional quantities are assumed tradable. Historical FX uses strictly prior daily closes at most four calendar days old. Dividends, cash interest, taxes, spread, slippage and liquidity impact are excluded, as in the preceding comparison.

`actual_sale` values remaining shares at the actual broker execution price and deducts a terminal exit fee; all later events and later cash contributions are excluded. `extended_hold` continues to the same common stored valuation date, with unliquidated shares marked at close and no hypothetical future exit fee. Its results include unrealized P&L. Neither horizon selects the best historical crossing parameters or annualizes independent cases.

## Verification

Tests cover native target equivalence, repeated reentry after full exits, exact share restoration and matching, same-open fee consolidation, explicit funding and cash conservation, no reentry for emergency tranches, same-day execution cutoffs and invariance of earlier P&L/funding under future price changes. The sell-only control is also compared per case/horizon against the preceding frozen journal replay to isolate the reentry change.
