# DevPilot — Working Memory

**Last updated:** 2026-10-01
**Roadmap authority:** [docs/PLAN.md](docs/PLAN.md) (9 phases). Ignore old phase numbers.

**Current position:** Phases 1 ✅, 2 ✅ (walking skeleton, real PR), 3 ✅ (frontend),
4 ✅ (real GitHub integration — proven live: issue #2 → PR #3).
**Next: Phase 5 — LangGraph agent.** SSE live run-streaming still deferred.

> Update this at the end of every session. Fuller tracking: [docs/PROGRESS.md](docs/PROGRESS.md).

---

## ✅ Phase 1 — Backend foundation (done)
- FastAPI + PostgreSQL + Alembic; Project CRUD (`apps/api/app/...`), `/health`
- Dedicated `devpilot_test` DB, pytest fixtures, **44 tests passing**; Ruff lint + format clean
- Docker Compose (Postgres + `migrate` + `api`), Dockerfile, Makefile
- Migrations chain verified drift-free on a fresh DB (current head: `deb3d64694ad`, Phase 4)
- CORS middleware (so the web app can call the API)

## ✅ Phase 3 — Frontend + light auth (done)
- `apps/web`: Next.js 14 + TS + Tailwind; auth pages + project list/create/detail; typed API client; loading/error/empty states. `npm run build`, lint, and 4 Vitest tests pass.
- Basic JWT auth (register/login/me) + `get_current_user`.
- **Agent UI:** `/tasks` (list + create) and `/tasks/[id]` — Run the agent, see status badge + event timeline + proposed diff + sandbox result, and Approve→PR / Reject. Nav has Tasks/Projects; post-login → `/tasks`.
- Deferred: SSE live run streaming (runs are synchronous); per-task run history list.

## ✅ Phase 4 — Real GitHub integration (done, proven live)
- `app/integrations/github_api.py` (REST via httpx; token = `GITHUB_TOKEN` or fallback `gh auth token`; git gets it via `GIT_CONFIG_*` env, never URL/args).
- `app/services/github.py`, `app/api/github.py`: `GET /github/repos`, `/github/repos/{o}/{n}/issues`, `/tree?ref=`; `POST /tasks/from-issue` (pins base branch → SHA, verifies target file at SHA, rejects closed issues/PRs).
- PRs now via REST (`github_pr.py`), against the task's base branch, body `Fixes #N`. Approval stores `diff_sha256` + `base_commit`; runs store `base_commit`. Migration `deb3d64694ad` (head).
- Hardening: safe `target_path` (no `..`/abs/.git, symlink-escape check at write), safe branch names, `git clone --`, issue text given to LLM as delimited untrusted context. Audit: `task.imported_from_issue`, `run.approved/rejected`.
- UI: `components/ImportFromIssue.tsx` on `/tasks`; manual form behind a `<details>`.
- Verified: 91 backend tests, ruff clean; web lint + tsc + 7 Vitest + build green; live read-only calls against GitHub OK (38 repos, tree@SHA, 404 mapping, PR-not-issue refusal).
- **Proof (2026-10-01):** planted `percent()` bug (`//` vs `/`) on `krish1809/devpilot-demo` @ `5eec58f`, opened issue #2 → `POST /tasks/from-issue` (task pinned to that SHA) → run 3 validated in sandbox (Groq one-line fix) → approve → https://github.com/krish1809/devpilot-demo/pull/3 ("Fixes #2", approval row stores diff sha256 `285019f4a722` + base commit). PR #3 left open for the user to merge.
- Dev DB has a smoke user `smoke-phase4@example.com` (owns task 3 / run 3) from the live check.

## 🟡 Phase 9 — Deploy + polish (seed only)
- GitHub Actions CI (`.github/workflows/ci.yml`) — backend ruff+migrations+pytest and frontend lint+vitest+build. CI workflow (`2d14c97`) is on origin. Deploy (Vercel/Render/Neon) + demo README not done.

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
- GitHub push for PRs now uses the API's token via env (Phase 4). An older PAT was exposed in chat once and stored via `credential.helper store` — user should revoke it and clear `~/.git-credentials`.

## Verify-before-trust checklist for agents
Before acting: read `docs/PLAN.md`, run `git status`, `alembic current`, check this file's date. If a referenced file/flag isn't present, re-inspect — docs may lag.
