# Stock Web Research

Search uses npm `ai-search-mcp@0.4.1` from
https://github.com/zhulingyu666/ai-search-mcp (not the Rust namesake).
`SEARCH_REGION=cn-zh` selects free public engines, with no model key.
Browsing uses `dhole-mcp==16.2` from
https://github.com/ouli-1242/dhole-mcp, plus Patchright Chromium.
PDF/OCR extras and site crawling are outside this initial read-only adapter.

Flow: stock Core HTTP/MCP bridge -> authenticated SaaS adapter -> official MCP
SDK stdio session -> search or Dhole native MCP tool. The registry is configured
by scripts/configure_stock_web.py; existing administrator registry edits are
retained on subsequent startup. Only the stock Docker backend installs these
optional dependencies (`STOCK_WEB=1`). No extra network port is exposed.

The SaaS administrator's feature settings control availability. It defaults off.
When opened by the administrator, a globe checkbox appears in the chat composer;
each run defaults off and stores its own Boolean opt-in. Core removes all tools
belonging to the stock-web plugin when that run has not opted in. The callback
also requires an authenticated service, enabled administrator setting, owned
conversation and active opted-in run. Opening the feature does not change RAG.

Search returns at most eight results. Fetch defaults to 4000 characters, with
8000 maximum and offset/focus support. Adapter output is bounded to 18KB. Source
links and upstream truncation/next_offset metadata are retained. No search-result
HTML, complete crawled site or model-created stock calculations are requested.
Stock numerical work stays in the data engine; external page claims require
source links and dates, and are not interchangeable with engine evidence.

Only public HTTP/HTTPS pages are accepted. Credentials in URLs, private DNS
answers and nonstandard ports are rejected. Dhole retains its own redirect and
SSRF checks. No caller-specified headers, cookies, methods, browser actions,
local-file parsing, login, cache deletion or arbitrary commands are exposed.
Each conversation has a separate runtime cache directory. Two web calls may be
in flight at once; subprocess sessions are closed at the end of a call, bounded
by a 55-second timeout. Free engine failures must be reported as unavailable
evidence; an empty result is not proof that a stock event does not exist.

Deployment: `docker compose --env-file .stock-private/stock.env build backend core
frontend`, then update only those stock services after checking active runs.
The chat_runs.web_enabled column is installed by the Alembic migration.

Verification (2026-10-05): stock backend, Core and data engine are healthy.
The migration has one head and a temporary-database upgrade preserves existing
data. Deployed native search returned three results from the so360 engine;
Dhole fetched Example Domain successfully. Neither smoke call used a model.
Desktop (1440px) and mobile (390px) browser checks verified default-off,
opt-in forwarding, hidden entry when administrator-disabled, and no overflow.
Browser checks use mocked authentication and API fixtures; a complete model-led
research conversation has not been exercised by these checks.

Enable in the SaaS administration page under system settings / feature access,
then re-enter chat to use the globe checkbox. The deployed administrator setting
remains disabled. The unrelated development Docker project is not updated.
