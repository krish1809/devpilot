# DevPilot — AI Software Engineering Platform

**Status:** Backend Phases 0–3 (auth, project ownership, rate limiting, audit) + Phase 2 frontend
**Repository:** https://github.com/krish1809/devpilot

DevPilot is a human-supervised AI software engineering platform. Its intended workflow is to accept a software task (including a GitHub issue), inspect a repository, create a plan, propose code changes, run validation in an isolated environment, present a diff for review, and—after explicit human approval—create a GitHub pull request.

The workflow below is the target product design. The currently confirmed implementation is the initial FastAPI/PostgreSQL backend and Project CRUD API; future agent, GitHub, frontend, and deployment features are not yet implemented.

## Product goals
- Demonstrate real software engineering: backend, data, AI agents, security, testing, DevOps, and observability.
- Build incrementally as a maintainable modular monolith before considering separate services.
- Keep LLM providers replaceable.
- Make agent plans, tool calls, validation, approvals, and outcomes inspectable.
- Keep humans in control of consequential repository actions.

## Intended workflow
1. Create a DevPilot project.
2. Connect an authorized GitHub repository.
3. Submit a task or select an issue.
4. Inspect repository context at a known commit.
5. Generate a structured plan and review it.
6. Implement a patch in an isolated workspace.
7. Run tests, lint, type checks, and configured security checks.
8. Review the diff and results.
9. Obtain explicit human approval.
10. Create a branch and pull request.
11. Preserve a traceable run history and audit trail.

## Architecture

```text
Next.js UI ──HTTPS/SSE──> FastAPI API
                              ├── PostgreSQL (+ pgvector later)
                              ├── Redis / workers (later)
                              └── LangGraph agent runtime (later)
                                      ├── planner / repo analyst
                                      ├── coder / tester / reviewer
                                      └── permissioned tools / MCP
                                               └── isolated Docker sandbox
                                                        └── human approval
                                                             └── GitHub PR
```

The early implementation can run in one API process. Introduce workers and additional infrastructure only when justified.

## Planned stack

| Area | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript |
| UI | Tailwind CSS, shadcn/ui |
| API | Python, FastAPI, Pydantic |
| ORM/migrations | SQLAlchemy 2.x, Alembic |
| Database | PostgreSQL; pgvector later |
| Cache/queue | Redis later |
| Agent orchestration | LangGraph |
| Tool interoperability | MCP plus internal adapters |
| Execution | Docker sandbox, hardened before untrusted code |
| Tests/quality | pytest, HTTPX, Ruff |
| CI/CD | GitHub Actions |
| Observability | OpenTelemetry, Prometheus, Grafana |
| Deployment | Container-based cloud deployment |
| IaC | Terraform/Kubernetes optional later |

LLM access must use a provider abstraction. Provider and model are configuration, not hard-coded business logic. Local Ollama and hosted providers can be supported as appropriate. API credentials are separate from a ChatGPT subscription; keep keys in environment variables or a secret manager, never in Git.

## Repository layout

```text
devpilot/
├── apps/
│   └── api/
│       ├── app/
│       │   ├── api/          # HTTP routers + dependencies (deps.py)
│       │   ├── core/         # settings/security
│       │   ├── db/           # SQLAlchemy base/session
│       │   ├── models/       # ORM models
│       │   ├── schemas/      # Pydantic models
│       │   ├── services/     # use-case logic
│       │   └── main.py
│       ├── alembic/          # migrations
│       ├── tests/            # pytest suite (dedicated test DB)
│       ├── Dockerfile
│       └── pyproject.toml
├── docs/
├── Makefile
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```
Future directories (`apps/web`, `infra/`, `.github/workflows/`, `agents/`, `integrations/`) are added when implementing them.

## Quick start (Docker, full stack)

Requirements: Docker Engine/Compose.

```bash
docker compose up -d --build   # or: make docker-up
```

This starts PostgreSQL, runs Alembic migrations (`migrate` service), then starts the API.

- Health: http://localhost:8000/health
- Swagger: http://localhost:8000/docs

Stop with `docker compose down` (or `make docker-down`).

> Note: building the API image pulls `python:3.12-slim`, so registry access is required on first build.

## Local backend setup (venv)

Requirements: Python 3.11+, Docker Engine/Compose, Git.

From repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Copy root `.env.example` to `.env` and adjust local values if needed. Keep `.env` ignored by Git.

Start PostgreSQL from repository root:

```bash
docker compose up -d postgres
docker compose ps
```

Apply migrations and run the API from `apps/api`:

```bash
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload
```

- Health: http://localhost:8000/health
- Swagger: http://localhost:8000/docs

Checks from `apps/api`:

```bash
pytest -v
ruff check .
ruff format --check .
```

Tests use a dedicated test database (`devpilot_test` by default, or `TEST_DATABASE_URL`). The suite creates and drops that database itself; destructive setup never runs against the development or production database.

## Frontend (apps/web)

Next.js 14 (App Router) + TypeScript + Tailwind. Auth (register/login) and full
project CRUD against the API. See [apps/web/README.md](apps/web/README.md).

```bash
cd apps/web
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL (default http://localhost:8000)
npm install
npm run dev                        # http://localhost:3000
```

Verified with `npm run build` and `npm run test` (Vitest).

## Current API

Base prefix: `/api/v1`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Basic liveness response |
| POST | `/projects` | Create project |
| GET | `/projects` | List projects |
| GET | `/projects/{project_id}` | Retrieve project |
| PATCH | `/projects/{project_id}` | Partially update project |
| DELETE | `/projects/{project_id}` | Delete project |

`name` is required, non-empty, and at most 100 characters. All project endpoints require a bearer token (`/api/v1/auth/register` + `/login`) and are scoped to the owner; another user's project returns 404. Register/login are rate-limited, and security-relevant actions are recorded to an audit log (`/api/v1/audit/me`). See [docs/API.md](docs/API.md) for the full contract.

## Development workflow
1. Inspect repository and Git status before editing.
2. Work on one small, coherent feature.
3. Follow `docs/AGENT_CONTEXT.md` and `docs/ARCHITECTURE.md`.
4. Add/update tests and docs.
5. Run relevant tests and lint/format checks; report actual results.
6. Review the diff for secrets and unrelated changes.
7. Commit meaningful, verified work. Do not create empty commits.

## Documentation
- [Coding-agent context](docs/AGENT_CONTEXT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Progress report](docs/PROGRESS.md)
- [API contract](docs/API.md)
- [Security design](docs/SECURITY.md)
