# DevPilot — Architecture

## Product flow
User task or GitHub issue → context retrieval → plan → human plan review (optional) → code patch in isolated workspace → tests/security checks → diff review → explicit approval → GitHub branch/PR → audit trail.

## Logical diagram

```text
┌─────────────────────────────┐
│ Next.js UI                  │
│ projects / tasks / run / diff│
└──────────────┬──────────────┘
               │ HTTPS + SSE
┌──────────────▼──────────────┐
│ FastAPI modular monolith    │
│ auth · API · app services   │
└───────┬──────────────┬──────┘
        │              │
┌───────▼────────┐ ┌───▼────────────────┐
│ PostgreSQL     │ │ Redis + workers    │
│ domain state   │ │ later, if needed   │
│ pgvector later │ └────────┬───────────┘
└────────────────┘          │
                    ┌───────▼────────────┐
                    │ LangGraph runtime  │
                    │ plan/inspect/code/ │
                    │ test/review        │
                    └────────┬──────────┘
                             │
                    ┌────────▼───────────┐
                    │ Permissioned tools │
                    │ GitHub / MCP / repo│
                    └────────┬───────────┘
                             │
                    ┌────────▼───────────┐
                    │ Docker sandbox     │
                    │ isolated execution │
                    └────────┬───────────┘
                             │
                    ┌────────▼───────────┐
                    │ Human approval     │
                    │ then PR publishing │
                    └────────────────────┘
```

## Component responsibilities
- **Web:** project/repository/task UI, run timeline, diff and validation display, approval action.
- **FastAPI:** versioned API, validation, authentication, authorization, use-case orchestration, SSE.
- **PostgreSQL:** durable users, projects, repositories, tasks, runs, events, approvals, artifacts metadata, PR references.
- **Redis/workers:** later asynchronous work and coordination; durable state remains in PostgreSQL.
- **LangGraph:** stateful, bounded workflow nodes with resumability.
- **Model adapter:** provider-neutral interface; model and provider configured externally.
- **Tools/MCP:** narrow typed interfaces with server-side permissions, timeouts, and audit.
- **Sandbox:** executes untrusted code away from API host, with resource limits and network disabled by default.
- **Approval/publishing:** approval bound to exact diff and base commit; publish only after required checks and explicit approval.

## Target domain entities
Conceptual entities to add only when needed:
- User: identity and access state.
- Project: user-owned grouping of work.
- RepositoryConnection: authorized GitHub repository reference; avoid storing raw long-lived tokens.
- Task: prompt or imported issue.
- AgentRun: attempt, status, model/config, base commit, timestamps, result.
- RunEvent: append-oriented activity timeline.
- Artifact: patch, logs, reports, controlled retention.
- Approval: actor, decision, timestamp, reviewed artifact hash.
- PullRequest: external PR ID/URL and publication status.
- EvaluationCase/Result: benchmark and measurements.

## Agent run state
Use typed state with run/task IDs, repository and base commit, task text, context references, structured plan, patch/artifact references, validation results, stage/status, retry counters, usage/cost, approval, PR result, and safe error summary. Avoid storing full repositories in graph state; use bounded context and artifact references.

## Suggested state machine
```text
CREATED → QUEUED → PLANNING → [PLAN_REVIEW]
        → INSPECTING → IMPLEMENTING → VALIDATING
        → [REPAIRING → VALIDATING, bounded]
        → REVIEWING → AWAITING_APPROVAL
        → PUBLISHING → COMPLETED
```
Also account for `FAILED`, `TIMED_OUT`, `CANCELLED`, `REJECTED`, and `PUBLISH_FAILED`. Enforce legal transitions in application logic. Publishing must be impossible without required validation and approval.

## Design decisions
- Start as a modular monolith; split services only when operational needs justify it.
- Use REST/JSON for standard APIs and SSE for one-way progress updates initially.
- Use PostgreSQL for durable state; Redis is not the source of truth.
- Use Alembic for schema evolution.
- Use a provider abstraction for LLMs.
- Keep model output untrusted and tool authorization outside the model.
- Require human approval for external publishing.
- Introduce Kubernetes/Terraform only if there is a demonstrated need.
