# Stock Research Capability Mapping

The reference site at http://192.168.3.5:8765/ was inspected live on 2026-10-05.
Whiteboard, screening, event research and algorithm backtest controls were read.
The whiteboard explicitly reported simulated prices, so its displayed returns
were not treated as numerical validation or real-market evidence. Remote scans
and database synchronization were not triggered.

| Module | Agent / engine contract | Rendering |
| --- | --- | --- |
| Indicator whiteboard | `stock_query`, task `analyze`, declarative indicators and price/separate panels; MA, EMA, RSI, Bollinger formulas, volume | OHLC, overlays, volume, individual indicator panels |
| Buy-point screening | `screenMode=latest/history/any`; `minHits` for minimum window hits; explicit Boolean conditions and bounded stock universe | Matched rows with `hitCount`; up to three matched stocks' charts; single-stock chart even for zero hits; engine-derived signal markers |
| Mathematical analysis | `stock_events`, before/after windows, 14 features, relative-price path, per-feature valid counts, forward distributions, baseline, Wilson intervals | Histograms and aligned event profiles; full saved table CSV; bounded profile pages for AI |
| Algorithm backtest | Single-stock or independent multi-stock scan; partial position sizes, separate delays, lot rounding, fees, slippage, tax, completed-trade accounting | Equity / benchmark, price chart with fill markers, multi-stock return distribution |

Numerical computation stays in the engine. The model receives at most 20 preview
rows and bounded summaries, with data references for additional field/page reads.
Event studies cap retained events at 4000 with seeded reservoir sampling and report
accepted versus retained counts. An incomplete forward window stays missing.

Safeguards retained: causal expressions, warmup before window cropping, compatible
units, suspension handling, scoped immutable datasets, unadjusted-data warnings,
and explicit coverage. No full-market claim may be made from a 300-stock sample.

Remaining differences from the reference package: whole-market asynchronous
scanning, intraday/order-book fill validation, dynamic per-rule position sizing and
holding-cost predicates, and non-causal MID/INSIDE research functions are not
implemented. Multiple stocks have separate cash; they are not a funded portfolio.
Legacy PEAK/TROUGH and frontend expression parity are not claimed. New causal
`CONFIRMEDPEAK(series,left,right)` and `CONFIRMEDTROUGH` emit on the confirmation
bar after `right` observed bars, with strict comparisons excluding ties.
`ACTIVE(start,end)` includes the start bar, excludes the end bar, and end wins
simultaneous signals. This is a causal interval state, not legacy INSIDE parity.
Missing inputs yield null; an active state is retained across unknown inputs.
These limitations must be stated when a requested rule needs them.

Live comparison additions: screening minimum hits is computed before last-hit
projection, after cropping the requested time window, excluding zero-volume bars.
`qualifiedHits` counts window hits of qualifying stocks; `matchedEvents` remains
the number of rows after screen-mode projection. Latest mode requires minHits=1.
The redundant post-crop expression evaluation in screening was removed: signals
are already validated and calculated with warmup before cropping.

Reference differences still requiring further work: per-rule positions, repeated
scale-in buys, cost-relative exit predicates, named expression marker sets, and
interactive indicator scaling. Reference full-market scans exceed the current
bounded synchronous 300-stock query contract. They need asynchronous jobs with
progress, cancellation and persisted results, not a larger synchronous timeout.
The reference price-times-volume formula is not accepted by the engine's strict
unit system; use normalized quantity ratios for comparable signals.

Validation on 2026-10-05: 26 engine tests and 7 stock answer protocol tests passed.
Prefix-invariance tests cover confirmation-date peaks and interval states;
minimum-hit tests cover cropped windows and latest-mode rejection. The deployed
HTTP and MCP schemas include minHits; Core's configured stock skill contains
ACTIVE and CONFIRMEDPEAK. Real-market verification on 000001 (last date
2026-09-11) produced five chart descriptors, eight confirmed peak hits in a
100-bar window, and 14 backtest fills. Only five explicitly requested dataset
rows were read; chart rows remained outside model context. No model calls were
made, so model selection of these new rules and total reply latency remain
unmeasured. Reproduce with scripts/verify_reference_rules.py inside the engine
container. Deploy using the private stock env file to retain the host relay URL.

Presentation repair: only the latest progress event stays expanded during work;
earlier events fold automatically. Legacy internal history JSON is converted to
clickable citations only when all references are bound to the message. Chart
metadata is refreshed from the owned engine dataset after browser loading, fixing
historical messages whose stored chart directory was empty. No chart payload is
added to the model context.
