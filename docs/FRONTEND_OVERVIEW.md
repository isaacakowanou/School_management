# Frontend Overview

The frontend (`frontend/`) is a **React + Vite** single-page app with
**React Router** and plain CSS. It serves two role-based areas — a **parent
portal** and an **admin audit log view** — against the FastAPI backend.

## Stack & layout

- React 18, React Router 6, Vite 5, plain CSS. JWT stored in `localStorage`.
- Source lives in `frontend/src/` (see [ARCHITECTURE.md](ARCHITECTURE.md) for the
  file-by-file breakdown).

## Routes

| Path | Area | Guard |
|------|------|-------|
| `/login` | Sign in | Public |
| `/` | Parent dashboard (linked students) | `parent` |
| `/students/:studentId/reports` | A student's approved/sent reports | `parent` |
| `/reports/:reportId` | Report detail + PDF download | `parent` |
| `/admin/audit-logs` | Admin audit log table | `admin` |

Unknown paths redirect to `/` (which then routes each role to its own home).

## Parent portal pages

- **LoginPage** — email/password form. On success, role is verified and the
  user lands on their area's home.
- **DashboardPage** (`/`) — greets the parent and lists their linked students
  (`GET /api/v1/parents/{parentId}/students`). Each card links to that student's
  reports.
- **StudentReportsPage** (`/students/:id/reports`) — lists the student's report
  cards from `GET /api/v1/reports/student/{studentId}`. The backend returns only
  `approved`/`sent` reports to parents, so drafts never appear. Shows a status
  badge per report.
- **ReportDetailPage** (`/reports/:id`) — `GET /api/v1/reports/{reportId}` and
  renders student info, term, school year, the course results table, overall
  average, GPA, and the summary (only when present, under a neutral "Summary"
  heading). The **Download PDF** button fetches `GET /api/v1/reports/{id}/pdf`
  with the bearer token as a blob and saves it (a plain link can't send the auth
  header). AI warnings are never requested or shown.

## Admin audit log page

- **AuditLogsPage** (`/admin/audit-logs`) — calls
  `GET /api/v1/audit-logs` (admin only) and renders a table: time, actor, action,
  entity type, entity id, and the JSON `old_value` / `new_value`. Three filter
  inputs — **entity type**, **entity id**, **actor user id** — are submitted as
  query params (blank fields are omitted); **Clear** resets. Loading, error, and
  empty states are handled. No other admin UI exists.

## Vite dev proxy

`vite.config.js` proxies `/api` → `http://127.0.0.1:8000`:

```js
server: { proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } } }
```

The browser only ever talks to its own origin (`localhost:5173`), so the backend
needs no CORS configuration in development. For production, serve the built
assets behind the same origin / a reverse proxy (or add CORS to the backend).

## Auth flow

1. **Login** — `POST /api/v1/auth/login` returns a JWT, which is stored in
   `localStorage`. The app then calls `GET /api/v1/auth/me` to read the
   authoritative role.
2. **Role gate** — only `parent` and `admin` are accepted; any other role
   (e.g. `teacher`) is rejected and the token is discarded. Parents additionally
   load `GET /api/v1/parents/me` to obtain their `parent_id`.
3. **Landing** — parents go to `/`, admins to `/admin/audit-logs`. `RequireRole`
   guards each area and redirects wrong-role users to their own home.
4. **Refresh / deep links** — on load, if a token exists, the same verification
   runs (`/auth/me`, plus `/parents/me` for parents) so sessions survive a page
   reload.
5. **Token use & expiry** — every API call sends `Authorization: Bearer <token>`.
   Any `401` from an authenticated request clears the token and returns the user
   to `/login`. **Logout** clears the stored token (the backend `/auth/logout`
   is a stateless no-op).

## Run

```bash
# backend
cd backend && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Seed accounts (password `dev-password-123`): `parent@school.test` (portal),
`admin@school.test` (audit logs), `teacher@school.test` (rejected at login).
