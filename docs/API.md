# DevPilot API — Current Contract

The live OpenAPI document at `/docs` is authoritative if it differs from this summary.

Local base URL: `http://localhost:8000`
Versioned prefix: `/api/v1`

## Health
`GET /health` returns `{"status":"ok"}`. This is a basic liveness endpoint, not necessarily a dependency-aware readiness check.

## Projects
| Method | Path | Behavior |
|---|---|---|
| POST | `/api/v1/projects` | Create; expected `201` |
| GET | `/api/v1/projects` | List; expected `200` |
| GET | `/api/v1/projects/{project_id}` | Get one; `200` or `404` |
| PATCH | `/api/v1/projects/{project_id}` | Partial update; `200` or `404` |
| DELETE | `/api/v1/projects/{project_id}` | Delete; `204` or `404` |

Create example:
```json
{
  "name": "DevPilot",
  "description": "AI software engineering platform"
}
```

Response includes `id`, `name`, `description`, `created_at`, and `updated_at`. Inspect `/docs` for the exact live schema.

## Validation
- `name` is required, non-empty, and at most 100 characters. Violations return `422` with the standard FastAPI/Pydantic error envelope.
- On `PATCH`, `name` is optional but, when present, must satisfy the same constraints.

## Known limitations
- Authentication/authorization not implemented.
- No pagination yet.
- No application-wide error envelope yet (validation uses the default FastAPI/Pydantic `422` shape; not-found uses `{"detail": "..."}`).
- No project ownership yet.
- No task, repository, or agent-run endpoints yet.

## Evolution rules
Keep routes versioned, use explicit schemas, validate inputs, maintain consistent errors, and test success, validation, missing-resource, and authorization paths.
