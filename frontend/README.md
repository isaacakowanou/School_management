# School Reports — Frontend

A small React + Vite single-page app with two role-based areas:

- **Parent portal** — parents view their linked students and those students'
  approved/sent report cards.
- **Admin audit log view** (`/admin/audit-logs`) — admins browse and filter the
  backend audit log.

## Prerequisites

- Node 18+ (developed on Node 26)
- The FastAPI backend running on `http://127.0.0.1:8000`

## Run

```bash
# 1) Start the backend (from the repo root)
cd backend
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000

# 2) In another terminal, start the frontend
cd frontend
npm install
npm run dev
```

Open the printed URL (default http://localhost:5173).

The Vite dev server proxies `/api` → `http://127.0.0.1:8000`, so no CORS
configuration is needed on the backend during development.

## Sign in

Accounts come from the backend seed data (all use password `dev-password-123`):

- **Parent** — `parent@school.test` → parent portal (linked students & reports).
- **Admin** — `admin@school.test` → audit log view at `/admin/audit-logs`.
- **Teacher** — `teacher@school.test` → rejected at login (no UI for teachers).

After login each role lands on its own area, and the routes are role-guarded:
parents cannot reach admin pages and admins cannot reach the parent portal.

## Build

```bash
npm run build     # outputs to dist/
npm run preview   # serve the production build locally
```

## Scope

- **Parents** see only the approved/sent reports the backend returns; drafts and
  AI warnings are never requested or displayed.
- **Admins** get the audit log view only — not a full admin dashboard.
- **Teachers** have no frontend and are rejected at login.
