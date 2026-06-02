# Frontend Overview

The frontend (`frontend/`) is a **React + Vite** single-page app with
**React Router** and plain CSS. It serves three role-based areas against the
FastAPI backend:

- **Parent portal** for linked students and approved/sent report cards.
- **Teacher portal** for assigned courses, grade entry, and course-result
  recalculation.
- **Admin area** for report review workflow, audit logs, and read-only
  management views.

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
| `/teacher` | Teacher course list | `teacher` |
| `/teacher/courses/:courseId` | Course detail, grades, results | `teacher` |
| `/admin` | Admin dashboard | `admin` |
| `/admin/reports` | Admin report-card list | `admin` |
| `/admin/reports/:reportId` | Admin report review/detail workflow | `admin` |
| `/admin/audit-logs` | Admin audit log table | `admin` |
| `/admin/students` | Read-only students list | `admin` |
| `/admin/students/:studentId` | Read-only student detail | `admin` |
| `/admin/parents` | Read-only parents list | `admin` |
| `/admin/parents/:parentId` | Read-only parent detail | `admin` |
| `/admin/teachers` | Read-only teachers list | `admin` |
| `/admin/teachers/:teacherId` | Read-only teacher detail | `admin` |
| `/admin/courses` | Read-only courses list | `admin` |
| `/admin/courses/:courseId` | Read-only course detail | `admin` |

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

## Teacher portal pages

- **TeacherCoursesPage** (`/teacher`) — lists the signed-in teacher's assigned
  courses from `GET /api/v1/courses`. Each course links to the course detail
  page.
- **TeacherCourseDetailPage** (`/teacher/courses/:id`) — loads the course,
  enrolled students, grade items, existing grades, and course results via:
  `GET /api/v1/courses/{courseId}`,
  `GET /api/v1/courses/{courseId}/students`,
  `GET /api/v1/courses/{courseId}/grade-items`,
  `GET /api/v1/courses/{courseId}/grades`, and
  `GET /api/v1/course-results/{courseId}`. `GradeEntryTable` creates or updates
  grade scores with `POST /api/v1/grades` and `PUT /api/v1/grades/{gradeId}`.
  **Recalculate results** calls
  `POST /api/v1/course-results/calculate/{courseId}` and refreshes the results
  table.

## Admin pages

- **AdminDashboardPage** (`/admin`) — landing page with links into report
  workflow and audit logs.
- **AdminReportsPage** (`/admin/reports`) — lists report cards from
  `GET /api/v1/reports`; each row links to report detail.
- **AdminReportDetailPage** (`/admin/reports/:id`) — loads a report with
  `GET /api/v1/reports/{reportId}` and supports the existing backend workflow:
  deterministic checker (`POST /api/v1/ai/check-report/{reportId}`), AI summary
  generation (`POST /api/v1/ai/generate-summary/{reportId}`), draft summary
  edit (`PUT /api/v1/reports/{reportId}/summary`), approve
  (`POST /api/v1/reports/{reportId}/approve`), send
  (`POST /api/v1/reports/{reportId}/send`), and authenticated PDF download
  (`GET /api/v1/reports/{reportId}/pdf`).
- **AuditLogsPage** (`/admin/audit-logs`) — calls
  `GET /api/v1/audit-logs` (admin only) and renders a table: time, actor,
  action, entity type, entity id, and the JSON `old_value` / `new_value`. Three
  filter inputs — **entity type**, **entity id**, **actor user id** — are
  submitted as query params (blank fields are omitted); **Clear** resets.
- **Read-only management lists** — `AdminStudentsPage`, `AdminParentsPage`,
  `AdminTeachersPage`, and `AdminCoursesPage` call
  `GET /api/v1/students`, `GET /api/v1/parents`, `GET /api/v1/teachers`, and
  `GET /api/v1/courses`. The courses page also calls
  `GET /api/v1/teachers` to display teacher names for `teacher_id`.
- **Read-only management details** — student, parent, teacher, and course detail
  pages load only existing read endpoints. Student detail shows linked parents
  and reports; parent detail shows linked students; teacher detail shows assigned
  courses; course detail shows teacher, enrolled students, grade items, and
  course results with student names where available.

The admin management list/detail pages are read-only in the frontend. CRUD
routes still exist in the backend, but these pages do not expose create, edit,
or delete controls.

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
2. **Role gate** — `parent`, `teacher`, and `admin` are accepted. Parents
   additionally load `GET /api/v1/parents/me` to obtain their `parent_id`.
3. **Landing** — parents go to `/`, teachers to `/teacher`, admins to `/admin`.
   `RequireRole` guards each area and redirects wrong-role users to their own
   home.
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

For a repeatable full-app demo, run the demo data script first:

```bash
cd backend
.venv/bin/python scripts/create_demo_data.py
```

Demo accounts created/updated by that script (password `dev-password-123`):
`demo-parent@school.test`, `demo-teacher@school.test`,
`demo-admin@school.test`.

The older `seed_data.py` script also creates basic accounts:
`parent@school.test`, `teacher@school.test`, and `admin@school.test` with the
same password, but the richer report-card demo data comes from
`backend/scripts/create_demo_data.py`.
