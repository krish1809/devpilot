# Deploying the DevPilot showcase

The public deployment is a **read-only showcase** (`DEMO_MODE=true`): visitors click
*View the demo* and browse real agent runs — plans, diffs, sandbox results, traces, pull
requests — and the SWE-bench Lite results, all recorded on a local machine. Starting the agent
needs Docker (the sandbox) and an LLM key, which free hosting can't provide, so agent runs stay
local. Everything below uses free tiers; no card is needed for the steps as written (check each
provider's current terms).

| Piece | Host | Notes |
|---|---|---|
| Web (Next.js) | **Vercel** (Hobby) | builds `apps/web` |
| API (FastAPI) | **Render** (free web service) | Docker image from `apps/api/Dockerfile`; sleeps when idle, ~1 min cold start |
| Database | **Neon** (free) | Postgres with the `pgvector` extension |

## 1. Neon — the database

1. Sign up at <https://neon.tech> (GitHub login is fine) and create a project, e.g. `devpilot`,
   Postgres 17, region close to you.
2. On the project dashboard, copy the **connection string** (it looks like
   `postgresql://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require`).
   Treat it as a password: don't paste it in chats or commit it.
3. Nothing else to configure: the API's migrations enable `pgvector` themselves.

## 2. Render — the API

1. Sign up at <https://render.com> with GitHub and allow access to the `devpilot` repository.
2. **New → Blueprint**, pick the `devpilot` repo. Render reads [`render.yaml`](../render.yaml)
   and proposes the `devpilot-api` web service (free plan, Docker).
3. When asked for the variables marked *sync: false*:
   - `DATABASE_URL` — the Neon connection string from step 1 (as copied; the API adapts the
     `postgresql://` prefix itself).
   - `CORS_ORIGINS` — leave as `http://localhost:3000` for now; you'll set the Vercel URL in step 4.
4. Apply. The first build takes several minutes. On start the container runs
   `alembic upgrade head` (creating all tables in Neon) and then serves.
5. Check it: open `https://<your-service>.onrender.com/health` → `{"status":"ok"}`, and
   `/api/v1/config` → `{"demo_mode":true}`.

## 3. Load the showcase data into Neon (from your machine)

The repo contains the curated export, [`deploy/showcase.json`](../deploy/showcase.json).
From `apps/api` with the virtualenv active:

```bash
DATABASE_URL='<neon connection string>' python -m scripts.showcase import ../../deploy/showcase.json
```

It prints the imported counts. It's idempotent — re-run it after refreshing the export:
`python -m scripts.showcase export --tasks 3 4 51 --evals lite-s20-seed7 lite-s20-seed7-v1-nogate`
(against your local database), commit, and import again.

## 4. Vercel — the web app

1. Sign up at <https://vercel.com> with GitHub. **Add New → Project**, import the `devpilot` repo.
2. Set **Root Directory** to `apps/web` (framework: Next.js is detected).
3. Add the environment variable `NEXT_PUBLIC_API_URL` = `https://<your-service>.onrender.com`
   (no trailing slash). Deploy.
4. Copy the site URL (e.g. `https://devpilot-xxxx.vercel.app`), then in **Render → devpilot-api →
   Environment** set `CORS_ORIGINS` to exactly that URL and save (Render redeploys).

## 5. Check the live site

Open the Vercel URL → *View the demo — no account needed*. You should see the tasks (the
weather-bug run with its plan, diff, trace and PR link), and **Benchmarks** with the SWE-bench
Lite results. If the first load is slow, that's Render waking the free service.

## Troubleshooting

- **"Could not reach the API"** in the browser: `NEXT_PUBLIC_API_URL` is wrong, or `CORS_ORIGINS`
  on Render doesn't exactly match the Vercel URL (scheme included, no trailing slash).
- **Render deploy fails at `alembic upgrade head`**: the `DATABASE_URL` is wrong or the Neon
  project is suspended (open it in the Neon console to wake it).
- **Empty pages after logging in to the demo**: step 3 wasn't run against the same database.
- Showcase mode refuses every write (403) except logging in — that's intended.
