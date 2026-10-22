# Stock SaaS and Core Reliability and UI Audit

**Goal:** Diagnose and repair runtime failures, and make the SaaS and Core interfaces clear, practical, responsive, and visually consistent through evidence-based auditing.

**Architecture:** Preserve the current Vue SaaS and Flask/static Core boundaries. Validate provider configuration at its owner, propagate bounded diagnostic error codes to the SaaS, and keep mathematical analysis in the data engine. Improve existing controls and workflows rather than introducing a second administration system.

**Tech Stack:** Flask, SQLite, httpx, Vue 3, TypeScript, ECharts, Vitest, Playwright, Docker Compose.

## Constraints

- Preserve production credentials, user data, model selections and grants unless a specific verified error requires correction.
- Deploy only services in the stock-analysis project. Other projects share Docker and must not be refactored or stopped.
- Do not print secrets, upstream arbitrary bodies, or private configuration files.
- RAG remains optional and disabled by default. Search is user opt-in and administrator-controlled.
- Inspect live state before relying on earlier findings. No claim of completeness based only on unit tests or page availability.

## Work and Acceptance

- [x] Capture current provider routing, recent run failure categories, Docker health and frontend baseline test results.
- [x] Repair verified provider URL/protocol errors; validate complete streamed responses and distinguish HTML/non-SSE replies from truncated streams.
- [x] Provide safe administrator connection verification with actionable, credential-free diagnostics. Verify successful and failed models, tools, timeouts, authentication and malformed responses without unbounded retries.
- [x] Propagate actionable failure reasons through persisted SaaS messages and live streams; provide appropriate retry/recovery controls.
- [x] Audit Core navigation, provider tree, model list, settings and credential editor, drawers, search, keyboard focus, errors and dirty-state handling at desktop/mobile sizes in light/dark themes.
- [x] Audit SaaS login, administration, chat composer, history, streaming process, sources, charts/tables and analysis workspace for navigation, layout, loading/error/empty states, keyboard access and theme consistency.
- [x] Fix each reproducible frontend issue and cover material behavioral changes with focused tests.
- [x] Verify meaningful chart pixels, table content, grouping, exports and conversation/analysis navigation using isolated fixtures and real APIs where appropriate.
- [x] Build and run relevant backend/frontend suites, inspect screenshots, deploy changes, verify live health and representative workflows, then repeat the completion audit against this full checklist.

## Evidence Ledger

The current live third-party gpt-5.6-sol provider was configured at https://api.suyehanzi.online without /v1. POST /chat/completions returned HTTP 200 HTML with zero SSE frames. GET /v1/models listed the selected model; POST /v1/chat/completions returned valid SSE with finish_reason=stop in a minimal successful probe. Other probes intermittently hit ConnectTimeout. Revalidate configuration before changing it because the user may have corrected it.

The Docker engine and stock services are currently running after stale host socket isolation. Many unrelated services share this engine. Investigate resource pressure without changing other projects' lifecycle or settings.

## UI Review Ledger

| Before | After | Why |
| --- | --- | --- |
| Distinct model failures collapse into a generic incomplete reply | Endpoint, format, authentication, rate limit, connect/read timeout and interrupted-stream messages have distinct recovery guidance | Users need a reason and appropriate recovery action |
| Provider setup has no end-to-end model connection verification | Saved models have separate text and tool-call tests, measured duration, safe status/HTTP codes and usage accounting | A saved configuration alone does not prove a working model |
| Failed processing shows an early duration and a successful check mark | Terminal progress and actual latency are persisted; interrupted steps are marked failed | A 120-second timeout must not appear to complete in 0.2 seconds |
| Model identity disappears on failed-message rollback | Failure persistence restores the model selected by the Core model event | History and administrator diagnosis must refer to the actual model |
| A disconnect after durable completion changes the answer to failed | Completed answers remain completed after the transport closes | Transport lifetime must not override an already committed result |
| Blank Core API base URL has no format example | Provider and direct-model editors show the complete Chat Completions base URL format | Helps prevent homepage URLs being mistaken for API endpoints |
| Model list lacks search and connection verification | Model/name/key search, enabled filter, empty results and per-model test actions | Makes configuration review and troubleshooting practical |
| Escape/backdrop silently discard dirty configuration | Escape/backdrop preserve changes; explicit cancel/close confirm discard | Avoids losing credentials or configuration edits accidentally |
| Empty local SaaS suppliers disappear | Suppliers with no accounts remain visible and expose an add-account action | A new supplier must have a usable path to its first model account |
| Non-retrieval answers can show empty retrieval diagnostics | Retrieval diagnostics require an actual query ID | Avoids reporting retrieval when none ran |
| Model-selection saved feedback can retain a stale selection | Selected model synchronizes with the saved Core response; unavailable/tools-disabled/read-only states are explicit | Makes the saved route and usable options clear |
| Only global/direct model egress is possible | Providers have an optional HTTP(S) proxy, inherited by models, discovery, gateway and billing | Allows a selected supplier to use the user's existing local proxy |
| Backend container recreation leaves Nginx using an obsolete IP | Docker resolver with 5-second DNS validity resolves the backend dynamically | Prevents persistent 502s after backend deployments |

## Verification Evidence

- Core: 165 tests passed with final protocol, proxy, bounded connection recovery, auth and configuration changes.
- Frontend: all 33 files / 125 tests passed; after the connection-event label change, 14 focused chat/admin tests passed. Production TypeScript and Docker builds passed.
- Backend: initial full suite returned 132 passed and one missing local optional MCP dependency. Installed the same MCP 2.3.0 version as production; all 8 search-manager tests passed. Final Core bridge suite includes 13 tests covering failure timing, model identity, completion and disconnect behavior.
- Provider tree and credentials: real isolated Core API writes, desktop/mobile, both themes; no production password or credentials were changed.
- Core diagnostics: model filtering, failed/successful test results, dirty-state protection, proxy configuration save and drawer boundaries passed on desktop/mobile.
- Core overview, runs, apps, tools, usage and models: both themes and widths 1440/390 passed without page overflow or browser exceptions. Screenshots in artifacts/verification.
- SaaS: login/admin theme checks, model-selection save, search manager, HTTP proxy settings, session expiry, failed-history duration and retry controls passed on desktop/mobile.
- Real engine artifacts: 300-row analysis, 12-row events and 23-row backtest. Nonblank colored chart pixels (desktop 19746, mobile 8936), reference insertion, historical metadata recovery, grouped directory, fullscreen, PNG export, complete table export and theme persistence passed.
- Table fixtures: stock directory, record details, pagination, aggregate table, fullscreen table, light/dark and compatible real chart rendering passed. Unsupported table data does not become a fabricated line chart.
- Streaming: heavy reasoning animation remains disabled; answer fade, manual reading position, smooth follow resumption and latest-reply button passed on desktop/mobile.
- Deployment regression: reproduced HTTP 502 after backend recreation with the original static Nginx upstream. After the dynamic DNS fix, recreated only the stock backend while leaving the stock frontend running; public /api/v1/health returned 200 again.

## Supplier Network Findings

The user had already corrected the provider URL to /v1 before this implementation. That correction was preserved, as was the gpt-5-6-sol default selection. The original missing /v1 produced 200 HTML, not model SSE; the client now rejects that immediately with INVALID_PROVIDER_ENDPOINT.

No-key network traces locate intermittent direct failures in TLS establishment: TCP completed in approximately 45-155 ms, then start_tls failed at the configured timeout. Restricting the TLS version did not reliably solve this; certificate verification remains enabled.

The existing host HTTP proxy at host.docker.internal:10808 returned an authentication response in 737 ms. Explicit proxy text and complete tool-call probes subsequently succeeded (about 12 seconds each), but some full Agent attempts still encountered CONNECT_TIMEOUT. Proxy configuration therefore improves routing options and is not proof that the supplier is consistently available. The selected supplier alone uses this local proxy; other suppliers retain their prior routes. The proxy application must remain running, and its field can be cleared in the provider drawer to return to direct access.

Agent model connection setup may retry only once for ConnectTimeout/ConnectError before any HTTP request bytes are sent. The retry emits MODEL_CONNECT_RETRY. Admin tests do not auto-retry; authentication errors, read errors, partial responses and tools are never replayed. Unit tests verify these boundaries. This is recovery from an unstarted request, not a fallback to a different paid model.

## Final Deployment Acceptance

The final live SaaS -> Core -> current_time -> model -> persisted answer probe completed successfully using gpt-5.6-sol. Run 79185558-9abc-4755-9c65-b5945e5aa40f finished with status COMPLETED, latency 26536 ms, no error code, and terminal progress PROCESS_COMPLETED. The probe explicitly requested the stock answer protocol and did not request search or stock data. This verifies the complete current-model tool workflow, not universal supplier stability or every stock analysis method.

Some preceding complete supplier responses ignored the required stock_answer boundary and needed a format-repair round; that additional request could encounter the same intermittent TLS failure. The stock output boundary remains enforced so process output stays in events rather than leaking into the final answer.

Final production checks returned HTTP 200 from the public SaaS health endpoint. The stock Core, backend and data engine containers were healthy and the frontend was running. The isolated preview and Vite verification servers were stopped; production services remain running. All acceptance items above have been reviewed. Residual supplier TLS availability and answer-protocol adherence remain external compatibility limitations, exposed through bounded diagnostics rather than hidden by unlimited retry or model fallback.
