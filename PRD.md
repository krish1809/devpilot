# DevPilot — Product Requirements Document (PRD)

**Owner:** krish1809
**Status:** Living document · Phase 1 complete (backend foundation)
**Last updated:** 2026-09-28

> This is the single source of truth for *what* DevPilot is and *why*. For *how* it is built, see [architecture.md](architecture.md); for *when*, see [phases.md](phases.md).

---

## 1. What we are building
DevPilot is a **human-supervised AI software engineering platform**. A user gives it a software task (a prompt or an imported GitHub issue); DevPilot inspects the target repository, produces a structured plan, generates a code patch in an isolated sandbox, runs validation (tests/lint/security), presents a reviewable diff, and — **only after explicit human approval** — opens a GitHub pull request. Every run leaves an auditable trail.

It is a **workflow product**, not a chat wrapper. The differentiators are inspectability (you can see the plan, tool calls, validation, and approval) and control (a human gates every consequential repository action).

## 2. Problem statement
AI coding assistants today either (a) live inside the editor with no durable run history, approvals, or isolation, or (b) act autonomously with weak guardrails. Teams that want to *safely* delegate scoped engineering tasks lack a tool that combines automation with **auditable, gated, sandboxed** execution.

## 3. Target users
| Persona | Needs | How DevPilot helps |
|---|---|---|
| **Solo developer / indie hacker** | Offload well-scoped tasks (bug fixes, small features) without losing control | Task → plan → patch → review → PR, all supervised |
| **Small team lead** | Consistent, reviewable AI changes with an audit trail | Approval records bound to exact diff + base commit; run history |
| **Open-source maintainer** | Triage and draft fixes for issues safely | Import issue → sandboxed patch → PR for human review |
| **Portfolio reviewer / hiring manager** (secondary) | Evidence of real engineering breadth | Demonstrates backend, data, agents, security, testing, DevOps |

## 4. Goals & non-goals
**Goals**
- Safe, supervised automation of scoped software tasks.
- Provider-neutral LLM usage (no vendor lock-in in core logic).
- Full inspectability: plans, tool calls, validation, approvals, outcomes.
- Incremental, maintainable modular monolith.

**Non-goals (for now)**
- Fully autonomous, unsupervised code merging.
- Multi-tenant hosted arbitrary-code execution before the sandbox threat model is reviewed.
- Microservices / Kubernetes before there is demonstrated need.

## 5. Core features
### Implemented (Phase 1)
- **Project management** — CRUD for projects (FastAPI + PostgreSQL). Validated input, tested, containerized.

### Planned (see [phases.md](phases.md))
- **Frontend** — Next.js UI for projects, tasks, runs, diffs, approvals.
- **Auth & ownership** — user identity, project ownership, RBAC, rate limiting.
- **GitHub integration** — connect repos, import issues, open PRs (least-privilege, webhook verification).
- **AI assistant** — provider-neutral model interface, structured task analysis.
- **Agent system** — LangGraph plan → inspect → implement → validate → review, with durable state.
- **RAG** — repository-aware retrieval scoped by permission/commit (pgvector).
- **Tools/MCP** — typed, permissioned tools with server-side authorization and audit.
- **Sandboxed execution** — disposable Docker workspace, resource limits, network off by default.
- **Human-in-the-loop** — approval bound to diff hash + base commit; stale-approval invalidation.
- **Evaluation, observability, CI/CD, deployment, scaling.**

## 6. User workflow (target)
1. Create a project → 2. Connect a GitHub repo → 3. Submit a task / pick an issue → 4. Inspect repo at a known commit → 5. Generate & review plan → 6. Implement patch in sandbox → 7. Run tests/lint/security → 8. Review diff → 9. Approve → 10. Open branch + PR → 11. Preserve run history.

## 7. Success metrics
- **Task success rate** and **test pass rate** on a versioned benchmark (Phase 11).
- **Tool-call correctness**, latency, and token/cost per run.
- Zero secrets leaked to prompts/logs/artifacts; zero unapproved publishes.

## 8. Constraints & assumptions
- Python 3.11+, PostgreSQL as source of truth, Alembic for schema.
- LLM provider and model are configuration, never hard-coded in business logic.
- Model output, repository content, and tool output are **untrusted**.
- Requires explicit human approval before any external publish.
