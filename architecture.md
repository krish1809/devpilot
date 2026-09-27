# DevPilot — Architecture

**Last updated:** 2026-09-28

> This is the concise, agent-facing architecture reference (app flow, folder/file structure, tech stack). For the deeper design narrative, domain entities, and the agent state machine, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 1. Tech stack

| Layer | Technology | Status |
|---|---|---|
| API | Python 3.12, FastAPI, Pydantic v2 | **In use** |
| ORM / migrations | SQLAlchemy 2.x (typed), Alembic | **In use** |
| Database | PostgreSQL 17 | **In use** |
| Tests / quality | pytest, HTTPX, Ruff | **In use** |
| Packaging / run | Docker, docker-compose, Uvicorn | **In use** |
| Frontend | Next.js, React, TypeScript, Tailwind, shadcn/ui | Planned (Phase 2) |
| Auth | TBD (session/JWT), RBAC | Planned (Phase 3) |
| Cache / queue | Redis + workers | Later, if needed |
| Agent orchestration | LangGraph | Planned (Phase 6) |
| Retrieval | pgvector, embeddings | Planned (Phase 7) |
| Tools | MCP + internal adapters | Planned (Phase 8) |
| Sandbox | Docker, resource-limited, network-off | Planned (Phase 9) |
| Observability | OpenTelemetry, Prometheus, Grafana | Planned (Phase 12) |
| CI/CD | GitHub Actions | Planned (Phase 13) |

## 2. High-level app flow

```text
Next.js UI ──HTTPS/SSE──> FastAPI API (modular monolith)
                              ├── PostgreSQL (durable state; pgvector later)
                              ├── Redis / workers (later)
                              └── LangGraph agent runtime (later)
                                    plan → inspect → implement → validate → review
                                      └── permissioned tools / MCP
                                            └── Docker sandbox (untrusted code)
                                                  └── human approval → GitHub PR
```

**Request path (current):** `HTTP → router → Pydantic schema → service → SQLAlchemy model → PostgreSQL`.
Routers stay thin (HTTP, DI, status codes, serialization). Services hold use-case logic and own transactions. Schemas validate input and shape output — ORM models are never exposed as request bodies.

## 3. Folder & file structure (current)

```text
devpilot/
├── apps/
│   └── api/
│       ├── app/
│       │   ├── api/
│       │   │   ├── deps.py           # Annotated DI aliases (DbSession)
│       │   │   └── projects.py       # Project router (thin)
│       │   ├── core/
│       │   │   └── config.py         # Pydantic Settings (env-driven)
│       │   ├── db/
│       │   │   ├── base.py           # DeclarativeBase
│       │   │   └── session.py        # engine, SessionLocal, get_db
│       │   ├── models/
│       │   │   └── project.py        # Project ORM model
│       │   ├── schemas/
│       │   │   └── project.py        # ProjectCreate/Update/Response
│       │   ├── services/
│       │   │   └── project.py        # CRUD use-case logic
│       │   └── main.py               # FastAPI app + /health
│       ├── alembic/                  # env.py, versions/ (migrations)
│       ├── tests/                    # conftest.py + test_*.py (dedicated test DB)
│       ├── Dockerfile
│       ├── .dockerignore
│       └── pyproject.toml            # deps + ruff + pytest config
├── docs/                            # deep design docs (architecture/security/api/...)
├── PRD.md architecture.md rules.md phases.md design.md memory.md  # agent-steering files
├── Makefile
├── docker-compose.yml               # postgres + migrate + api
├── .env.example                     # committed template (never .env)
└── README.md
```

## 4. Planned structure (added only when implemented)
```text
apps/api/app/
├── agents/         # LangGraph nodes/state (Phase 6)
├── integrations/   # GitHub/LLM provider adapters (Phase 4-5)
└── core/security.py  # auth/RBAC helpers (Phase 3)
apps/web/           # Next.js frontend (Phase 2)
infra/              # IaC, if justified (Phase 16)
.github/workflows/  # CI (Phase 13)
```

## 5. Module boundaries (rules of thumb)
- **Router** → HTTP only, delegates to services.
- **Service** → business logic + transaction coordination; no HTTP concerns.
- **Model** → persistence shape only.
- **Integration adapter** → narrow wrapper around one external provider.
- **Agent node** → one bounded workflow stage; no ambient access to all tools.
- **Sandbox** → runs untrusted repo code; never on the API host.

## 6. Key architectural decisions
- Modular monolith first; split services only when operations demand it.
- PostgreSQL is the source of truth; Redis is never authoritative.
- Alembic for all schema changes; never `create_all()` as a migration substitute.
- LLM access behind a provider abstraction.
- Model output + tool authorization: model **cannot** authorize itself; auth is server-side.
- Human approval is mandatory before any external publish.
