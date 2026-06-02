# School Reports — Frontend

A React + Vite single-page app with three role-based areas:

- **Parent portal** — parents view their linked students and those students'
  approved/sent report cards, including authenticated PDF downloads.
- **Teacher portal** (`/teacher`) — teachers view assigned courses, enter/update
  grades, and recalculate course results.
- **Admin area** (`/admin`) — admins use the dashboard, report-card workflow,
  audit logs, and read-only management list/detail pages.

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

## Demo data and sign in

For the richest local demo, run the backend demo script before signing in:

```bash
cd backend
.venv/bin/python scripts/create_demo_data.py
```

Demo accounts created/updated by that script all use password
`dev-password-123`:

- **Parent** — `demo-parent@school.test` → parent portal with Demo Student's
  approved report and PDF.
- **Teacher** — `demo-teacher@school.test` → teacher portal with Demo
  Mathematics, grade entry, and course-result recalculation.
- **Admin** — `demo-admin@school.test` → admin dashboard, reports workflow,
  audit logs, and read-only management pages.

The backend `seed_data.py` script also creates basic accounts with the same
password (`parent@school.test`, `teacher@school.test`, `admin@school.test`),
but those do not provide the full approved-report demo by themselves.

After login each role lands on its own area, and the routes are role-guarded:
parents cannot reach admin or teacher pages, teachers cannot reach admin or
parent pages, and admins cannot reach parent or teacher pages.

## Build

```bash
npm run build     # outputs to dist/
npm run preview   # serve the production build locally
```

## Scope

- **Parents** see only the approved/sent reports the backend returns; drafts and
  AI warnings are never requested or displayed.
- **Teachers** can work only with their own assigned courses through the backend
  ownership checks.
- **Admins** can run the report workflow and view audit logs plus read-only
  students/parents/teachers/courses list and detail pages. The management pages
  do not expose create, edit, or delete controls.
