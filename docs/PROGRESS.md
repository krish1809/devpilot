# DevPilot — Progress Report

**As of:** 2026-09-30
**Roadmap authority:** [PLAN.md](PLAN.md) (9 phases). This file tracks progress against those phases; it does not define them.

## Summary
Phases 1–6 are done. Tasks come straight from GitHub issues; the agent is a
durable LangGraph state graph (retrieve → plan → code → test with a bounded
repair loop → review → human approval → PR) that runs in the background,
checkpoints every step to Postgres, can be cancelled or resumed, and is capped
on attempts, LLM calls, tokens, and time. Repository RAG (pgvector + full-text,
local embeddings) lets the agent find the file to fix from the issue alone.
Next is **Phase 7 — evaluation on SWE-bench Lite**. Phases 7–8 are not started;
Phase 9 has a CI seed only.

## Progress against PLAN.md phases

| Phase | Title | Status | Notes |
|---|---|---|---|
| 1 | Finish backend foundation | ✅ Done | CRUD API, Ruff green, migrations, Docker Compose |
| 2 | **Walking skeleton (agent loop)** | ✅ Done | Groq + Docker sandbox + real PR; 64 tests |
| 3 | Frontend + light auth | ✅ Done | Auth + projects + agent UI (create task, run, view diff/events, approve→PR). SSE live-streaming deferred (runs are synchronous) |
| 4 | Real GitHub integration | ✅ Done | List repos/issues/tree, import issue → task pinned to (repo, branch, SHA), PR via REST with `Fixes #N`; 91 backend tests. Proven live: devpilot-demo issue #2 → PR #3 |
| 5 | LangGraph agent | ✅ Done | Graph + Postgres checkpoints + interrupt-based approval, background runs, cancel/resume, budgets; 103 backend tests; proven live incl. resume across a server restart |
| 6 | Repository RAG | ✅ Done | pgvector + FTS hybrid retrieval, file localization; smoke eval: root-cause localization 5/5 with RAG vs 2/5 without ([eval/phase6-rag.md](eval/phase6-rag.md)) |
| 7 | Evaluation on SWE-bench Lite | 🟡 In progress | Harness + official scoring + results UI built; 20-instance seeded run in progress ([eval/README.md](eval/README.md)) |
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

## Repository RAG detail (Phase 6)
- Postgres now runs `devpilot-postgres:17-pgvector` (`infra/postgres/Dockerfile`: `FROM postgres:17` + `postgresql-17-pgvector`, same Debian/glibc as before so the existing volume's collations are unchanged; the official pgvector image is bookworm and is only used in CI). Dev DB backed up before the swap; data verified intact.
- `apps/api/app/rag/`: `chunking.py` (tracked files only; Python split at top-level defs, others in overlapping 60-line windows; exclusions + secret redaction), `embeddings.py` (provider-neutral `Embedder`; default fastembed `BAAI/bge-small-en-v1.5`, local ONNX, 384-d), `index.py` (atomic build-or-reuse per (repo, commit, model); hybrid retrieval = exact cosine over the index + Postgres FTS on identifiers, fused with RRF; traceback-named files boosted; files ranked by best chunk).
- Tables `repo_indexes`, `repo_chunks` (vector(384) + generated tsvector, GIN) — migration `cb5554ccaecd`, which also makes `tasks.target_path` nullable and adds `agent_runs.use_rag/target_path/retrieval`.
- Graph: new `retrieve` node (prepare → retrieve → plan). Retrieved chunks go to planner + coder as delimited untrusted context (minus the file sent whole). With no `target_path`, `plan` localizes (`TARGET:`/`PLAN:` format) and the server validates the choice (safe, tracked, indexable) or falls back to the top candidate. RAG is per-run (`use_rag`); with RAG off and no target, the planner gets the file list (baseline).
- LLM client now retries 429s, waiting as the provider asks (Retry-After / "try again in Xs"), capped at 30s × 6 — Groq's free tier is 8k tokens/min.
- Evaluation: `python -m scripts.rag_eval --owner <email>` → [docs/eval/phase6-rag.md](eval/phase6-rag.md). Both configs resolved 5/5; RAG fixed the root-cause file 5/5 vs 2/5 (no-RAG patched callers — workarounds), ~20% fewer tokens.
- Tests: 137 backend (chunking/exclusions/redaction, pgvector index + hybrid retrieval on the real test DB, localization + fallback, context exclusion, RAG on/off, 429 retry). Web: lint + tsc + 10 Vitest + build.

## Immediate next steps
1. Begin **Phase 7 — SWE-bench Lite** (see PLAN.md): a harness that runs the agent on SWE-bench Lite instances (repo + base commit + issue + FAIL_TO_PASS tests) and reports resolve rate, cost, latency; compare baseline vs RAG. Expect to need per-repo sandbox images (dependencies) and to respect Groq's rate limit.

## Limitations
Single-file agent (the task may name the file, or the agent localizes one); runs execute in the API process
(no separate worker) and progress is polled, not streamed; no RAG, evaluation,
or deployment yet.
