# RAG Chat SaaS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a deployable multi-user RAG knowledge-base chat application with grounded streaming answers, citation-linked document reading, and an administrator workspace.

**Architecture:** A Flask application factory exposes versioned JSON/SSE APIs and owns SQLite persistence, local sessions, encrypted settings, provider scheduling and RAG orchestration. A Vue 3 SPA consumes that API through a typed client and presents an edge-to-edge chat workspace plus a citation-bound reader. Nginx and Gunicorn run the two services on one named Compose network.

**Tech Stack:** Python 3.12, Flask 3, SQLAlchemy 2, Alembic, SQLite WAL, Argon2id, cryptography, httpx, pytest, Vue 3, TypeScript, Vite, Pinia, Vue Router, Vitest, Playwright, Motion, PDF.js, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-24-rag-chat-saas-design.md`

## Global Constraints

- The application is a separate Git repository at `F:\my_projects\rag-chat-saas`.
- Memory-service integration remains disabled.
- Credentials, prompts, answers, evidence passages and document bodies must not appear in logs or audit payloads.
- UI text is at least 12px; content pages are edge-to-edge and administrative collections use dense non-wrapping row lists.
- Consumer callers never send tenant, workspace, publication or index-build IDs.
- All mutating APIs require authenticated sessions and CSRF validation, except login and forced password replacement bootstrap flow.
- Every conversation and message query carries the authenticated owner predicate.

---

### Task 1: Backend Foundation, Schema, and Authentication

**Files:** Create `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/extensions.py`, `backend/app/models.py`, `backend/app/auth.py`, `backend/app/api/auth.py`, `backend/migrations/`, `backend/tests/test_auth.py`, `.env.example`.

**Interfaces:** Produces `create_app(config=None)`, authenticated `g.current_user`, `POST /api/v1/auth/login`, `POST /api/v1/auth/change-password`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/session`, and CSRF enforcement.

- [ ] Write tests proving bootstrap admin creation, forced password change, opaque cookie sessions, invalid credentials, CSRF rejection, logout and user isolation.
- [ ] Run `pytest backend/tests/test_auth.py -q` and verify failure before implementation.
- [ ] Implement SQLAlchemy models, WAL/foreign-key pragmas, Argon2id password hashing, hashed sessions, CSRF and bootstrap logic.
- [ ] Run the focused test and commit `feat: establish saas authentication foundation`.

### Task 2: Encrypted Settings, Users, and Provider Accounts

**Files:** Create `backend/app/crypto.py`, `backend/app/admin.py`, `backend/app/api/admin.py`, `backend/tests/test_admin.py`.

**Interfaces:** Produces administrator-only RAG endpoint settings, user lifecycle, provider/account CRUD, masked secret responses, concurrency/cooldown fields, and health summaries.

- [ ] Write tests for role enforcement, Fernet ciphertext persistence, masked responses, account validation and disabled-user sessions.
- [ ] Run focused tests to red, implement minimal APIs, rerun and commit `feat: manage encrypted saas connections`.

### Task 3: RAG Consumer Client and Citation Proxy

**Files:** Create `backend/app/clients/rag.py`, `backend/app/api/knowledge.py`, `backend/tests/test_rag_client.py`.

**Interfaces:** Produces knowledge-base listing, retrieval, citation page metadata, page content and Range-preserving document proxy endpoints without exposing the configured consumer key.

- [ ] Write respx/httpx tests covering timeout/error mapping, metadata retention, exact query/citation binding and Range headers.
- [ ] Implement the typed client and authenticated proxy APIs, test and commit `feat: connect saas to rag consumer api`.

### Task 4: Provider Pool, Context, and Streaming Chat

**Files:** Create `backend/app/clients/openai_compatible.py`, `backend/app/provider_pool.py`, `backend/app/context.py`, `backend/app/chat.py`, `backend/app/api/chat.py`, `backend/tests/test_chat.py`.

**Interfaces:** Produces conversation/message CRUD, weighted least-in-flight selection, semaphores, retry/cooldown, grounded prompt construction, deterministic citation validation, rolling summary, and SSE chat events.

- [ ] Write tests for owner isolation, account concurrency, failover, history trimming, incomplete-message exclusion, citation validation and persisted interrupted streams.
- [ ] Implement, run tests and commit `feat: stream grounded multi-turn chat`.

### Task 5: Vue Application Shell and Login

**Files:** Create `frontend/package.json`, `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/router.ts`, `frontend/src/api/`, `frontend/src/stores/`, `frontend/src/views/LoginView.vue`, `frontend/src/views/PasswordChangeView.vue`, `frontend/src/styles/` and component tests.

**Interfaces:** Produces guarded routes, session bootstrap, forced-password route, CSRF-aware client and the full-height responsive shell.

- [ ] Write Vitest tests for login, forced change and route guards.
- [ ] Implement with system typography, immediate active feedback, keyboard focus, reduced motion/transparency and no decorative content margins.
- [ ] Run frontend tests and commit `feat: build saas application shell`.

### Task 6: Conversation Workspace and Evidence Reader

**Files:** Create `frontend/src/views/ChatView.vue`, `frontend/src/components/chat/`, `frontend/src/components/evidence/`, `frontend/src/stores/chat.ts`, frontend tests and Playwright acceptance tests.

**Interfaces:** Produces conversation sidebar, inline knowledge-base selector, streaming answer bubbles, clickable citations, complete PDF reader, page jump, normalized highlights, full-result view and mobile sheet.

- [ ] Write component tests for streaming, source links, reader navigation, detailed results and empty/error states.
- [ ] Implement Motion-based interruptible symmetric reader transitions and PDF.js Range loading.
- [ ] Verify desktop/mobile screenshots, focus, reduced motion and canvas pixels; commit `feat: deliver grounded chat workspace`.

### Task 7: Administrator Workspace and Statistics

**Files:** Create `frontend/src/views/AdminView.vue`, `frontend/src/components/admin/`, `backend/app/api/stats.py`, backend/frontend tests.

**Interfaces:** Produces dense row lists and bounded aligned forms for RAG settings, providers/accounts, users, health, concurrency and usage statistics.

- [ ] Test authorization, masking, filtering, non-wrapping rows, overflow behavior and modal dismissal protection.
- [ ] Implement and verify responsive layouts; commit `feat: add saas administration workspace`.

### Task 8: Deployment, Acceptance, and Operations

**Files:** Create `compose.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `scripts/start.ps1`, `scripts/backup.ps1`, `scripts/restore.ps1`, `README.md`, end-to-end tests.

**Interfaces:** Produces one-command startup, health checks, persistent SQLite data, SSE proxying, clean bootstrap, backup/restore and server deployment documentation.

- [ ] Validate clean-volume bootstrap, restart persistence, health, backup/restore and stub-provider/RAG end-to-end flow.
- [ ] Run all backend/frontend/browser tests and `docker compose config --quiet`.
- [ ] Audit repository for secrets/build outputs and commit `build: package rag chat saas`.

### Task 9: Existing RAG Console Alignment

**Files:** Modify the existing `rag-service` console components and tests identified by the UI audit.

**Interfaces:** Consumes the canonical consumer evidence projection and produces consistent lists/forms, citation reader interaction, reduced internal-ID exposure, and deployable console assets.

- [ ] Inventory all console routes, list/form primitives and evidence flows with browser screenshots.
- [ ] Add regression tests, replace client-side evidence merging, align high-density layouts and Apple interaction behavior.
- [ ] Run console tests and browser acceptance across desktop/mobile, then commit focused changes in the RAG worktree.
