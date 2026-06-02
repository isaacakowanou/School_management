# Architecture

This document describes the structure of the School AI Grade & Report-Card
Management System. It is reconstructed from the current codebase (the repo is
the source of truth).

## High-level

- **Backend** — FastAPI application (`backend/`) exposing a JSON REST API under
  `/api/v1`, backed by SQLAlchemy + SQLite, with Alembic migrations. JWT bearer
  auth with role-based access (`admin`, `teacher`, `parent`).
- **Frontend** — React + Vite single-page app (`frontend/`) with three
  role-based areas: a **parent portal**, a **teacher portal**, and an **admin
  area** for report workflow, audit logs, and read-only management views. Talks
  to the backend through a Vite dev proxy.

```
School_management/
├── backend/        FastAPI app, services, models, migrations, tests
├── frontend/       React + Vite SPA
└── docs/           this documentation
```

## Backend structure (`backend/`)

| Path | Purpose |
|------|---------|
| `main.py` | App entry. Creates the `FastAPI` app, mounts every router under `/api/v1`, defines `GET /health`. |
| `config.py` | Loads `backend/.env` via `python-dotenv` (`override=False`). Imported for its side effect before env vars are read. |
| `database.py` | SQLAlchemy engine + `SessionLocal`, and the `get_db()` dependency. Reads `DATABASE_URL` (defaults to `sqlite:///./school_ai.db`). |
| `auth.py` | Auth core: password hashing (`passlib`/bcrypt), JWT encode/decode (`python-jose`), `get_current_user`, and `require_role` → `require_admin` / `require_teacher` / `require_parent`. |
| `models.py` | All SQLAlchemy ORM models (the database schema). See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md). |
| `schemas.py` | Pydantic request/response models (e.g. `UserResponse`, `ReportCardResponse`, `AuditLogResponse`). |
| `audit.py` | `create_audit_log(...)` helper + a `_json_safe` serializer; writes `AuditLog` rows for audited grade, course-result, and report-card actions. |
| `utils.py` | Shared helpers: `get_report_card_or_404`, `get_current_teacher`, `to_student_response`, `to_course_response`. |
| `seed_data.py` | Idempotent dev seed (admin/teacher/parent users, a course, grade items, students, enrollments). |
| `scripts/create_demo_data.py` | Idempotent local demo setup for the finished app: demo users, linked student, course, grades, approved report card, and PDF. |
| `routes/` | One router module per resource (see below). |
| `services/` | Business logic separated from HTTP (see below). |
| `templates/` | `report_card.html` — Jinja2 template used when rendering report-card PDFs. |
| `tests/` | `unittest` suite for services and parent routes. |
| `alembic/` | Migration environment; `versions/ba9dbad0d63e_create_initial_tables.py` creates all tables. |

### `routes/`

Each module defines an `APIRouter`; `main.py` mounts them with a prefix. Routes
combine FastAPI dependencies for auth (`require_admin`, `get_current_user`, …)
with per-resource access-control helpers. Full list in
[API_ROUTES.md](API_ROUTES.md).

- `auth.py` — login, current user (`/me`), logout.
- `users.py` — user CRUD (admin only).
- `students.py` — student CRUD and student⇄parent links.
- `parents.py` — parent CRUD, `GET /parents/me`, and a parent's linked students.
- `teachers.py` — teacher CRUD and a teacher's courses.
- `courses.py` — course CRUD.
- `enrollments.py` — enrollments and a course's enrolled students.
- `grade_items.py` — grade-item CRUD (graded components within a course).
- `grades.py` — grade (score) CRUD.
- `course_results.py` — calculate and read per-course term results.
- `reports.py` — report-card generation, review, approval, sending, retrieval, PDF download.
- `ai.py` — deterministic checks and OpenAI summary generation.
- `audit_logs.py` — read the audit log (admin only).

### `services/`

Pure-ish business logic, unit-tested independently of HTTP:

- `grade_calculator.py` — deterministic calculations: weighted course average,
  overall average, GPA, and letter grade (weights must sum to ≈1.0).
- `report_builder.py` — `build_report_card_data(...)` assembles a student's
  course results into report-card data (overall average + GPA).
- `pdf_generator.py` — renders the report card to a PDF using the Jinja2
  template + ReportLab; writes files under `storage/pdfs/`.
- `ai_checker.py` — rule-based checks that produce structured warnings
  (e.g. weight totals, missing data). Deterministic, no external calls.
- `ai_summary.py` — natural-language report summary via the OpenAI API
  (default model `gpt-4o-mini`; requires `OPENAI_API_KEY`).
- `email_service.py` — sends report-ready notifications to a student's linked
  parents over SMTP.

### Auth & roles

JWTs are issued at login with the user's id (`sub`) and `role`. `get_current_user`
decodes the token and loads the `User`. `require_role(...)` enforces a specific
role; many read endpoints instead use `get_current_user` plus an ownership check
(e.g. a teacher may only read their own courses; a parent only their own data).

## Frontend structure (`frontend/src/`)

| Path | Purpose |
|------|---------|
| `main.jsx` | Mounts the app inside `BrowserRouter` + `AuthProvider`. |
| `App.jsx` | Route table; wraps areas in `RequireRole`. |
| `api/` | `client.js` (fetch wrapper: base URL, bearer token, error + 401 handling, blob download), plus resource wrappers for auth, parents, students, teachers, courses, grade items, grades, course results, reports, AI actions, and audit logs. |
| `auth/AuthContext.jsx` | Auth state + `login`/`logout`/bootstrap. Allows `parent`, `teacher`, and `admin`. Parents additionally load their `Parent` row. Exposes `user`, `role`, `parentId`, `homePath`. |
| `auth/RequireRole.jsx` | Route guard: requires auth and (optionally) an exact role; sends wrong-role users to their own home. |
| `pages/` | Parent pages (`DashboardPage`, `StudentReportsPage`, `ReportDetailPage`), teacher pages (`TeacherCoursesPage`, `TeacherCourseDetailPage`), admin pages (`AdminDashboardPage`, `AdminReportsPage`, `AdminReportDetailPage`, `AuditLogsPage`, read-only list/detail pages for students, parents, teachers, courses), and `LoginPage`. |
| `components/` | `Layout` (top bar + outlet), `AdminLayout` (admin sidebar + outlet), `GradeEntryTable`, `Spinner`, `ErrorBanner`, `Empty`, `StatusBadge`. |
| `utils/` | `format.js` (percent/GPA formatting), `roles.js` (`homePathForRole`, `isPathForRole`). |
| `styles/index.css` | Plain CSS for the whole app. |
| `vite.config.js` | Dev server config; proxies `/api` → `http://127.0.0.1:8000`. |

See [FRONTEND_OVERVIEW.md](FRONTEND_OVERVIEW.md) for pages, auth flow, and the proxy.

### Auth context & role guards

`AuthContext` stores the JWT in `localStorage` and, after login (or on a page
refresh), verifies the account via `GET /auth/me`. The frontend accepts
`parent`, `teacher`, and `admin`; parents additionally load their `Parent` row
via `GET /parents/me` for the `parentId`. `RequireRole` gates each route subtree
and redirects wrong-role or unauthenticated users.

### Frontend areas

- **Parent portal** (`/`, `/students/:id/reports`, `/reports/:id`) — linked
  students and their **approved/sent** report cards only; drafts and AI warnings
  are never requested.
- **Teacher portal** (`/teacher`, `/teacher/courses/:id`) — teacher's assigned
  courses, enrolled students, grade items, grade entry/update, and course-result
  recalculation.
- **Admin area** (`/admin/*`) — dashboard, report list/detail workflow
  (checker, AI summary generation/editing, approval, sending, PDF download),
  audit logs with filters, read-only students/parents/teachers/courses list
  pages, and read-only detail pages for those resources.
