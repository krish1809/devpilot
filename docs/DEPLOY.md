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
   - `FRONTEND_URL` — the Vercel URL (reset links point here); set it after step 4 if you
     don't know it yet.
   - `EMAIL_FROM`, `RESEND_API_KEY`, `BOOTSTRAP_USER_EMAIL` — see "Password reset email" below
     (optional: without them the showcase works, but reset emails aren't sent).
4. Apply. The first build takes several minutes. On start the container runs
   `alembic upgrade head` (creating all tables in Neon), loads the showcase data (step 3), and
   then serves.
5. Check it: open `https://<your-service>.onrender.com/health` → `{"status":"ok"}`, and
   `/api/v1/config` → `{"demo_mode":true}`.

## 3. Showcase data — loads itself

The repo contains the curated export, [`apps/api/showcase/showcase.json`](../apps/api/showcase/showcase.json),
and it ships inside the API image. On every start, in `DEMO_MODE` only, the container runs
`python -m scripts.showcase autoload`: it imports the bundled file under the read-only demo user
if its content changed since the last import (the file's SHA-256 is kept in the `app_state`
table), and otherwise does nothing. It never blocks startup — a failure is logged and the API
serves anyway. So the first deploy fills Neon by itself, and **refreshing the showcase is just a
commit**: export, commit, push → Render redeploys (the file is under `apps/api/`) → the new data
is loaded on start. No database credentials need to leave Render.

To refresh the export from your local database (from `apps/api`, virtualenv active):

```bash
python -m scripts.showcase export --tasks 3 4 51 --evals lite-s20-seed7 lite-s20-seed7-v1-nogate
```

The SWE-bench pipeline does this automatically when a benchmark run completes
([eval/README.md](eval/README.md)).

⚠️ Never set `DEMO_MODE=true` against your development database: the import replaces the demo
user's tasks and any benchmark runs with the same names.

A manual import is still possible (e.g. to a different database). Use a hidden prompt so the
password stays off the screen and out of shell history, and so the `&` in Neon's URL can't split
the command (which would run the import against your *local* database):

```bash
read -rs DATABASE_URL && export DATABASE_URL   # paste the string, press Enter (input is hidden)
python -m scripts.showcase import showcase/showcase.json
unset DATABASE_URL
```

## 4. Vercel — the web app

1. Sign up at <https://vercel.com> with GitHub. **Add New → Project**, import the `devpilot` repo.
2. Set **Root Directory** to `apps/web` (framework: Next.js is detected).
3. Add the environment variable `NEXT_PUBLIC_API_URL` = `https://<your-service>.onrender.com`
   (no trailing slash). Deploy.
4. Copy the site URL (e.g. `https://devpilot-xxxx.vercel.app`), then in **Render → devpilot-api →
   Environment** set `CORS_ORIGINS` to exactly that URL and save (Render redeploys).

## Password reset email (optional)

The API sends reset links through [Resend](https://resend.com) over HTTPS (Render's free
plan blocks outbound SMTP). Free tier at the time of writing: ~3,000 emails/month — check
current limits.

1. Sign up at Resend and create an API key with **Sending access** only.
2. Without a verified domain, Resend only sends *from* `onboarding@resend.dev` *to the
   address you signed up with* — enough for the owner's own account. (To email anyone,
   verify a domain you own and use an address on it in `EMAIL_FROM`.)
3. In **Render → devpilot-api → Environment** set:
   `EMAIL_BACKEND=resend`, `EMAIL_FROM=DevPilot <onboarding@resend.dev>`,
   `RESEND_API_KEY=<key>`, `FRONTEND_URL=https://<your-site>.vercel.app`,
   `FORWARDED_ALLOW_IPS=*`, and `BOOTSTRAP_USER_EMAIL=<your Resend sign-up email>`.
4. After the redeploy, open the site → *Log in* → *Forgot password?* → your email. Set a
   password from the link; you can now log in as yourself (read-only, like every showcase
   session). Showcase mode allows only the two reset endpoints besides login.

If `EMAIL_BACKEND` is left as `console` in production, no email is sent and nothing is
printed — the API logs a warning instead.

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
