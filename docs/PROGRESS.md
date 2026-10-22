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

**The Phase 7 headline number is being produced unattended** (since 2026-10-22, 06:16 IST).
A systemd user service on the owner's laptop generates the remaining SWE-bench patches
(paced by Groq's 200k tokens/day — about 3 days), then scores every patch in **GitHub
Actions** (the laptop has no room for the per-instance Docker images), then publishes the
report, the README numbers, the showcase data (which the deployed API loads on its own) and a
fresh screenshot — with no one at the keyboard. CI scoring was validated first: it reproduced
the local verdicts exactly. See "SWE-bench pipeline" below.

## Progress against PLAN.md phases

| Phase | Title | Status | Notes |
|---|---|---|---|
| 1 | Finish backend foundation | ✅ Done | CRUD API, Ruff green, migrations, Docker Compose |
| 2 | **Walking skeleton (agent loop)** | ✅ Done | Groq + Docker sandbox + real PR; 64 tests |
| 3 | Frontend + light auth | ✅ Done | Auth + projects + agent UI (create task, run, view diff/events, approve→PR). Live run progress over SSE (added 2026-10-22; polling fallback) |
| 4 | Real GitHub integration | ✅ Done | List repos/issues/tree, import issue → task pinned to (repo, branch, SHA), PR via REST with `Fixes #N`; 91 backend tests. Proven live: devpilot-demo issue #2 → PR #3 |
| 5 | LangGraph agent | ✅ Done | Graph + Postgres checkpoints + interrupt-based approval, background runs, cancel/resume, budgets; 103 backend tests; proven live incl. resume across a server restart |
| 6 | Repository RAG | ✅ Done | pgvector + FTS hybrid retrieval, file localization; smoke eval: root-cause localization 5/5 with RAG vs 2/5 without ([eval/phase6-rag.md](eval/phase6-rag.md)) |
| 7 | Evaluation on SWE-bench Lite | 🟡 Running unattended | Harness + official scoring + results UI. v1 ablation (6 instances, pre-syntax-gate): RAG 2/6, oracle-file 3/6. **v2 headline (20 instances)** resumed 2026-10-22 as an unattended pipeline: local generation → scoring in GitHub Actions (validated: identical verdicts to local scoring) → auto-publish. 2/20 instances generated at launch; ETA ≈3 days. See [eval/README.md](eval/README.md) |
| 8 | One MCP server + observability | ✅ Done | `devpilot-tools` MCP server (per-run binding, permission policy, audit log; the agent's sandbox runs go through it), LLM/tool-call tracing + UI, prompt-injection tests, risky-change warnings. Langfuse skipped (disk); built-in tracing instead |
| 9 | Deploy + portfolio polish | ✅ Live at [devpilot-pied.vercel.app](https://devpilot-pied.vercel.app) | Vercel (web) → Render free (API, DEMO_MODE) → Neon (Postgres + pgvector). Read-only showcase that **loads its own data on deploy** (autoload, since 2026-10-22), [DEPLOY.md](DEPLOY.md), product README with screenshots/GIF, CI green. The pipeline refreshes numbers, showcase data and the benchmarks screenshot when the v2 run completes |

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
- Local scoring used to start regardless of free space. `app/evals/swebench.py` now checks the
  tighter of the eval cache's and Docker's filesystems before each instance: generation needs
  2 GB; scoring needs `max(6 GB, 4 × compressed image size + 1 GB)`, the size looked up on Docker
  Hub (Docker's containerd store keeps compressed and unpacked layers; Matplotlib's image is
  3.07 GB compressed). Below that it raises `LowDisk`; `run-all`/`pipeline` sleep and retry and
  finish only when generation **and** scoring are complete.

## SWE-bench pipeline (added 2026-10-22)
- **Why:** the laptop's disk (≈3.5 GB free after a safe cache cleanup) can't hold SWE-bench
  images (≈1–3 GB compressed, ~3× unpacked), and the previous unattended loop died with its
  session on 2026-10-02.
- **Scoring in CI:** `.github/workflows/swebench-score.yml` + `apps/api/scripts/ci_score.py`
  (one job per instance; frees ~25 GB; `swebench==5.0.2`; retries harness errors) → merged
  `swebench-scores` artifact. `app/evals/harness_io.py` (stdlib only) is shared with local
  scoring so both run the identical command and parse verdicts the same way. Predictions
  (every patch) are committed to `docs/eval/predictions/<name>.jsonl`.
- **Validated 2026-10-22:** `ci-score --force` on django-11620's three patches
  ([run](https://github.com/krish1809/devpilot/actions/runs/39701119345), 4 min) gave exactly the
  local verdicts — gold ✅ (FAIL_TO_PASS 1/1, PASS_TO_PASS 66/66), rag ❌, oracle-file ❌.
- **Pipeline:** `python -m scripts.swebench_eval pipeline …` (`apps/api/scripts/eval_pipeline.py`):
  generate until done (publishing the partial report and the README's progress line after each
  productive pass) → CI scoring until every result has a verdict → one commit with the final
  report, README numbers and showcase file → Render redeploys and the API loads it → re-capture
  `docs/images/benchmarks.png` from the live site (`apps/web/scripts/capture-benchmarks.mjs`,
  best effort). Publishes from a dedicated clone (`~/.cache/devpilot/swebench/publish-repo`),
  never the owner's checkout; its commits end in `[automated]`.
- **Running as** the systemd user service `devpilot-benchmark` (installed with
  `infra/systemd/install.sh`): survives the terminal, restarts on failure, resumes at login after
  a reboot, and disables itself when done (marker `~/.cache/devpilot/swebench/pipeline-lite-s20-seed7.done`).
  Log: `~/.cache/devpilot/swebench/pipeline.log`.
- **Showcase autoload:** the curated export moved to `apps/api/showcase/showcase.json` and ships in
  the API image; on start (DEMO_MODE only) the container imports it if its SHA-256 changed
  (`app_state` table, migration `cd35ce4e3392`); never blocks startup. Deployed 2026-10-22: Neon
  re-imported itself (demo task ids are now 4–6).
- Tests: backend 241 passed (ci_score 6, pipeline 18 incl. real git against a bare repo with a
  push race, evals +8, showcase +4); web 29; lint/tsc/build green; CI green.

## Immediate next steps
Nothing needs a human for the benchmark. To watch it:
`tail -f ~/.cache/devpilot/swebench/pipeline.log`, `systemctl --user status devpilot-benchmark`,
and the `[automated]` commits on GitHub. To stop it: `systemctl --user disable --now devpilot-benchmark`.

1. (owner) Confirm the Neon `neondb_owner` password was reset after it was pasted in chat on
   2026-10-02 — it needs the Neon and Render dashboards (reset in Neon, paste the new URL into
   Render's `DATABASE_URL`); an agent has no access to either.
2. When the pipeline finishes (≈3 days): check the final commit, the README numbers and the live
   Benchmarks page; then update this file and memory.md with the headline result.

## Limitations
Single-file agent (the task may name the file, or the agent localizes one). Runs execute
in the API process's background threads (no separate worker). The hosted site is a
read-only showcase: running the agent needs Docker and an LLM key, so it runs locally.
