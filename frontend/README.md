# Parent Portal (T-33)

A small React + Vite single-page app for parents to view their children's
approved/sent report cards.

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

Use a **parent** account from the backend seed data:

- Email: `parent@school.test`
- Password: `dev-password-123`

Non-parent accounts (admin/teacher) are rejected after login.

## Build

```bash
npm run build     # outputs to dist/
npm run preview   # serve the production build locally
```

## Scope

Parent portal only — no admin or teacher UI. Parents see only the
approved/sent reports the backend returns; drafts and AI warnings are never
requested or displayed.
