# DevPilot — Progress Report

**As of:** 2026-10-22
**Roadmap authority:** [PLAN.md](PLAN.md) (9 phases). This file tracks progress against those phases; it does not define them.

## Summary
All nine phases have been built, and the app is live at
[devpilot-pied.vercel.app](https://devpilot-pied.vercel.app) (read-only showcase).
Tasks come from GitHub issues; the agent is a durable LangGraph graph (retrieve →
plan → code → test with a bounded repair loop → review → human approval → PR) that
runs in the background, checkpoints every step to Postgres, streams its progress to
the browser over SSE, and is capped on attempts, LLM calls, tokens and time.

**The one open item is the Phase 7 headline number.** The SWE-bench Lite harness
works, but the 20-instance v2 benchmark stopped after 1 instance (the unattended
loop died around 2026-10-02 and the machine rebooted on 2026-10-18). Restarting it
is blocked: the disk is 99% full (≈1.8 GB free) and scoring needs ≈8 GB free (each
instance image is ≈3.8 GB). Once the owner frees space, restart it (command in
"Immediate next steps"), then refresh the README numbers and the showcase data.

## Progress against PLAN.md phases

| Phase | Title | Status | Notes |
|---|---|---|---|
| 1 | Finish backend foundation | ✅ Done | CRUD API, Ruff green, migrations, Docker Compose |
| 2 | **Walking skeleton (agent loop)** | ✅ Done | Groq + Docker sandbox + real PR; 64 tests |
| 3 | Frontend + light auth | ✅ Done | Auth + projects + agent UI (create task, run, view diff/events, approve→PR). Live run progress over SSE (added 2026-10-22; polling fallback) |
| 4 | Real GitHub integration | ✅ Done | List repos/issues/tree, import issue → task pinned to (repo, branch, SHA), PR via REST with `Fixes #N`; 91 backend tests. Proven live: devpilot-demo issue #2 → PR #3 |
| 5 | LangGraph agent | ✅ Done | Graph + Postgres checkpoints + interrupt-based approval, background runs, cancel/resume, budgets; 103 backend tests; proven live incl. resume across a server restart |
| 6 | Repository RAG | ✅ Done | pgvector + FTS hybrid retrieval, file localization; smoke eval: root-cause localization 5/5 with RAG vs 2/5 without ([eval/phase6-rag.md](eval/phase6-rag.md)) |
| 7 | Evaluation on SWE-bench Lite | 🟡 Harness done, headline run incomplete | Harness + official scoring + results UI built. v1 ablation (6 instances, pre-syntax-gate): RAG 2/6, oracle-file 3/6. **v2 headline (20 instances): only 1/20 run** — loop stopped ~2026-10-02; restart blocked on disk space (needs ≈8 GB free). See [eval/README.md](eval/README.md) |
| 8 | One MCP server + observability | ✅ Done | `devpilot-tools` MCP server (per-run binding, permission policy, audit log; the agent's sandbox runs go through it), LLM/tool-call tracing + UI, prompt-injection tests, risky-change warnings. Langfuse skipped (disk); built-in tracing instead |
| 9 | Deploy + portfolio polish | ✅ Live at [devpilot-pied.vercel.app](https://devpilot-pied.vercel.app) | Vercel (web) → Render free (API, DEMO_MODE) → Neon (Postgres + pgvector). Read-only showcase mode, showcase export/import, [DEPLOY.md](DEPLOY.md), product README with screenshots/GIF, CI green. Pending: refresh numbers + showcase data after the v2 benchmark |

## Backend detail (Phase 1)
- API: `GET /health`; `/api/v1/auth/{register,login,me}`; `/api/v1/projects` CRUD; `/api/v1/audit/me`.
- Auth is basic JWT (HS256). Projects are owner-scoped; auth is rate-limited; security-relevant actions are audited. (Ownership/rate-limit/audit exceed the plan's minimal auth but are kept — see [../memory.md](../memory.md).)
- Tests: 44 passing against a dedicated `devpilot_test` DB. Ruff lint + format clean. Migration chain verified drift-free on a fresh DB.

## Frontend detail (Phase 3)
- `apps/web`: Next.js 14 (App Router) + TS + Tailwind. Auth pages, project list/create + detail/edit/delete.
- **Agent UI:** `/tasks` (list + create task) and `/tasks/[id]` (Run the agent, view status badge, event timeline, proposed diff, sandbox result, and **Approve → open PR / Reject**). Post-login lands on `/tasks`.
- Typed API client (`lib/api.ts`) covers auth, projects, and agent endpoints. `npm run build`, `npm run lint`, and Vitest all green.
- Live progress: since Phase 5 runs are background jobs; since 2026-10-22 the page streams them over SSE (see "Live run streaming" below). Run history landed in Phase 5.

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
- UI (`app/tasks/[id]/page.tsx`): live updates (SSE since 2026-10-22, polling fallback), run history, plan, usage line, Cancel / Resume, sandbox output, graph checkpoints.
- Live check (2026-10-01): real Groq + Docker + PostgresSaver — run paused at approval after ~12s (1 attempt, 2 LLM calls, ~1.2k tokens); server killed and restarted; the new process resumed the paused graph from Postgres and completed it.

## Repository RAG detail (Phase 6)
- Postgres now runs `devpilot-postgres:17-pgvector` (`infra/postgres/Dockerfile`: `FROM postgres:17` + `postgresql-17-pgvector`, same Debian/glibc as before so the existing volume's collations are unchanged; the official pgvector image is bookworm and is only used in CI). Dev DB backed up before the swap; data verified intact.
- `apps/api/app/rag/`: `chunking.py` (tracked files only; Python split at top-level defs, others in overlapping 60-line windows; exclusions + secret redaction), `embeddings.py` (provider-neutral `Embedder`; default fastembed `BAAI/bge-small-en-v1.5`, local ONNX, 384-d), `index.py` (atomic build-or-reuse per (repo, commit, model); hybrid retrieval = exact cosine over the index + Postgres FTS on identifiers, fused with RRF; traceback-named files boosted; files ranked by best chunk).
- Tables `repo_indexes`, `repo_chunks` (vector(384) + generated tsvector, GIN) — migration `cb5554ccaecd`, which also makes `tasks.target_path` nullable and adds `agent_runs.use_rag/target_path/retrieval`.
- Graph: new `retrieve` node (prepare → retrieve → plan). Retrieved chunks go to planner + coder as delimited untrusted context (minus the file sent whole). With no `target_path`, `plan` localizes (`TARGET:`/`PLAN:` format) and the server validates the choice (safe, tracked, indexable) or falls back to the top candidate. RAG is per-run (`use_rag`); with RAG off and no target, the planner gets the file list (baseline).
- LLM client now retries 429s, waiting as the provider asks (Retry-After / "try again in Xs"), capped at 30s × 6 — Groq's free tier is 8k tokens/min.
- Evaluation: `python -m scripts.rag_eval --owner <email>` → [docs/eval/phase6-rag.md](eval/phase6-rag.md). Both configs resolved 5/5; RAG fixed the root-cause file 5/5 vs 2/5 (no-RAG patched callers — workarounds), ~20% fewer tokens.
- Tests: 137 backend (chunking/exclusions/redaction, pgvector index + hybrid retrieval on the real test DB, localization + fallback, context exclusion, RAG on/off, 429 retry). Web: lint + tsc + 10 Vitest + build.

## Phases 7–9 detail (summary — full notes in [../memory.md](../memory.md))
- **Phase 7:** `app/evals/swebench.py` + CLI `python -m scripts.swebench_eval {generate,score,report,run-all}`; scoring with the official `swebench` harness from `apps/api/.venv-swebench`; results in `eval_runs`/`eval_results`, API `/api/v1/evals`, web `/evals`; reports rewritten into `docs/eval/phase7-*.md` after every pass.
- **Phase 8:** `app/mcp/server.py` (`devpilot-tools` MCP server, per-run binding, permission policy, audit), LLM/tool-call tracing (`llm_calls`, `tool_calls`, `GET /runs/{id}/trace`, web trace panel), prompt-injection tests, risky-change warnings, syntax gate. Built-in tracing instead of Langfuse (self-hosting it didn't fit the disk).
- **Phase 9:** showcase mode (`app/core/demo.py`), `scripts/showcase.py export|import`, `render.yaml`, Dockerfile runs migrations then uvicorn, [DEPLOY.md](DEPLOY.md).

## Live run streaming (added 2026-10-22, closes the Phase 3 SSE item)
- `GET /api/v1/runs/{id}/stream` (`app/api/agent.py` → `app/services/run_stream.py`): Server-Sent Events. Re-reads the run every 1 s and pushes a full `run` snapshot (same shape as `GET /runs/{id}`) only when it changed; `done` when the run leaves `running`; `timeout` after the run's wall-clock limit + 60 s; keep-alive comments every 15 s. Owner-scoped like the other run endpoints.
- Web: `lib/sse.ts` (incremental parser) + `api.streamRun` in `lib/api.ts` use `fetch` streaming so the bearer token stays in a header (`EventSource` can't send one and a URL token would land in access logs). `app/tasks/[id]/page.tsx` streams while a run is `running` and falls back to 1.5 s polling if the stream fails or times out.
- Tests: backend `tests/test_run_stream.py` (8: change-only snapshots, heartbeat/timeout, disconnect, deleted run, auth, ownership, HTTP stream of a finished run) — backend suite **209 passed** (incl. the disk-guard tests below); web `lib/sse.test.ts` + 3 `streamRun` tests — **29 passed**; lint, `tsc`, `next build` green.
- Live check (2026-10-22, local API + real Groq + Docker sandbox): run 86 (devpilot-demo @ `5eec58f`) streamed prepare → retrieve → plan → code → test → review → `validated` → `done` over ~16 s. That run is left `validated` (unapproved) in the local dev DB — nothing was published.

## Eval disk guard (added 2026-10-22)
- The unattended benchmark used to start scoring regardless of free space; each instance image is ≈3.8 GB, so on
  today's 99%-full disk it would have filled the filesystem (and taken Postgres down with it).
- `app/evals/swebench.py`: `free_disk_gb()` measures the tighter of the eval cache's and Docker's data-root
  filesystems; `require_free_disk()` raises `LowDisk` before each instance (generation ≥ 2 GB, scoring ≥ 6 GB).
  The CLI prints the reason and stops cleanly; finished work is kept and resumes on the next run.
- `run-all` now finishes only when generation **and** scoring are both complete (previously a scoring pass cut
  short could still end the loop with unscored results). It sleeps and retries otherwise.
- Tests: 5 new in `tests/test_evals.py` (scoring/generation stop before any image or clone, patch-less results
  still score, tightest-filesystem measurement, run-all completion). Verified on this machine: both steps are
  currently refused (1.8 GB free).

## Immediate next steps
1. **Free disk space** (owner): ≈8 GB free is needed before the benchmark can score instances. Largest candidates seen 2026-10-22: `~/.cache/uv` (6.6 GB; `uv cache prune`), `~/.cache/huggingface` (4.2 GB), `~/Downloads` (3.7 GB), `~/.cache/google-chrome` (1.2 GB), Docker build cache/dangling images (`docker builder prune`, `docker image prune`).
2. **Restart the v2 benchmark** (resumes where it left off), from `apps/api` with `.venv` active:
   `nohup python -m scripts.swebench_eval run-all --name lite-s20-seed7 --n 20 --seed 7 --owner smoke-phase4@example.com --with-gold >> ~/.cache/devpilot/swebench/run-all.log 2>&1 &`
   Groq's free tier allows ≈200k tokens/day → ≈3 days for the remaining 19 instances. Stop it only by exact PID (see memory.md).
3. When it finishes: re-export `deploy/showcase.json`, re-import into Neon (owner enters the URL via `read -rs`), refresh the README numbers and `docs/images/benchmarks.png`.

## Limitations
Single-file agent (the task may name the file, or the agent localizes one). Runs execute
in the API process's background threads (no separate worker). The hosted site is a
read-only showcase: running the agent needs Docker and an LLM key, so it runs locally.
