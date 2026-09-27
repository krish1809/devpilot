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
- No rate limiting yet.
- No application-wide error envelope yet (validation uses the default FastAPI/Pydantic `422` shape; not-found/auth use `{"detail": "..."}`).
- No task, repository, or agent-run endpoints yet.

## Evolution rules
Keep routes versioned, use explicit schemas, validate inputs, maintain consistent errors, and test success, validation, missing-resource, and authorization paths.
