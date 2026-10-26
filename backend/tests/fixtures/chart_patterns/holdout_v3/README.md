# Source cases selected independently before the first v3 evaluation

The source labels and date windows were selected from the official IBD/MarketSmith
[*Top Stocks 2019*](https://shop.investors.com/images/promotional/shop/assets/pdf/TopStocks-2019.pdf)
before either the baseline or proposed detector was run on these cases. They were
not part of the previous five published examples or the book calibration cases.

| Case | Source label / intended check | Physical PDF pages |
| --- | --- | --- |
| ADBE, July–December 2019 | Cup with Handle, breakout December 13 | 169–170 |
| EW, spring–July 2019 | Cup with Handle, breakout July 22–24 | 109–110 |
| OLED, April/May–June 2019 | Cup with Handle, breakout June 18 | 65–66 |
| MKTX, August–December 2019 | Cup with Handle formed by December 4 | 73–74 |
| ROKU, September 2018–May 2019 | Source calls it Cup with Handle but explicitly states 66% depth; the entire base must be excluded under the chapter/default maximum of 50% | 89–90 |
| BLD, May/June 2018–August 2019 | Source states 53% depth; same exclusion check, **unscorable** because the historical quote could not be retrieved | 37–38 |

The two depth cases are exclusions against the configured rule, not a claim that
the publisher mislabeled them. Any independently valid smaller base is outside
the exclusion window. A failed trade is not automatically a negative shape label.

Five OHLC arrays were retrieved through yfinance with `auto_adjust=False`, so OHLC
are adjusted for splits but not for dividends. Each file ends at its observation
date. No publisher chart images or article text are included. BLD returned a
missing-symbol response from Yahoo and HTTP 404 from Stooq; it remains in the
manifest and is never counted as a correctly rejected case.

The manifest SHA256 before evaluation is
`0a8a45e0dd1508c7a929e435dd4a8c094fbc2ccdff3e1c7c2783f038ff43dc35`.

Run from `backend`:

```sh
python -m scripts.evaluate_chart_holdout_v3 --output /tmp/holdout-v3.json
python -m scripts.evaluate_chart_holdout_v3 --module-source /tmp/chart_patterns_v2.py --output /tmp/holdout-v2.json
```

The evaluator reports four positive coverage checks and one usable depth
exclusion separately. It requires matching pattern kind, left-rim date window and
detection window, replays detections without future data, preserves misses, and
reports bad or missing inputs as unscorable. This selected sample is too small to
estimate precision across the stock universe or investment returns.

After the first evaluation (v3 0/4, v2 1/4), MKTX exposed a floor-location
regression and this set was used for a correction. Final v3 is 1/4. These cases
are now calibration/regression data, not an independent validation of final v3.
The first and final reports are retained in `docs/`; see
`docs/chart-analysis-robustness-v3.md` for the complete evaluation history.
