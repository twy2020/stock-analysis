# Stock Lab Historical Reference

Historical research-contract notes. Use the root README for current setup,
login, relay ports and deployment instructions.

Stock research workspace built on the existing Vue SaaS and independent Agent Core.
The model designs query schemas and interprets results; the data engine owns queries,
indicators, screening, descriptive statistics, event studies and exploratory backtests.

## Start

```powershell
./scripts/start-stock.ps1
```

Stock chat: http://127.0.0.1:18110/
Stock Core console: http://127.0.0.1:18210/admin
Initial login is in `.stock-private/initial-login.txt`; console token in
`.stock-private/admin.token`. Change the initial password after login.
All private files, Docker networks and named volumes are independent from the running
`rag-chat-saas` and other Core installations. Setup copies model configuration and
credential files from this project's Core copy without modifying the source service.
No CAD/OCR/RAG integrations are registered in the stock deployment.

Set `MARKET_API_URL` and ports in `.stock-private/stock.env`. The default market source
is `http://192.168.3.5:8765/api/db`. If the LAN address changes, update it and recreate
the data-engine container. Compose uses `10.252.251.0/24` by default; override
`STOCK_NETWORK_SUBNET` if needed. Core configuration persists in `.stock-private/core.json`.
After changing tool schemas, run `bootstrap_stock.py --refresh-tools` and recreate Core.

On this Windows host, `collabflow-auth-private` occupies `192.168.0.0/20`, which
overlaps the market LAN. An authenticated host relay on port 18765 is enabled by
`.stock-private/market-relay.enabled`; `start-stock.ps1` starts it in the background.
The engine uses `http://host.docker.internal:18765/api/db` and `MARKET_API_TOKEN_FILE`.
The relay accepts only the fixed market routes and uses the engine token. On a host
without the overlap, remove the marker and restore the direct market URL (clear
`MARKET_API_TOKEN_FILE`). For a different upstream, launch `scripts/market-relay.py`
with `--upstream` set to that server's origin. No existing Docker network is changed.

## Query Contract

Tools: `stock_schema`, `stock_health`, `stock_query`, `stock_events`, `stock_backtest`,
`stock_dataset`, `stock_annotate`, `stock_sql`. All are exposed by authenticated HTTP
at `/tools/execute`, and by stateless MCP at `/mcp`. MCP uses `params._meta.context`
for the trusted gateway's delegated scope, outside model arguments. Core has a
registered `stock` HTTP-to-MCP bridge as well. MCP aliases require explicit grants;
the deployment uses direct tool names to avoid presenting duplicate tools to the model.

```json
{
  "task": "screen",
  "universe": {"board": "cyb", "excludeST": true, "sample": 100, "seed": 2026},
  "window": {"bars": 300, "warmup": 260},
  "condition": "CROSS(MA(CLOSE,5),MA(CLOSE,20))",
  "output": {"fields": ["code","name","date","close"], "previewRows": 5}
}
```

The model can select a source (`bars`, `snapshot`, `stocks`, `rank`, `dates`),
stock universe, dates, causal indicator expressions, boolean conditions, filters,
grouping and aggregates (count/sum/mean/median/sample std/min/max/quantile), output
fields, ordering and summary projections. Raw SQL supports a single SELECT/WITH over
stocks/bars via sqlglot validation and the upstream read-only connection. Set
`STOCK_ALLOW_SQL=false` to disable it.

Tool responses contain summaries, at most 20 preview rows and immutable `datasetRef`
handles, bounded to 20 KB for analysis artifacts. Chart rows use a separate SaaS
route authenticated by message ownership. `stock_dataset` reads specific fields or
pages of summaries, up to 20 rows and 20 KB per request. Nested summary fields can
be selected by dotted paths; oversized reads must narrow fields/limit. References use `[data:ds_...]` and must
be returned or re-read in the current run. Annotations contain a dataset, date, field
and label; the engine derives their numeric values. Charts never consume model-written
series or coordinates. Message artifacts survive SSE reconnection and page reload.

## Research Semantics And Limits

- Prices are unadjusted CNY, volume is lots, amount is CNY; returned yields are fractions.
- `PCTCHANGE` expressions return percent, whereas statistics and API yields are fractions.
- Missing values remain missing under NOT; logical operators require predicates.
- SMA volume averages use active observations. Price calendars retain zero-volume bars.
- Event horizons count observed bars, including suspension placeholders. Per-horizon
  denominators exclude unavailable future data. Cooldown sets minimum event separation.
- Event baseline uses the same eligible stock/date range. Wilson intervals assume
  independent samples and are not significance evidence for correlated events.
- Single-stock backtests use close signals/next open, T+1 and 100-share lots; one-price
  and suspension bars skip fills. Costs are simplified constants. Corporate actions,
  historical ST status and detailed daily price-limit rules are unavailable.
- Comparisons align on shared dates. Sampling is seeded; selected/scanned/skipped/capped
  coverage is reported. Queries are bounded to 300 stocks, 6000+1000 bars and 90 seconds.
  Sampled results are not full-market conclusions. Snapshot aggregates operate on the
  requested returned slice: request sufficient `output.limit` and inspect `limitReached`.
- Charts show at most 2000 price bars; browser table previews show 200 rows. CSV exports
  retrieve the full saved query table (up to 5000 rows) through the owned browser endpoint,
  without expanding the model context. Dataset limits and actual coverage are reported.
- Chart expand opens a dark frosted analysis workspace: generated-chart tabs, engine
  metrics, data/source views and PNG/CSV exports on the left, the current AI conversation
  on the right. Narrow screens stack these regions. Chart/row references enter the composer.
- Dataset TTL is 30 days; expired historical artifacts require a new query. Data files
  are immutable and scoped by tenant, actor and conversation.

RAG defaults off in SaaS and Core, including knowledge-list startup calls and tool
registration. SaaS administrators control availability in Admin -> System Settings
through a persisted `system.features` setting; `RAG_ENABLED` is the initial fallback.
The composer contains no RAG toggle. To enable it later, configure the knowledge
service/callback, enable the administrator setting and the Core caller's `ragEnabled`.
New conversations then show a knowledge picker outside the input box. Search is a
future separately granted tool. Disabling the setting blocks subsequent retrieval
callbacks and removes knowledge-base identity from subsequent Core requests.

## Verification

The four research modules and remaining differences are mapped in
[`stock-capability-audit.md`](stock-capability-audit.md). Historical screening
uses `screenMode=history/any`; event `before/after` profiles are accessible through
bounded `stock_dataset` profile pages; backtest `execution` supports position sizes
and independent buy/sell delays. Multi-stock results summarize separate cash accounts.

```powershell
./stock-data-engine/.venv/Scripts/python.exe -m unittest discover -s stock-data-engine/tests -v
cd agent-core
./.venv/Scripts/python.exe -m unittest discover -s tests -v
cd ../rag-chat-saas/backend
../.venv/Scripts/python.exe -m pytest -q
cd ../frontend
npm test
npm run build
```

Tests use deterministic fixtures/mocked model traffic, not paid model calls.

`node scripts/verify-stock.mjs` in the frontend runs real-data browser checks.
Set `STOCK_VERIFY_SEND=true` to additionally submit a short test message through
the real configured model. This opt-in check makes a paid model request and records
`sendVerified` in the browser report. Temporary verification sessions are revoked.
Set `STOCK_VERIFY_SAVED=true` to reuse existing, unexpired verification datasets when
the market source is unavailable. This validates saved-data rendering and exports,
not current market connectivity.
