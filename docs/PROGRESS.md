# DevPilot — Progress Report

**As of:** 2026-09-30
**Roadmap authority:** [PLAN.md](PLAN.md) (9 phases). This file tracks progress against those phases; it does not define them.

## Summary
Phase 1 (backend foundation) is complete and verified. Parts of Phase 3
(frontend + basic JWT auth) were built out of order and work. The critical
next milestone — **Phase 2, the walking skeleton (the whole agent loop, minimal)** —
has not been started. Everything from Phase 4 onward (real GitHub integration,
LangGraph agent, RAG, SWE-bench evaluation, MCP/observability, deploy) is not
started.

## Progress against PLAN.md phases

| Phase | Title | Status | Notes |
|---|---|---|---|
| 1 | Finish backend foundation | ✅ Done | CRUD API, Ruff green, migrations, Docker Compose |
| 2 | **Walking skeleton (agent loop)** | ✅ Done | Groq + Docker sandbox + real PR; 64 tests |
| 3 | Frontend + light auth | 🟡 Partial | CRUD UI + JWT auth done; agent run/diff/approve UI pending |
| 4 | Real GitHub integration | ⬜ Not started | Repo/issue/PR via fine-grained PAT |
| 5 | LangGraph agent | ⬜ Not started | Durable multi-step graph + HITL |
| 6 | Repository RAG | ⬜ Not started | pgvector |
| 7 | Evaluation on SWE-bench Lite | ⬜ Not started | The resume number |
| 8 | One MCP server + Langfuse | ⬜ Not started | + prompt-injection refusal test |
| 9 | Deploy + portfolio polish | 🟡 Seed | CI workflow written (unpushed); deploy + demo README pending |

## Backend detail (Phase 1)
- API: `GET /health`; `/api/v1/auth/{register,login,me}`; `/api/v1/projects` CRUD; `/api/v1/audit/me`.
- Auth is basic JWT (HS256). Projects are owner-scoped; auth is rate-limited; security-relevant actions are audited. (Ownership/rate-limit/audit exceed the plan's minimal auth but are kept — see [../memory.md](../memory.md).)
- Tests: 44 passing against a dedicated `devpilot_test` DB. Ruff lint + format clean. Migration chain verified drift-free on a fresh DB.

## Frontend detail (Phase 3, partial)
- `apps/web`: Next.js 14 (App Router) + TS + Tailwind. Auth pages, project list/create, detail/edit/delete. Typed API client, loading/error/empty states. `npm run build` + Vitest green.

## Immediate next steps
1. Begin **Phase 2 — walking skeleton** (see PLAN.md): pick a small public Python repo with a known failing test; build the clone → LLM patch → sandbox test → diff → approve → PR loop in its crudest form.
2. Line up an LLM API key and Docker (both on the developer's machine).
3. Push the pending CI commit once the GitHub token has `workflow` scope.

## Limitations
The agent, sandbox, GitHub integration, RAG, evaluation, and deployment are not
built yet. The current app is a solid foundation, not the finished product.
