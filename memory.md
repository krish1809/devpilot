# DevPilot — Working Memory

**Last updated:** 2026-09-30
**Roadmap authority:** [docs/PLAN.md](docs/PLAN.md) (9 phases). Ignore old phase numbers.

**Current position:** Phase 1 ✅ and Phase 2 ✅ (walking skeleton) complete and proven
end-to-end with a real Groq patch + real PR. Phase 3 🟡 partial (CRUD UI + JWT auth;
agent/run/diff/approve UI still to add). **Next: Phase 3 UI for the agent loop, or Phase 4 (GitHub integration).**

> Update this at the end of every session. Fuller tracking: [docs/PROGRESS.md](docs/PROGRESS.md).

---

## ✅ Phase 1 — Backend foundation (done)
- FastAPI + PostgreSQL + Alembic; Project CRUD (`apps/api/app/...`), `/health`
- Dedicated `devpilot_test` DB, pytest fixtures, **44 tests passing**; Ruff lint + format clean
- Docker Compose (Postgres + `migrate` + `api`), Dockerfile, Makefile
- Migrations at head `c1a2b3d4e5f6`; chain verified drift-free on a fresh DB
- CORS middleware (so the web app can call the API)

## 🟡 Phase 3 — Frontend + light auth (partially done, out of order)
- `apps/web`: Next.js 14 + TS + Tailwind; auth pages + project list/create/detail; typed API client; loading/error/empty states. `npm run build` + 4 Vitest tests pass.
- Basic JWT auth (register/login/me) + `get_current_user`.
- **Still needed for Phase 3 proper:** live run status (SSE), diff view, approve/reject — these depend on the Phase 2 agent existing first.

## 🟡 Phase 9 — Deploy + polish (seed only)
- GitHub Actions CI (`.github/workflows/ci.yml`) — backend ruff+migrations+pytest and frontend lint+vitest+build. **Commit `2d14c97` is local/unpushed** (token lacks `workflow` scope). Deploy (Vercel/Render/Neon) + demo README not done.

## Built beyond the plan's minimal scope (kept, harmless)
- Per-owner project scoping (`owner_id`), auth rate limiting, audit log (`audit_logs`, `/audit/me`). Plan keeps auth minimal and puts audit in Phase 8; these are ahead of schedule and reusable. Kept to avoid churn.

## ✅ Phase 2 — Walking skeleton (DONE, proven end-to-end)
The whole loop works: clone at commit → run failing test in sandbox → one Groq
call for a fixed file → apply → re-run test in sandbox → diff + pass/fail → human
approve → open real PR.
- LLM: `app/integrations/llm.py` (Groq, `openai/gpt-oss-120b`, bounded retries)
- Sandbox: `app/sandbox/runner.py` (throwaway container, `--network none`, limits)
- Git/PR: `app/integrations/git_ops.py`, `app/integrations/github_pr.py` (gh CLI)
- Orchestration: `app/services/agent.py`; endpoints in `app/api/agent.py`:
  POST/GET `/api/v1/tasks`, POST `/tasks/{id}/run`, GET `/runs/{id}`, POST `/runs/{id}/approve`
- Data: Task, AgentRun, RunEvent, Approval, PullRequest (migration b698e033df6b)
- **Proof:** opened https://github.com/krish1809/devpilot-demo/pull/1 from a planted
  failing unittest (fix `a - b` → `a + b`). Demo target repo: `krish1809/devpilot-demo`.
- Tests: 64 total (agent orchestration + approval mocked; sandbox docker-gated).
- Note: `/tasks/{id}/run` is synchronous for now (moves to a worker in a later phase).

## ⚠️ Constraints / gotchas
- **Sandbox network:** npm registry + github.com + PyPI reachable (npm install & git push work); Docker Hub + fonts.googleapis.com NOT (Docker image builds & web-font fetch fail here). Raw DB row deletes are approval-gated.
- Do not repeat the earlier Alembic reset — verify DB state before destructive migration ops.
- `.env` git-ignored; no real secrets committed. Set a strong `SECRET_KEY` for any real deploy.
- GitHub push uses `credential.helper store` primed with the user's PAT (exposed in chat once — user to rotate).

## Verify-before-trust checklist for agents
Before acting: read `docs/PLAN.md`, run `git status`, `alembic current`, check this file's date. If a referenced file/flag isn't present, re-inspect — docs may lag.
