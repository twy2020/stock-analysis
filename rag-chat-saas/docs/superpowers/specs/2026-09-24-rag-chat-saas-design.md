# RAG Chat SaaS Design

Status: Approved

Build a single-organization, multi-user knowledge-base chat SaaS using Flask, SQLAlchemy, SQLite, Vue 3 and TypeScript. It consumes the scoped `/api/v1/consumer/**` contract from `rag-service`, supports OpenAI-compatible SiliconFlow and DeepSeek accounts, stores isolated conversations, streams grounded answers with citations, and opens citation-bound full documents at the matching page. Administrators configure RAG, model accounts, concurrency, users, health and usage. Deployment uses Docker Compose with one explicitly named network.

The frontend is a full-height, edge-to-edge application. Conversation chrome and the evidence reader follow Apple interaction principles: immediate press response, spatially symmetric and interruptible panels, critically damped motion, restrained translucency, system typography, reduced-motion/transparency support, and dense row-based administration views. UI text is at least 12px. The reader resizes the conversation on desktop and becomes a full-screen sheet on narrow screens.

Security requirements: Argon2id passwords; forced first password change; opaque hashed sessions in HttpOnly cookies; CSRF on mutations; encrypted credentials using an environment master key; owner predicates on every conversation/message query; administrator APIs never return decrypted secrets; audit events exclude prompts, answers, evidence passages and credentials.

Conversation context uses a persisted rolling summary plus recent completed turns and current RAG evidence. Memory-service integration is disabled. Provider selection is weighted least-in-flight with per-account concurrency, cooldown and failover.
