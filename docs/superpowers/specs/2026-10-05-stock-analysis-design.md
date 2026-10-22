# Stock analysis system

Approved in chat on 2026-10-05. The data engine owns all numerical,
statistical, indicator, screening and backtest calculations. The agent interprets
engine summaries using approved research skills. It never supplies computed
series, prices or performance numbers to the chart renderer.

## Boundaries

- Keep Vue 3, Flask SaaS and the existing independent LangGraph Core.
- Add stock-data-engine, consuming the documented read-only Market HTTP API.
- Expose schema-validated HTTP tools and a stateless MCP endpoint backed by the
  same dispatch functions. Credentials, upstream URLs and budgets are server owned.
- Persist datasets with tenant, actor and conversation scope. Chart annotations
  reference exact dates/fields in these datasets, with engine-derived values.
- The agent writes a declarative query schema (universe, window, expressions,
  condition, task, output projection). The engine executes it. Tool responses
  contain bounded summaries/previews and dataset handles, never full chart data.
  Browser artifact loading is a separate authenticated SaaS-to-engine route.
- SaaS persists stock artifacts alongside messages and forwards their SSE events.
- RAG is disabled by default; disabled mode must not depend on a knowledge service.
- Stock deployment uses its own Compose project, network, volumes, credentials,
  session cookie and host ports. Never restart the existing rag-chat-saas project.

## Research semantics

Data is unadjusted daily OHLC, volume in lots, amount in CNY. Returns are fractions.
Indicators use causal expressions with explicitly missing warmup; no eval or
arbitrary Python. Reject comparisons of incompatible units and look-ahead functions.
Calendar bars are retained for price series; zero-volume observations are excluded
from volume averages and cannot be traded. Event studies report observations per
horizon, quantiles, distributions, same-period baseline, overlap and sample warnings.
Sampling is seeded and coverage is reported. Backtests signal at close, execute at
the next tradable opening under T+1 and lot sizing, include configurable costs,
record skipped fills and show buy-and-hold on the same accounting basis. Raw-price
backtests are exploratory because corporate actions are unavailable.

## Artifacts

Version stock-artifact/1 contains datasetRef, provenance, warnings, summary,
table, charts and annotations. Charts support candlesticks, volume, indicator
panels, distributions, comparisons and equity curves. Data references in answers
use [data:datasetRef]; SaaS rejects references not returned in that run. Renderer
uses ECharts, escaped text, fixed-height responsive plots, CSV download, date
zoom, source tables and click-to-compose data references.

## Acceptance

Test calculations with hand-computable fixtures, missing/invalid data, unit errors,
overlapping events, insufficient horizons, next-open execution and costs. Test
scope boundaries, artifact persistence/replay, disabled RAG, and reference validation.
Build and test Vue; verify real market queries and desktop/mobile chart screenshots.
No paid model is required for deterministic verification.
