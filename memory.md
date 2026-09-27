# DevPilot — Working Memory

**Last updated:** 2026-09-28
**Current phase:** Backend Phases 0–3 + Phase 2 frontend COMPLETE and verified. Backend: 42 tests. Frontend: builds clean + 4 vitest tests. Pushed to GitHub. Next: full-stack manual verify, then Phase 5 (AI) or Phase 13 (CI).

> Fast-moving state file for humans and coding agents: what's done, what's in flight, what's next. Update this at the end of every work session. The fuller narrative report is [docs/PROGRESS.md](docs/PROGRESS.md); phase status is in [phases.md](phases.md).

---

## ✅ Completed
- **Phase 0** — repo, Python 3.12 venv (`apps/api/.venv`), `.env.example`, docker-compose PostgreSQL 17, DB connectivity.
- **Phase 1 — backend foundation:**
  - FastAPI app + `/health` — [apps/api/app/main.py](apps/api/app/main.py)
  - Settings — [apps/api/app/core/config.py](apps/api/app/core/config.py)
  - DB base/session + `get_db` — [apps/api/app/db/](apps/api/app/db/)
  - Project model / schemas / service / router — [apps/api/app/models/project.py](apps/api/app/models/project.py), [schemas](apps/api/app/schemas/project.py), [services](apps/api/app/services/project.py), [api/projects.py](apps/api/app/api/projects.py)
  - `Annotated` DI aliases — [apps/api/app/api/deps.py](apps/api/app/api/deps.py)
  - Alembic migration `b7eb1608d21a` (projects table) — at head
  - Input validation: non-empty, ≤100-char `name`
  - **Tests: 17 passing** against dedicated `devpilot_test` DB — [apps/api/tests/](apps/api/tests/)
  - **Ruff lint + format clean**
  - **Containerized:** [apps/api/Dockerfile](apps/api/Dockerfile), [.dockerignore](apps/api/.dockerignore), compose `migrate`+`api`, [Makefile](Makefile)
  - Docs populated ([docs/](docs/)), README written, agent-steering files created (PRD/architecture/rules/phases/design/memory)
  - Initial commit `84ec564` created **locally** (not pushed)
- **Phase 3 — auth & ownership (core done):**
  - `User` model + `users` migration `8c838c6e7458`
  - `app/core/security.py` — scrypt password hashing + HS256 JWT (stdlib only)
  - `/api/v1/auth/register|login|me` — [apps/api/app/api/auth.py](apps/api/app/api/auth.py)
  - `get_current_user` / `CurrentUser` bearer dep — [apps/api/app/api/deps.py](apps/api/app/api/deps.py)
  - Projects now owner-scoped: `owner_id` FK + migration `be53ba0b8d54`; all endpoints require auth; others' projects → 404
  - Rate limiting on auth (`app/core/rate_limit.py`, in-memory sliding window → 429 + Retry-After)
  - Audit log: `audit_logs` table + migration `c1a2b3d4e5f6`; records register/login/project events; `GET /api/v1/audit/me`
  - `CLAUDE.md` added (agent entrypoint → rules.md/memory.md)
  - **Tests: 42 passing**; full migration chain verified on a throwaway DB (`alembic check` → no drift)
- **Phase 2 — frontend (`apps/web`, done + verified):**
  - Next.js 14.2.35 (App Router) + TS + Tailwind; design tokens from `design.md`
  - Auth pages, project list/create, project detail/edit/delete
  - Typed API client (`lib/api.ts`) + `AuthProvider` (`lib/auth.tsx`); loading/error/empty states
  - `npm run build` succeeds (7 routes), `npm run test` 4/4 (Vitest). node_modules/.next gitignored; package-lock.json committed
- **GitHub:** commits pushed to `origin/main` (credential.helper store primed with user's PAT — user to revoke that exposed token). Pushing after each commit going forward.

## 🟡 In progress / files being worked on
- *(none actively — clean stopping point)*
- ⚠️ **Dev DB migration pending:** dev is at `8c838c6e7458`; head is now `c1a2b3d4e5f6`. Applying `be53ba0b8d54` (owner_id NOT NULL) fails until the 2 legacy ownerless `projects` rows are cleared. Fresh deploys/CI are unaffected (verified: full chain applies clean on an empty DB with no drift). Test DB is fine (recreated each run).

## ⏭️ Next actions (in order)
1. **Clear the 2 legacy dev project rows**, then apply the migration:
   `docker exec devpilot-postgres psql -U devpilot -d devpilot -c "DELETE FROM projects;"` then `alembic upgrade head` (from `apps/api`). *(A raw delete needs your approval — the agent's attempt was blocked.)*
2. **Push** commits: `git push -u origin main` *(needs network + GitHub auth; not doable in sandbox)*.
3. **Verify Docker stack**: `make docker-up` → http://localhost:8000/docs *(image build needs Docker Hub access)*.
4. Continue Phase 3 (rate limiting, audit events) **or** start Phase 2 (frontend).

## ⚠️ Known constraints / gotchas
- Auth uses **stdlib crypto** (scrypt + HMAC HS256) because the sandbox has no network for `bcrypt`/`PyJWT`; isolated in `app/core/security.py` for easy swap. Set a strong `SECRET_KEY` in any real deploy.
- **Sandbox network:** npm registry + github.com + PyPI are reachable (npm install, git push work); Docker Hub and fonts.googleapis.com are NOT (Docker image builds and web-font fetch fail here). Raw DB row deletes are classifier-gated (need user approval).
- Do **not** repeat the earlier Alembic reset — verify DB state before any destructive migration op.
- `.env` is git-ignored and currently holds no real secrets (all keys empty).

## 🔗 Verify-before-trust checklist for agents
Before acting: `git status`, `alembic current`, and check this file's date. If a referenced file/flag isn't present, re-inspect the checkout — docs may lag.
