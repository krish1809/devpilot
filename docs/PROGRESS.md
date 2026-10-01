# DevPilot — Progress Report

**As of:** 2026-09-30
**Roadmap authority:** [PLAN.md](PLAN.md) (9 phases). This file tracks progress against those phases; it does not define them.

## Summary
Phases 1–4 are done. The full loop (clone → baseline test → LLM patch →
sandbox re-test → diff → human approval → real PR) runs from the browser, and
tasks can now be imported straight from a GitHub issue on any repo the token can
access. Next is **Phase 5 — the LangGraph agent**. Phases 5–8 are not started;
Phase 9 has a CI seed only.

## Progress against PLAN.md phases

| Phase | Title | Status | Notes |
|---|---|---|---|
| 1 | Finish backend foundation | ✅ Done | CRUD API, Ruff green, migrations, Docker Compose |
| 2 | **Walking skeleton (agent loop)** | ✅ Done | Groq + Docker sandbox + real PR; 64 tests |
| 3 | Frontend + light auth | ✅ Done | Auth + projects + agent UI (create task, run, view diff/events, approve→PR). SSE live-streaming deferred (runs are synchronous) |
| 4 | Real GitHub integration | ✅ Done (code) | List repos/issues/tree, import issue → task pinned to (repo, branch, SHA), PR via REST with `Fixes #N`; 91 backend tests. Live end-to-end PR from an imported issue still to be demoed |
| 5 | LangGraph agent | ⬜ Not started | Durable multi-step graph + HITL |
| 6 | Repository RAG | ⬜ Not started | pgvector |
| 7 | Evaluation on SWE-bench Lite | ⬜ Not started | The resume number |
| 8 | One MCP server + Langfuse | ⬜ Not started | + prompt-injection refusal test |
| 9 | Deploy + portfolio polish | 🟡 Seed | CI workflow on origin; deploy + demo README pending |

## Backend detail (Phase 1)
- API: `GET /health`; `/api/v1/auth/{register,login,me}`; `/api/v1/projects` CRUD; `/api/v1/audit/me`.
- Auth is basic JWT (HS256). Projects are owner-scoped; auth is rate-limited; security-relevant actions are audited. (Ownership/rate-limit/audit exceed the plan's minimal auth but are kept — see [../memory.md](../memory.md).)
- Tests: 44 passing against a dedicated `devpilot_test` DB. Ruff lint + format clean. Migration chain verified drift-free on a fresh DB.

## Frontend detail (Phase 3)
- `apps/web`: Next.js 14 (App Router) + TS + Tailwind. Auth pages, project list/create + detail/edit/delete.
- **Agent UI:** `/tasks` (list + create task) and `/tasks/[id]` (Run the agent, view status badge, event timeline, proposed diff, sandbox result, and **Approve → open PR / Reject**). Post-login lands on `/tasks`.
- Typed API client (`lib/api.ts`) covers auth, projects, and agent endpoints. `npm run build`, `npm run lint`, and Vitest all green.
- Deferred: live run streaming via SSE (needs async runs); a per-task run history list.

## GitHub integration detail (Phase 4)
- `apps/api/app/integrations/github_api.py` — httpx REST client: repos, issues, resolve ref→SHA, tree, read file at SHA, create PR. Token from `GITHUB_TOKEN` (fallback `gh auth token`); `git_auth_env()` gives git the token via `GIT_CONFIG_*` env (never in URLs/args/logs).
- `apps/api/app/integrations/github_pr.py` — clone at the run's commit, apply the approved diff, push with env auth, open PR via REST (no more `gh pr create`).
- `apps/api/app/services/github.py` + `app/api/github.py` — `GET /github/repos`, `/github/repos/{o}/{n}/issues`, `/tree`; `POST /tasks/from-issue`.
- Binding (migration `deb3d64694ad`): tasks get `repo_full_name`, `base_branch`, `issue_number/title/url`; runs record the `base_commit` they ran on; approvals record `diff_sha256` + `base_commit`. PR targets the task's base branch and says `Fixes #N`.
- Safety: `target_path` must stay inside the checkout (also enforced at write time, incl. symlinks); branch names validated; `git clone --`; issue text is passed to the LLM as delimited untrusted context.
- Frontend: `components/ImportFromIssue.tsx` on `/tasks` (repo → issue → file picker from the tree at the pinned SHA → test command); manual form kept as a fallback; task detail shows repo, issue link, branch @ SHA.
- Tests: `apps/api/tests/test_github.py` (27, GitHub mocked with `httpx.MockTransport`); Vitest covers new client calls.

## Immediate next steps
1. Demo Phase 4 live: plant a new bug + open an issue on `krish1809/devpilot-demo` (its `main` is already fixed and has no open issues), import it, run, approve.
2. Begin **Phase 5 — LangGraph agent** (see PLAN.md).

## Limitations
Single-file, single-LLM-call agent; synchronous runs; no RAG, evaluation, or
deployment yet.
