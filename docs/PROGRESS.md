# DevPilot — Progress Report

**As of:** 2026-09-30
**Roadmap authority:** [PLAN.md](PLAN.md) (9 phases). This file tracks progress against those phases; it does not define them.

## Summary
Phases 1–5 are done. Tasks come straight from GitHub issues; the agent is a
durable LangGraph state graph (plan → code → test with a bounded repair loop →
review → human approval → PR) that runs in the background, checkpoints every
step to Postgres, can be cancelled or resumed, and is capped on attempts, LLM
calls, tokens, and time. Next is **Phase 6 — repository RAG**. Phases 6–8 are
not started; Phase 9 has a CI seed only.

## Progress against PLAN.md phases

| Phase | Title | Status | Notes |
|---|---|---|---|
| 1 | Finish backend foundation | ✅ Done | CRUD API, Ruff green, migrations, Docker Compose |
| 2 | **Walking skeleton (agent loop)** | ✅ Done | Groq + Docker sandbox + real PR; 64 tests |
| 3 | Frontend + light auth | ✅ Done | Auth + projects + agent UI (create task, run, view diff/events, approve→PR). SSE live-streaming deferred (runs are synchronous) |
| 4 | Real GitHub integration | ✅ Done | List repos/issues/tree, import issue → task pinned to (repo, branch, SHA), PR via REST with `Fixes #N`; 91 backend tests. Proven live: devpilot-demo issue #2 → PR #3 |
| 5 | LangGraph agent | ✅ Done | Graph + Postgres checkpoints + interrupt-based approval, background runs, cancel/resume, budgets; 103 backend tests; proven live incl. resume across a server restart |
| 6 | Repository RAG | ⬜ Not started | pgvector |
| 7 | Evaluation on SWE-bench Lite | ⬜ Not started | The resume number |
| 8 | One MCP server + Langfuse | ⬜ Not started | + prompt-injection refusal test |
| 9 | Deploy + portfolio polish | 🟡 Seed | CI workflow on origin; deploy + demo README pending |

## Backend detail (Phase 1)
- API: `GET /health`; `/api/v1/auth/{register,login,me}`; `/api/v1/projects` CRUD; `/api/v1/audit/me`.
- Auth is basic JWT (HS256). Projects are owner-scoped; auth is rate-limited; security-relevant actions are audited. (Ownership/rate-limit/audit exceed the plan's minimal auth but are kept — see [../memory.md](../memory.md).)
- Tests: 44 passing against a dedicated `devpilot_test` DB. Ruff lint + format clean. Migration chain verified drift-free on a fresh DB.

## Frontend detail (Phase 3)
- `apps/web`: Next.js 14 (App Router) + TS + Tailwind. Auth pages, project list/create + detail/edit/delete.
- **Agent UI:** `/tasks` (list + create task) and `/tasks/[id]` (Run the agent, view status badge, event timeline, proposed diff, sandbox result, and **Approve → open PR / Reject**). Post-login lands on `/tasks`.
- Typed API client (`lib/api.ts`) covers auth, projects, and agent endpoints. `npm run build`, `npm run lint`, and Vitest all green.
- Deferred: live run streaming via SSE (needs async runs); a per-task run history list.

## GitHub integration detail (Phase 4)
- `apps/api/app/integrations/github_api.py` — httpx REST client: repos, issues, resolve ref→SHA, tree, read file at SHA, create PR. Token from `GITHUB_TOKEN` (fallback `gh auth token`); `git_auth_env()` gives git the token via `GIT_CONFIG_*` env (never in URLs/args/logs).
- `apps/api/app/integrations/github_pr.py` — clone at the run's commit, apply the approved diff, push with env auth, open PR via REST (no more `gh pr create`).
- `apps/api/app/services/github.py` + `app/api/github.py` — `GET /github/repos`, `/github/repos/{o}/{n}/issues`, `/tree`; `POST /tasks/from-issue`.
- Binding (migration `deb3d64694ad`): tasks get `repo_full_name`, `base_branch`, `issue_number/title/url`; runs record the `base_commit` they ran on; approvals record `diff_sha256` + `base_commit`. PR targets the task's base branch and says `Fixes #N`.
- Safety: `target_path` must stay inside the checkout (also enforced at write time, incl. symlinks); branch names validated; `git clone --`; issue text is passed to the LLM as delimited untrusted context.
- Frontend: `components/ImportFromIssue.tsx` on `/tasks` (repo → issue → file picker from the tree at the pinned SHA → test command); manual form kept as a fallback; task detail shows repo, issue link, branch @ SHA.
- Tests: `apps/api/tests/test_github.py` (27, GitHub mocked with `httpx.MockTransport`); Vitest covers new client calls.

## LangGraph agent detail (Phase 5)
- `apps/api/app/agents/graph.py` — `StateGraph`: `prepare` (clone at pinned SHA, baseline test) → `plan` (LLM, numbered plan) → `code` (LLM, whole file) → `test` (sandbox) → repair loop back to `code` (≤ `agent_max_attempts`, failure output fed back) or `fail` → `review` (deterministic: non-empty, only the target file, ≤300 changed lines, no conflict markers) → `human_approval` (`interrupt()`) → `publish`. Every LLM call goes through a budget check (calls + tokens); every working node checks cancellation + wall-clock deadline.
- `apps/api/app/agents/checkpoint.py` — `PostgresSaver` on a psycopg pool, thread id `run-<id>`. Its tables are created by `alembic upgrade head` (env.py hook) — **never lazily in a request** (its `CREATE INDEX CONCURRENTLY` deadlocks against the request's open transaction; found and fixed during this phase). Alembic autogenerate ignores those tables.
- `apps/api/app/agents/runner.py` — `start_run`, `execute_run` (background; never raises, records every outcome), `cancel_run`, `prepare_resume`, `approve_run` (records Approval with diff hash, resumes with `Command(resume=…)`; `publish` refuses a stale hash), `checkpoint_history`. `AgentDeps` injects DB/LLM/sandbox/publisher/checkpointer (tests use fakes + InMemorySaver; one test uses a real PostgresSaver across a simulated restart).
- Endpoints: `POST /tasks/{id}/run` → 202; `GET /tasks/{id}/runs`; `GET /runs/{id}/checkpoints`; `POST /runs/{id}/cancel|resume`. Migration `b88d25944321` adds `plan`, `attempts`, `llm_calls`, `prompt/completion_tokens`, `cancel_requested`.
- Sandbox now runs as the host uid with `PYTHONDONTWRITEBYTECODE=1`.
- UI (`app/tasks/[id]/page.tsx`): live polling, run history, plan, usage line, Cancel / Resume, sandbox output, graph checkpoints.
- Live check (2026-10-01): real Groq + Docker + PostgresSaver — run paused at approval after ~12s (1 attempt, 2 LLM calls, ~1.2k tokens); server killed and restarted; the new process resumed the paused graph from Postgres and completed it.

## Immediate next steps
1. Begin **Phase 6 — repository RAG** (see PLAN.md): pgvector, chunk + embed repo at the pinned commit, retrieve for planner/coder; lets the agent pick the file instead of requiring `target_path`.

## Limitations
Single-file agent (the task names the file); runs execute in the API process
(no separate worker) and progress is polled, not streamed; no RAG, evaluation,
or deployment yet.
