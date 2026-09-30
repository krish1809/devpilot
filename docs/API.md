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
`project.deleted`. Audit rows never contain passwords, tokens, or full payloads.

## Agent (walking skeleton)
The agent turns a failing test into a fix and, after human approval, a PR.
All endpoints require authentication and are owner-scoped.

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/tasks` | Create a task (`repo_url`, `base_commit?`, `test_command`, `target_path`, `description?`); `201` |
| GET | `/api/v1/tasks` | List caller's tasks; `200` |
| GET | `/api/v1/tasks/{id}` | Get a task; `200`/`404` |
| POST | `/api/v1/tasks/{id}/run` | Run the agent synchronously; returns the run with `diff`, `test_passed`, `status`, and `events` |
| GET | `/api/v1/runs/{id}` | Get a run (with events and any pull request); `200`/`404` |
| POST | `/api/v1/runs/{id}/approve` | `{decision: "approved"\|"rejected", base_branch?}`. Approving a **validated** run opens a PR; `409` if the run is not validated |

Run `status` values: `running`, `validated`, `test_failed`, `error`, `approved`,
`rejected`, `published`, `publish_failed`. Publishing is impossible without an
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
- No task, repository, or agent-run endpoints yet.

## Evolution rules
Keep routes versioned, use explicit schemas, validate inputs, maintain consistent errors, and test success, validation, missing-resource, and authorization paths.
