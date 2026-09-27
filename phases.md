# DevPilot — Project Phases

**Last updated:** 2026-09-28

> The phase-by-phase build order. A phase is **done only when its exit criteria are met** — a checked box means implemented and verified, not planned. Detailed roadmap notes live in [docs/ROADMAP.md](docs/ROADMAP.md); current state is tracked in [memory.md](memory.md).

Legend: ✅ done · 🟡 in progress · ⬜ not started

---

## ✅ Phase 0 — Product & environment
Product direction, public repo, Python env, `.env` template, docker-compose PostgreSQL, DB connectivity verified.

## ✅ Phase 1 — Backend foundation *(current baseline)*
FastAPI app + `/health`, Pydantic Settings, SQLAlchemy base/session, PostgreSQL, Alembic + first migration, Project model/schemas, Project CRUD API, input validation, **dedicated test DB + pytest suite (17 tests)**, **Ruff lint/format clean**, **Docker image + compose api/migrate services**.
**Remaining:** push the initial commit to GitHub.
**Exit:** reproducible setup, clean migrations, tested CRUD, lint passing, no secrets committed. → *met locally; push pending.*

## ✅ Phase 2 — Frontend
Next.js 14 (App Router) + TypeScript + Tailwind in `apps/web`.
- [x] Auth pages (register/login) + `AuthProvider`/`useAuth` (token in localStorage)
- [x] Project list + create, project detail + edit + delete
- [x] Typed API client with error mapping (`lib/api.ts`), loading/error/empty states
- [x] Design tokens from `design.md` (`app/globals.css`, light/dark)
- [x] Vitest unit tests (API client) + production build verified (`npm run build`)

Deferred: shadcn/ui adoption (hand-rolled Tailwind primitives for now), richer
component/E2E tests, audit-trail UI.

## ✅ Phase 3 — Authentication & authorization
- [x] User model + `users` migration
- [x] Password hashing (`scrypt`) + signed JWT access tokens (`app/core/security.py`)
- [x] Register / login / me endpoints (`/api/v1/auth/*`)
- [x] `get_current_user` bearer dependency
- [x] Project ownership (`owner_id` FK) + per-owner scoping on all project endpoints
- [x] Cross-user access tests (404 on others' projects)
- [x] Rate limiting on auth endpoints (`app/core/rate_limit.py`, 429 + Retry-After)
- [x] Audit events (`audit_logs` table, `/api/v1/audit/me`)
**Deferred (later hardening, not blocking):** roles/teams (RBAC beyond ownership),
refresh tokens / token revocation, and swapping stdlib crypto for `bcrypt`/`PyJWT`
once network deps are available (isolated in `app/core/security.py`).

## ⬜ Phase 4 — GitHub integration
GitHub App vs OAuth chosen deliberately (prefer App for repo automation). Authorized repo listing, issue retrieval, secure short-lived tokens, webhook signature verification.

## ⬜ Phase 5 — Basic AI assistant
Provider-neutral model interface, structured task analysis, timeouts/retries/usage tracking, mocked tests + opt-in live tests.

## ⬜ Phase 6 — Agent system
LangGraph state/graph; planner + repository analyst; tool registry; durable run/event state; bounded retries, cancellation, failure handling.

## ⬜ Phase 7 — RAG
Repo-aware chunking, embeddings, pgvector, permission/commit-scoped retrieval, retrieval evaluation; exclude secrets/binaries/vendor content.

## ⬜ Phase 8 — MCP & tools
Typed tools, explicit permissions, server-side argument validation, timeouts/rate limits, audit logs, prompt-injection tests.

## ⬜ Phase 9 — Sandboxed execution
Disposable Docker workspace; CPU/memory/PID/disk/time limits; network off by default; no Docker socket or host secrets; bounded logs + cleanup.

## ⬜ Phase 10 — Human-in-the-loop
Approval records tied to diff hash + base commit; graph pause/resume; cancellation; stale-approval invalidation; publication-gate tests.

## ⬜ Phase 11 — Evaluation
Versioned task benchmark; task success, test pass rate, regressions, tool correctness, latency, token/cost; reproducible comparisons.

## ⬜ Phase 12 — Observability
Structured logs + run IDs; OpenTelemetry; Prometheus/Grafana where useful; metrics, redaction, retention.

## ⬜ Phase 13 — CI/CD
GitHub Actions: lint/tests/build, migration checks, dependency/container scanning, image build/publish, deployment approval + rollback.

## ⬜ Phase 14 — Deployment
Provider chosen on cost/fit; managed database, secret manager, TLS, backups/restore, health/readiness, deployment docs.

## ⬜ Phase 15 — Scaling
Redis/worker queue when needed; idempotent jobs; bounded retries; backpressure; concurrency limits; separate API/worker scaling.

## ⬜ Phase 16 — Optional Kubernetes/Terraform
Adopt only when justified; resource limits, probes, network/security policies, reproducible IaC.

## ⬜ Phase 17 — Portfolio polish
Architecture docs, demo, honest evaluation/limitations, security model, clean history, resume bullets based only on implemented results.

---

### Suggested next move
Phases 0–3 (backend) and Phase 2 (frontend) are done and verified. Next options:
1. **Verify the full stack together** on a networked machine: run the API (`make docker-up` or uvicorn) + `cd apps/web && npm run dev`, then register/login/create a project in the browser.
2. **Phase 5 (AI assistant)** — provider-neutral LLM interface (testable with a mock; real calls need an API key).
3. **Phase 13 (CI/CD)** — GitHub Actions to run backend + frontend lint/tests on every push.
