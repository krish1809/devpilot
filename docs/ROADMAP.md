# DevPilot — Phase-wise Roadmap

This is the agreed target plan. A phase is complete only after its exit criteria are met; roadmap items are not claims of implementation.

## Phase 0 — Product and environment
- [x] Product direction, workflow, and initial architecture
- [x] Public GitHub repo and local clone
- [x] Python environment and dependencies
- [x] Environment template and ignored local `.env`
- [x] Docker Compose PostgreSQL
- [x] PostgreSQL connectivity verified

## Phase 1 — Backend foundation (current)
- [x] FastAPI app and `/health`
- [x] Pydantic Settings
- [x] SQLAlchemy base/session
- [x] PostgreSQL connection
- [x] Alembic and first `projects` migration
- [x] Project model and schemas
- [x] Project create/list/get/update/delete API
- [x] Manual CRUD flow in Swagger
- [x] Dedicated test DB and safe pytest fixtures
- [x] Automated CRUD/error/validation tests
- [x] Ruff lint and format checks
- [x] Consistent error handling and validation review
- [x] Secret/gitignore and migration review
- [x] Containerized deployment (Dockerfile + compose api/migrate services)
- [ ] Meaningful commit/push

**Exit:** reproducible setup, clean migrations, tested CRUD, lint passing, no secrets committed.

## Phase 2 — Frontend
Next.js, TypeScript, Tailwind, shadcn/ui; project list/create/detail; typed API client; loading/error/empty states; build and tests.

## Phase 3 — Authentication and authorization
User identity, secure auth strategy, project ownership, RBAC, rate limiting, audit events, cross-user access tests.

## Phase 4 — GitHub integration
Choose GitHub App/OAuth deliberately (prefer App for repo automation where suitable); authorized repository listing, issue retrieval, secure token handling, webhook verification if used.

## Phase 5 — Basic AI assistant
Provider-neutral model interface, structured task analysis, timeouts/retries/usage tracking, mocked tests and opt-in live tests.

## Phase 6 — Agent system
LangGraph state/graph; planner and repository analyst; tool registry; durable run/event state; bounded retries, cancellation, and failures.

## Phase 7 — RAG
Repository-aware chunking, embeddings, pgvector, permission/commit-scoped retrieval, retrieval evaluation, exclude secrets/binaries/vendor content.

## Phase 8 — MCP and tools
Typed tools, explicit permissions, server-side argument validation, timeouts/rate limits, audit logs, prompt-injection tests.

## Phase 9 — Sandboxed execution
Disposable Docker workspace, CPU/memory/PID/disk/time limits, network disabled by default, no Docker socket or host secrets, bounded logs and cleanup.

## Phase 10 — Human-in-the-loop
Approval records tied to diff hash/base commit, graph pause/resume, cancellation, stale approval invalidation, publication gate tests.

## Phase 11 — Evaluation
Versioned task benchmark; task success, test pass rate, regressions, tool correctness, latency, token/cost metrics; reproducible comparisons.

## Phase 12 — Observability
Structured logs and run IDs; OpenTelemetry; Prometheus/Grafana where useful; metrics, redaction, retention.

## Phase 13 — CI/CD
GitHub Actions for lint/tests/build, migration checks, dependency/container scanning, image build/publish, deployment approval and rollback.

## Phase 14 — Deployment
Select provider based on cost/fit; managed database, secret manager, TLS, backups/restore, health/readiness, deployment docs.

## Phase 15 — Scaling
Redis/worker queue when needed, idempotent jobs, bounded retries, backpressure, concurrency limits, separate API/worker scaling.

## Phase 16 — Optional Kubernetes/Terraform
Adopt only when justified; resource limits, probes, network/security policies, reproducible IaC, documented complexity/cost.

## Phase 17 — Portfolio polish
Architecture docs, demo, honest evaluation and limitations, security model, clean issues/history, resume bullets based only on implemented results.
