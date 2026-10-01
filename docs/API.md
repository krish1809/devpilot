# DevPilot API — Current Contract

The live OpenAPI document at `/docs` is authoritative if it differs from this summary.

Local base URL: `http://localhost:8000`
Versioned prefix: `/api/v1`

## Health
`GET /health` returns `{"status":"ok"}`. This is a basic liveness endpoint, not necessarily a dependency-aware readiness check.

## Auth
| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/auth/register` | Register; `201`, or `409` if email taken, `422` on invalid input |
| POST | `/api/v1/auth/login` | Log in; `200` with `{access_token, token_type}`, or `401` |
| GET | `/api/v1/auth/me` | Current user; `200` with a valid bearer token, else `401` |

`register` and `login` are rate-limited per client IP; exceeding the limit returns
`429` with a `Retry-After` header.

Authentication is a bearer JWT (HS256). Send it as `Authorization: Bearer <access_token>`.
Register example:
```json
{ "email": "user@example.com", "password": "supersecret" }
```
Passwords must be 8–128 characters. Emails are normalized to lowercase.

## Projects
All project endpoints **require authentication** and are **scoped to the owner**.
A project owned by another user returns `404` (existence is not revealed).

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/projects` | Create (owned by caller); `201`, `401` if unauthenticated |
| GET | `/api/v1/projects` | List caller's projects; `200`, `401` |
| GET | `/api/v1/projects/{project_id}` | Get one; `200`, `404`, `401` |
| PATCH | `/api/v1/projects/{project_id}` | Partial update; `200`, `404`, `401` |
| DELETE | `/api/v1/projects/{project_id}` | Delete; `204`, `404`, `401` |

## Audit
| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/audit/me` | Current user's own audit events (newest first); `200`, `401` |

Security-relevant actions are recorded to an append-only `audit_logs` table:
`user.registered`, `user.login.succeeded`, `user.login.failed`, `project.created`,
`project.deleted`, `task.imported_from_issue`, `run.approved`, `run.rejected`. Audit rows never contain passwords, tokens, or full payloads.

## Agent
The agent turns a failing test into a fix and, after human approval, a PR.
All endpoints require authentication and are owner-scoped.

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/tasks` | Create a task manually (`repo_url`, `base_commit?`, `base_branch?`, `test_command`, `target_path`, `description?`); `201`. A `https://github.com/...` URL is bound to `repo_full_name` automatically |
| POST | `/api/v1/tasks/from-issue` | Import an **open** GitHub issue (`repo_full_name`, `issue_number`, `base_branch?`, `target_path`, `test_command`); resolves the branch to a commit SHA and pins the task to it; verifies `target_path` exists at that SHA; `201`/`404`/`422` |
| GET | `/api/v1/tasks` | List caller's tasks; `200` |
| GET | `/api/v1/tasks/{id}` | Get a task; `200`/`404` |
| POST | `/api/v1/tasks/{id}/run` | Start the LangGraph agent **in the background**; optional body `{use_rag?: bool}` (default `RAG_ENABLED`); `202` with the new run (`status: running`). Poll `GET /runs/{id}` |
| GET | `/api/v1/tasks/{id}/runs` | The task's runs, newest first (`id`, `status`, `attempts`, `test_passed`, …) |
| GET | `/api/v1/runs/{id}` | A run: `status`, `plan`, `target_path` (given or localized), `use_rag`, `retrieval` (index stats, candidate files, retrieved chunk locations), `attempts`, `llm_calls`, `prompt_tokens`, `completion_tokens`, `diff`, `sandbox_output`, `events`, `pull_request`; `200`/`404` |
| GET | `/api/v1/runs/{id}/trace` | Every LLM call (node, model, prompt/completion tokens, latency, ok/error — no prompt text) and every audited MCP tool call (tool, redacted arguments, allowed/denied, outcome, latency); plus totals |
| GET | `/api/v1/runs/{id}/checkpoints` | Every persisted graph step (oldest first): `step`, `next` node(s), `attempts`, `llm_calls`, `waiting_for_approval` |
| POST | `/api/v1/runs/{id}/cancel` | Request cancellation of a `running` run (stops at the next node boundary → `cancelled`); `409` otherwise |
| POST | `/api/v1/runs/{id}/resume` | Continue an `error`/`cancelled`/abandoned run from its last checkpoint (`202`, background); `409` otherwise |
| POST | `/api/v1/runs/{id}/approve` | `{decision: "approved"\|"rejected", base_branch?}`. Resumes the graph paused at `human_approval`. Approving a **validated** run publishes a PR against the task's base branch (override with `base_branch`); `409` if not validated. The approval records the diff's SHA-256 + base commit, and publishing refuses if the diff changed (stale approval). Failed runs can still be rejected |

`target_path` is optional (Phase 6): when omitted, the planner localizes the file — from
retrieved candidates with RAG on, or from the plain file list with RAG off — and the
server only accepts a tracked, indexable text file. When given, it must be a relative
path inside the repo (no `..`, absolute paths, or `.git/`);
branch names are validated so they can't be read as git options.

## Benchmarks (Phase 7)
Read-only, any authenticated user. Written by `python -m scripts.swebench_eval`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/evals` | Benchmark runs, newest first, with per-config summaries (resolved/scored, resolve rate + 95% Wilson CI, infra failures, patches produced, gold-file localization, avg tokens/LLM calls/time) |
| GET | `/api/v1/evals/{id}` | One run: summary plus every (instance, config) result including the patch and the harness's test-status counts |

## GitHub (Phase 4)
Server-side token only (`GITHUB_TOKEN`, a fine-grained PAT; falls back to the host's `gh auth token`).
The token is never returned to clients. Upstream failures map to `404` (not found / no access),
`422` (invalid input), `503` (no token configured), or `502` (other GitHub errors).

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/github/repos` | Repos the token can access (`full_name`, `default_branch`, `private`, `can_push`, …) |
| GET | `/api/v1/github/repos/{owner}/{name}/issues?state=open` | Issues (PRs filtered out) |
| GET | `/api/v1/github/repos/{owner}/{name}/tree?ref=` | Files at `ref` (default branch if omitted) plus the resolved `commit_sha` |

A run also carries `review_warnings`: security-sensitive constructs the patch newly adds
(environment access, process execution, network calls, credential paths, payload decoding),
shown to the reviewer before approval. They warn; they don't block.

Run `status` values: `running`, `validated` (waiting for approval), `test_failed`,
`review_failed`, `error`, `cancelled`, `approved`, `rejected`, `published`, `publish_failed`.
Runs are bounded by `AGENT_MAX_ATTEMPTS` (3), `AGENT_MAX_LLM_CALLS` (8),
`AGENT_MAX_TOKENS` (100k) and `AGENT_RUN_TIMEOUT_SECONDS` (900); hitting a bound ends the run as `error`. Publishing is impossible without an
explicit approval of a run whose test actually passed (human-in-the-loop gate).
Repository code is only ever executed in the disposable Docker sandbox.

Create example:
```json
{
  "name": "DevPilot",
  "description": "AI software engineering platform"
}
```

Response includes `id`, `owner_id`, `name`, `description`, `created_at`, and `updated_at`. Inspect `/docs` for the exact live schema.

## Validation
- `name` is required, non-empty, and at most 100 characters. Violations return `422` with the standard FastAPI/Pydantic error envelope.
- On `PATCH`, `name` is optional but, when present, must satisfy the same constraints.

## Known limitations
- Auth is bearer-JWT (HS256) with per-owner project scoping; no roles/teams, no refresh tokens, no token revocation list yet.
- Tokens are signed with stdlib HMAC + `hashlib.scrypt` password hashing (no external crypto deps in the sandbox); swap to `bcrypt`/`PyJWT` when convenient — see `app/core/security.py`.
- No pagination yet.
- Rate limiting is in-memory/per-process (fine for a single API process; a multi-replica deployment would need a shared store, which is out of scope for this portfolio project).
- No application-wide error envelope yet (validation uses the default FastAPI/Pydantic `422` shape; not-found/auth use `{"detail": "..."}`).
- Agent runs execute in the API process's background threads (FastAPI `BackgroundTasks`), not a separate worker; progress is polled, not streamed (no SSE). Cancellation is cooperative between graph steps.

## Evolution rules
Keep routes versioned, use explicit schemas, validate inputs, maintain consistent errors, and test success, validation, missing-resource, and authorization paths.
