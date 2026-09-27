# DevPilot Web

Next.js 14 (App Router) + TypeScript + Tailwind frontend for DevPilot.
Covers authentication (register/login) and project CRUD against the API.

## Prerequisites
- Node.js 18.18+ (or 20+)
- The DevPilot API running and reachable (default `http://localhost:8000`)

## Setup

```bash
cd apps/web
cp .env.local.example .env.local   # adjust NEXT_PUBLIC_API_URL if needed
npm install
npm run dev
```

Open http://localhost:3000.

## Scripts
- `npm run dev` — start the dev server
- `npm run build` — production build
- `npm run start` — serve the production build
- `npm run lint` — ESLint (next/core-web-vitals)
- `npm run test` — Vitest unit tests

## Structure
```text
app/
  layout.tsx            # fonts, AuthProvider, Nav
  page.tsx              # redirects to /projects or /login
  login/ register/      # auth pages
  projects/             # list + create
  projects/[id]/        # detail + edit + delete
components/
  Nav.tsx
  ui/                   # button, input, card, label, spinner, alert
lib/
  api.ts                # typed fetch client + ApiError mapping
  auth.tsx              # AuthProvider / useAuth (token in localStorage)
  types.ts utils.ts
```

## Notes
- The auth token is stored in `localStorage` and sent as `Authorization: Bearer <token>`.
- Design tokens (colors, radius, fonts) live in `app/globals.css` and follow `../../design.md`; light/dark follow the OS preference.
- UI primitives are hand-rolled Tailwind components (no shadcn CLI dependency); shadcn/ui can be layered in later if desired.
