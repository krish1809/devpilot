# DevPilot — Working Memory

**Last updated:** 2026-10-22
**Roadmap authority:** [docs/PLAN.md](docs/PLAN.md) (9 phases). Ignore old phase numbers.

**Current position:** All 9 phases built. Live: **https://devpilot-pied.vercel.app** (Vercel, `apps/web`) →
API **https://devpilot-api-gr7a.onrender.com** (Render free, DEMO_MODE) → Neon Postgres.
**The Phase 7 headline run is in progress, unattended:** systemd user service `devpilot-benchmark` (started
2026-10-22 06:16 IST) generates the v2 patches locally (Groq 200k tokens/day → ≈3 days), then scores them in
**GitHub Actions**, then publishes report + README numbers + showcase data + screenshot by itself. Nothing for a
human to do except confirm the Neon password reset (see Phase 9). When it's done, record the headline result here.
2026-10-22 sessions: SSE run streaming; eval disk guard (size-aware); CI scoring + unattended pipeline; showcase
autoload; safe disk cleanup (+1.99 GB). Backend **241** tests, web **29**; lint/tsc/build/CI green.

> Update this at the end of every session. Fuller tracking: [docs/PROGRESS.md](docs/PROGRESS.md).

---

## ✅ Phase 1 — Backend foundation (done)
- FastAPI + PostgreSQL + Alembic; Project CRUD (`apps/api/app/...`), `/health`
- Dedicated `devpilot_test` DB, pytest fixtures, **44 tests passing**; Ruff lint + format clean
- Docker Compose (Postgres + `migrate` + `api`), Dockerfile, Makefile
- Migrations chain verified drift-free (`alembic check` clean; current head `b04f052d3d3e`, Phase 8)
- CORS middleware (so the web app can call the API)

## ✅ Phase 3 — Frontend + light auth (done)
- `apps/web`: Next.js 14 + TS + Tailwind; auth pages + project list/create/detail; typed API client; loading/error/empty states. `npm run build`, lint, and 4 Vitest tests pass.
- Basic JWT auth (register/login/me) + `get_current_user`.
- **Agent UI:** `/tasks` (list + create) and `/tasks/[id]` — Run the agent, see status badge + event timeline + proposed diff + sandbox result, and Approve→PR / Reject. Nav has Tasks/Projects; post-login → `/tasks`.
- Live progress streams over SSE since 2026-10-22 (see "Live run streaming" below); run history landed in Phase 5.

## ✅ Phase 4 — Real GitHub integration (done, proven live)
- `app/integrations/github_api.py` (REST via httpx; token = `GITHUB_TOKEN` or fallback `gh auth token`; git gets it via `GIT_CONFIG_*` env, never URL/args).
- `app/services/github.py`, `app/api/github.py`: `GET /github/repos`, `/github/repos/{o}/{n}/issues`, `/tree?ref=`; `POST /tasks/from-issue` (pins base branch → SHA, verifies target file at SHA, rejects closed issues/PRs).
- PRs now via REST (`github_pr.py`), against the task's base branch, body `Fixes #N`. Approval stores `diff_sha256` + `base_commit`; runs store `base_commit`. Migration `deb3d64694ad` (head).
- Hardening: safe `target_path` (no `..`/abs/.git, symlink-escape check at write), safe branch names, `git clone --`, issue text given to LLM as delimited untrusted context. Audit: `task.imported_from_issue`, `run.approved/rejected`.
- UI: `components/ImportFromIssue.tsx` on `/tasks`; manual form behind a `<details>`.
- Verified: 91 backend tests, ruff clean; web lint + tsc + 7 Vitest + build green; live read-only calls against GitHub OK (38 repos, tree@SHA, 404 mapping, PR-not-issue refusal).
- **Proof (2026-10-01):** planted `percent()` bug (`//` vs `/`) on `krish1809/devpilot-demo` @ `5eec58f`, opened issue #2 → `POST /tasks/from-issue` (task pinned to that SHA) → run 3 validated in sandbox (Groq one-line fix) → approve → https://github.com/krish1809/devpilot-demo/pull/3 ("Fixes #2", approval row stores diff sha256 `285019f4a722` + base commit). PR #3 left open for the user to merge.
- Dev DB has a smoke user `smoke-phase4@example.com` (local dev DB only; password not recorded here) owning the live-check tasks/runs.

## ✅ Phase 5 — LangGraph agent (done, proven live)
- `app/agents/graph.py` (state graph + nodes + budgets/guards), `checkpoint.py` (PostgresSaver), `runner.py` (start/execute/cancel/resume/approve/checkpoint_history). `services/agent.py` is now queries only.
- Graph: prepare → plan → code → test ⟲ (repair ≤3) → review → human_approval (`interrupt`) → publish; `fail` on exhausted attempts. Statuses added: `review_failed`, `cancelled`.
- Runs start in the background (`POST /tasks/{id}/run` → 202); UI streams progress over SSE (polling fallback). Cancel is cooperative at node boundaries; resume continues from the last checkpoint (allowed for error/cancelled/stale-running).
- Bounds (config): `agent_max_attempts` 3, `agent_max_llm_calls` 8, `agent_max_tokens` 100k, `agent_run_timeout_seconds` 900, `agent_review_max_changed_lines` 300. Groq provider now reports token usage (`last_usage`).
- ⚠️ Gotcha: `PostgresSaver.setup()` uses `CREATE INDEX CONCURRENTLY` → deadlocks if called while any transaction is open (e.g. lazily inside a request). It runs from `alembic upgrade head` (env.py) and in the test session fixture. Never call it lazily.
- Migration head `b88d25944321`. Sandbox runs as host uid (root-owned files broke `git clean`).
- Tests: 103 backend (graph, repair loop, budgets, review guard, cancel, resume-from-checkpoint, approve/reject/stale, HTTP flow, Postgres restart durability). Web: lint + tsc + 9 Vitest + build.
- Live proof 2026-10-01: task pinned to devpilot-demo@5eec58f → validated in ~12s, 7 checkpoints; killed + restarted uvicorn; new process loaded the paused graph and resumed it (rejected → nothing published).

## ✅ Phase 6 — Repository RAG (done, evaluated)
- Postgres image is now `devpilot-postgres:17-pgvector` built from `infra/postgres/Dockerfile` (`FROM postgres:17` + pgvector) — ⚠️ don't switch the dev volume to `pgvector/pgvector:pg17` (Debian bookworm, different glibc → collation risk). CI uses that image (fresh DB, fine). Pre-swap backup was taken to the session scratchpad.
- `app/rag/` (chunking, embeddings, index). fastembed `BAAI/bge-small-en-v1.5` (384-d, local, downloads ~67MB once). Hybrid retrieval: exact cosine + FTS → RRF; traceback boost; files ranked by best chunk.
- Graph: `retrieve` node; `target_path` optional → planner localizes (`TARGET:` line), server validates (tracked + indexable) else falls back. Per-run `use_rag`; RAG off + no target = file-list baseline.
- LLM client retries 429 per Retry-After (cap 30s × 6). Groq free tier = 8k TPM — evals must be paced.
- Migration head `cb5554ccaecd`. Tests 137. Eval: `python -m scripts.rag_eval --owner smoke-phase4@example.com` → `docs/eval/phase6-rag.md` (root-cause localization RAG 5/5 vs no-RAG 2/5; both resolve 5/5).

## 🟡 Phase 7 — SWE-bench Lite (harness done; v2 running unattended)
- Harness: `app/evals/swebench.py`, CLI `python -m scripts.swebench_eval {generate,score,report}` (see `docs/eval/README.md`). Scoring uses the **official** `swebench` harness installed in `apps/api/.venv-swebench` (gitignored; `pip install swebench`). Results in `eval_runs`/`eval_results`, API `/api/v1/evals`, web `/evals`.
- Configs: `rag` (headline, issue only), `oracle-file`, `oracle-file+rag`, optional `gold` calibration. Agent never sees tests (no test command).
- Agent changes for real repos: excerpts + SEARCH/REPLACE edits for files > 12k chars (diff-hunk fallback; fuzzy only ≥3 lines & unique), prompt budgets, optional test command, lazy embeddings for repos > 3k chunks, IDF keyword filter, source-first candidates, daily-quota 429 stops immediately.
- Constraints: Groq free tier = 8k TPM / 1k RPD (only gpt-oss-120b/20b + qwen available); CPU embeddings ~12 chunks/s; disk ~9 GB free → scorer deletes each instance image (~3.8 GB). `requests` tests hit live network → harness may flag `network_unreachable` infra failures.
- **Groq daily cap: 200k tokens/day (rolling) for gpt-oss-120b** — ≈7 instances × 3 configs per day.
- Runs (2026-10-01): `lite-s20-seed7-v1-nogate` = first 6 instances with the pre-syntax-gate agent (kept as an ablation). `lite-s20-seed7` = **v2 headline** (syntax gate on). An unattended loop runs `score v1 → report v1 → run-all v2 --with-gold` (log: `~/.cache/devpilot/swebench/run-all.log`); it sleeps 30 min between quota windows and rewrites `docs/eval/phase7-*.md` after every pass. If the machine restarts, re-run (from `apps/api`, `.venv` active, with ≥6 GB free — ideally ~8): `nohup python -m scripts.swebench_eval run-all --name lite-s20-seed7 --n 20 --seed 7 --owner smoke-phase4@example.com --with-gold >> ~/.cache/devpilot/swebench/run-all.log 2>&1 &` (the CLI prints to stdout; the log is just this redirect).
- **Status 2026-10-22:** the v2 run resumed as the `devpilot-benchmark` systemd user service (see "SWE-bench
  pipeline" below). At launch: django-11620 complete (rag ❌, oracle-file ❌, gold ✅ — re-scored in CI, identical),
  django-11848 generated (all 3 configs validated, RAG localized `django/utils/http.py`).
- **Disk guard (2026-10-22):** `app/evals/swebench.py` checks free space on the tighter of the eval cache and Docker's data root (`docker info` → `/var/lib/docker`) before each instance: generation needs `MIN_FREE_GB_GENERATE`=2 GB; local scoring needs `max(6, 4 × compressed + 1)` GB with the compressed size from Docker Hub (12 GB if unknown) — this machine's Docker uses the **containerd image store**, which keeps compressed + unpacked layers. Measured compressed sizes: django ≈1.15 GB, sympy/sphinx/pylint ≈1.1, scikit-learn 1.5, **matplotlib 3.07**. Below the threshold it raises `LowDisk`; `run-all`/`pipeline` sleep and retry and finish only when generation **and** scoring are complete.
- **SWE-bench pipeline (2026-10-22):** `python -m scripts.swebench_eval pipeline` (`scripts/eval_pipeline.py`) =
  generate → `ci-score` (export `docs/eval/predictions/<name>.jsonl` → push → dispatch `swebench-score.yml` → wait →
  download `swebench-scores` → import; a CI harness error never overwrites a real verdict) → `publish_final`
  (report + README section between `<!-- swebench:start/end -->` + `apps/api/showcase/showcase.json`, one commit) →
  marker `~/.cache/devpilot/swebench/pipeline-lite-s20-seed7.done` → disables the unit → waits for the live API to
  serve the final results, re-captures `docs/images/benchmarks.png` (`apps/web/scripts/capture-benchmarks.mjs`,
  playwright-core + system Chrome; best effort). Commits come from the clone `~/.cache/devpilot/swebench/publish-repo`
  (never the owner's checkout) and end in `[automated]`; after them, `git pull --ff-only` in the checkout is clean.
- **Service:** `~/.config/systemd/user/devpilot-benchmark.service` (from `infra/systemd/install.sh` + `.service.in`),
  args `--name lite-s20-seed7 --n 20 --seed 7 --owner smoke-phase4@example.com --with-gold --ablation
  lite-s20-seed7-v1-nogate --site https://devpilot-pied.vercel.app --api https://devpilot-api-gr7a.onrender.com`.
  Log `~/.cache/devpilot/swebench/pipeline.log`. Status `systemctl --user status devpilot-benchmark`; stop
  `systemctl --user disable --now devpilot-benchmark`. Verified that `gh` (keyring), git credentials and Docker all
  work inside systemd. Restarting is safe (finished results are in the DB; only an in-flight run is redone).
- **CI scoring validated 2026-10-22:** run https://github.com/krish1809/devpilot/actions/runs/39701119345 (4 min) — gold ✅
  (F2P 1/1, P2P 66/66), rag ❌, oracle-file ❌: identical to local. Those 3 rows now carry `scored_by: GitHub Actions …`.
- Scoring lessons: harness `patch_successfully_applied=false` can mean the patched file didn't import (we saw IndentationError) → hence the syntax gate; "Image not found" was a transient Docker Hub failure → scorer now retries harness errors (3×) instead of scoring them.
- ⚠️ Stop the pipeline with systemd (above). For a manually started loop, stop it by **exact PID**: `ps -eo pid,args | grep scripts.swebench_eval` then `kill <pid>`. `pkill -f`/`pgrep -f` patterns match the agent tool's own shell wrapper (`bash -c …`) — they have killed it twice and miscounted processes once; use `systemctl --user show -p MainPID --value devpilot-benchmark`.

## ✅ Live run streaming (SSE) — added 2026-10-22
- `GET /api/v1/runs/{id}/stream` → `app/api/agent.py::stream_run` + `app/services/run_stream.py::run_events`.
  Re-reads the run every 1 s (`db.expire_all()`, then `rollback()` to free the connection), emits `run` (full
  `RunResponse` JSON) only on change, `done` when status ≠ `running`, `timeout` after `agent_run_timeout_seconds`+60,
  `: keep-alive` every 15 s. Headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`. No gzip middleware in the
  stack (would buffer SSE) — keep it that way.
- Web: `lib/sse.ts` + `api.streamRun` (fetch streaming; token in the Authorization header — `EventSource` can't send
  headers and a URL token would hit access logs). `app/tasks/[id]/page.tsx` streams while `running`, falls back to
  1.5 s polling on stream failure/timeout; a `finished` flag prevents a stray poll after the final snapshot.
- Tests: `tests/test_run_stream.py` (8), `lib/sse.test.ts` (5), 3 `streamRun` tests in `lib/api.test.ts`.
- Live check: local API on :8001, run 86 (devpilot-demo @ 5eec58f) streamed prepare→retrieve→plan→code→test→review→
  validated→done in ~16 s. Run 86 + user `live-sse-<ts>@example.com` remain in the LOCAL dev DB, unapproved
  (nothing published). The demo API on Render gets the endpoint on the next deploy; showcase runs are finished, so
  there it sends one snapshot and `done`.

## ✅ Phase 8 — MCP server + observability + injection defenses (done in code)
- `app/mcp/server.py`: `devpilot-tools` (MCP SDK **2.x** — `MCPServer`, not FastMCP), bound per process to one run + policy (`read`/`execute`). Tools: `run_tests` (only the task's configured command, in the sandbox), `git_diff`, `read_file` (confined, secrets refused), `search_code`. Denials are `ToolError`s (reason reaches client; crashes stay generic). Every call → `tool_calls` audit (redacted args). `app/mcp/client.py`: stdio subprocess in production (`AgentDeps.tool_server=stdio_target`), in-process in tests. The agent's sandbox runs go through it.
- Tracing: `llm_calls` table (node, tokens, latency, ok/error) + `GET /runs/{id}/trace`; web trace panel. No Langfuse (self-host too heavy for the disk; built-in tracing instead).
- Injection: `tests/test_injection.py` (secrets never in prompts, injected text confined to untrusted tags, protected CI/secret paths, sandbox has no network); `agents/risk.py` review warnings above Approve; syntax gate in `_code`.
- Tests: 183 backend, 17 web. Migration head `b04f052d3d3e`.

## ✅ Phase 9 — Deploy + polish (live)
- ⚠️ The Neon connection string (with password) was pasted in chat on 2026-10-02; the user said they'd reset the `neondb_owner` password and update Render's `DATABASE_URL`. **Not yet confirmed** (needs their Neon + Render dashboards). Never write that string into files/commits.
- **Showcase autoload (2026-10-22):** export lives at `apps/api/showcase/showcase.json` (moved from `deploy/`) and ships in the image; the Dockerfile runs `alembic upgrade head && (python -m scripts.showcase autoload || true) && exec uvicorn …`. Autoload imports only in DEMO_MODE and only when the file's SHA-256 differs from `app_state.showcase_sha256` (migration head `cd35ce4e3392`). Refreshing prod = commit a new export (Render redeploys on `apps/api/**`). First autoload ran on deploy 2026-10-22 → demo task ids changed 1–3 → **4–6**. ⚠️ Never run autoload/import with DEMO_MODE against the dev DB: it replaces eval runs with the same names (the real benchmark rows).
- Render env: DEMO_MODE=true, SECRET_KEY (generated), DATABASE_URL (Neon, pooler), CORS_ORIGINS=https://devpilot-pied.vercel.app. Vercel env: NEXT_PUBLIC_API_URL=https://devpilot-api-gr7a.onrender.com. Both auto-deploy from `main`.
- Showcase mode `DEMO_MODE=true` (`app/core/demo.py`): middleware refuses all writes except login + `/auth/demo`, blocks `/api/v1/github/*`; `POST /auth/demo` → read-only demo user; `GET /api/v1/config` → `{demo_mode}`. Web adapts (demo button on login, banner, hides run/approve/import controls).
- `scripts/showcase.py export|import|autoload` → `apps/api/showcase/showcase.json` (tasks 3, 4, 51 + both SWE-bench runs; scrubbed paths/org ids; idempotent import under demo user). The pipeline re-exports it automatically when v2 finishes.
- Deploy: `render.yaml` (API, Docker, free), Dockerfile runs `alembic upgrade head` then uvicorn on `$PORT`; DB URLs `postgres://`/`postgresql://` auto-normalized; Vercel root `apps/web` with `NEXT_PUBLIC_API_URL`; Neon for Postgres+pgvector. Guide: `docs/DEPLOY.md`.
- Rehearsed 2026-10-02: built image (702 MB), ran in demo mode on an empty DB → migrations OK, 118 MB RAM, import OK (twice), visitor flow + 403 on writes + CORS OK.
- Showcase run: devpilot-demo issue #4 (weather °C bug in units.py, not named in the issue) → localized via RAG → PR #5 (run 51, through MCP stdio, traced).
- README rewritten as a product page; screenshots + GIF in `docs/images/` (captured with playwright-core driving system Chrome; script lives in the session scratchpad — recapture benchmarks.png when v2 completes).
- I accidentally committed `__pycache__` to devpilot-demo (Phase 4 + Phase 9 commits); removed in `fddab84` with a `.gitignore`.
- (older note) GitHub Actions CI (`.github/workflows/ci.yml`) — backend ruff+migrations+pytest and frontend lint+vitest+build. Was red from Phase 4 until 2026-10-01 (setuptools flat-layout error on `pip install -e .`); fixed — **check `gh run list` after every push**. Deploy (Vercel/Render/Neon) + demo README not done.

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
- GitHub push for PRs now uses the API's token via env (Phase 4). The PAT exposed in chat (2026-09-28) is **dead**: verified 2026-10-22 with the exact token (length-checked) → HTTP 401; `~/.git-credentials` doesn't exist; git uses the `gh` credential helper.
- Disk (2026-10-22): freed 1.99 GB safely (npm cache, pnpm metadata/dlx cache, `pnpm store prune`, `uv cache prune`, Docker build cache, unused `pgvector/pgvector:pg17` image) → ≈3.5 GB free. Left alone on purpose: `~/.cache/huggingface` (other projects' models), browser caches (browsers running), `~/Downloads`, other projects, Docker volumes. The uv cache is mostly hard-linked into project venvs, so clearing it frees little.

## Verify-before-trust checklist for agents
Before acting: read `docs/PLAN.md`, run `git status`, `alembic current`, check this file's date. If a referenced file/flag isn't present, re-inspect — docs may lag.
