# Build Tickets — T-01 … T-34 (complete)

This roadmap is **reconstructed from the current implementation and git
history**. Named ticket commits exist for **T-07 – T-34** (with T-14 split across
two commits). **T-01 – T-06** are inferred from the initial foundation commit and
the current code, so those early boundaries may not match the original tracker
exactly. Every listed capability exists in the repo today.

Status: **all of T-01 – T-34 are complete.** Backend and frontend final
verification passed.

## Backend foundation

| Ticket | Title | Status | Evidence in repo |
|--------|-------|--------|------------------|
| T-01 – T-06 | Backend foundation bundle: FastAPI scaffold, requirements, database setup, SQLAlchemy models, initial Alembic migration, auth core, seed/test scaffolding | ✅ | Initial commit `Set up backend foundation`; current files `backend/main.py`, `requirements.txt`, `database.py`, `models.py`, `auth.py`, `alembic/`, `seed_data.py` |

## Core domain CRUD

| Ticket | Title | Status | Evidence |
|--------|-------|--------|----------|
| T-07 | Auth routes: login, `/me`, logout | ✅ | `routes/auth.py`; commits `T-07 add auth routes`, `T-07 cleanup support Swagger auth` |
| T-08 | Users CRUD (admin) | ✅ | `routes/users.py`; commit `T-08 add user management routes` |
| T-09 | Students routes, including student⇄parent link endpoints as implemented today | ✅ | `routes/students.py`; commit `T-09 add student routes` |
| T-10 | Parents CRUD + parent profile routes | ✅ | `routes/parents.py`; commit `T-10 add parents routes` |
| T-11 | Teachers CRUD | ✅ | `routes/teachers.py`; commit `T-11 add teacher routes` |
| T-12 | Courses CRUD | ✅ | `routes/courses.py`; commit `T-12 add course routes` |
| T-13 | Enrollments (+ course students) | ✅ | `routes/enrollments.py`; commit `T-13 add enrollment routes` |
| T-14 | Grade items routes + shared route-helper cleanup | ✅ | `routes/grade_items.py`, `utils.py`; commits `T-14 add grades item routes`, `T-14 cleanup  share route helpers` |
| T-15 | Grade submission/update/delete routes | ✅ | `routes/grades.py`; commit `T-15 add grade submission routes` |

## Grading & results

| Ticket | Title | Status | Evidence |
|--------|-------|--------|----------|
| T-16 | Grade calculator service (+ tests) | ✅ | `services/grade_calculator.py`, `tests/test_grade_calculator.py`; commit `T-16 add grade calculator service` |
| T-17 | Course result calculation and retrieval routes | ✅ | `routes/course_results.py`; commit `T-17 add course result calculations` |
| T-18 | Audit logging utility | ✅ | `backend/audit.py`; commit `T-18 add audit logging` |

## Report cards

| Ticket | Title | Status | Evidence |
|--------|-------|--------|----------|
| T-19 | Report builder service (+ tests) | ✅ | `services/report_builder.py`, `tests/test_report_builder.py` |
| T-20 | Report card HTML template | ✅ | `templates/report_card.html` |
| T-21 | PDF generator (ReportLab) (+ tests) | ✅ | `services/pdf_generator.py`, `tests/test_pdf_generator.py` |
| T-22 | Report generation route | ✅ | `routes/reports.py` (`POST /generate/{student_id}`) |
| T-23 | Report retrieval/download routes | ✅ | `routes/reports.py` (`GET /{id}`, `/{id}/pdf`, `/student/{id}`) |

## AI

| Ticket | Title | Status | Evidence |
|--------|-------|--------|----------|
| T-24 | Deterministic report checker | ✅ | `services/ai_checker.py`, `routes/ai.py` (`/check-report`); commit `T-24 add deterministic report checker` |
| T-25 | Student grade checker route | ✅ | `routes/ai.py` (`/check-grades`); commit `T-25 add student grade checker route` |
| T-26 | OpenAI AI summary service (+ tests) | ✅ | `services/ai_summary.py`, `tests/test_ai_summary.py`; commit `T-26 add AI report summary service` |
| T-27 | Student/report AI summary routes | ✅ | `routes/ai.py` (`/generate-summary`, `/summary`); commit `T-27 add student AI summary route` |

## Admin review → send (confirmed by git history)

| Ticket | Title | Status | Commit |
|--------|-------|--------|--------|
| T-28 | Report review route | ✅ | `T-28 add report review route` |
| T-29 | Audited summary edit route | ✅ | `T-29 add audited summary edit route` |
| T-30 | Report approval route | ✅ | `T-30 add report approval route` |
| T-31 | Email service | ✅ | `T-31 add email service` |
| T-32 | Report sending route | ✅ | `T-32 add report sending route` |

## Frontend

| Ticket | Title | Status | Notes |
|--------|-------|--------|-------|
| T-33 | **Parent portal frontend** | ✅ | React + Vite SPA: login, dashboard (linked students), student reports (approved/sent only), report detail, authenticated PDF download. Included a small backend prep route `GET /api/v1/parents/me` (commit `T-33 prep add current parent route`) so a parent can resolve their `parent_id`. |
| T-34 | **Admin audit log frontend** | ✅ | Role-aware auth refactor and an admin-only audit log view at `/admin/audit-logs` with `entity_type` / `entity_id` / `actor_user_id` filters over `GET /api/v1/audit-logs`. |

## Post-roadmap frontend additions

These additions exist in the current repo but are not assigned new T-xx numbers
here because this document only has confirmed ticket labels through T-34.

| Area | Status | Evidence |
|------|--------|----------|
| Teacher portal frontend | ✅ | `/teacher`, `/teacher/courses/:courseId`; `TeacherCoursesPage`, `TeacherCourseDetailPage`, `GradeEntryTable`; supports assigned courses, grade entry/update, and course-result recalculation. |
| Admin dashboard | ✅ | `/admin`; `AdminDashboardPage`; admin sidebar in `AdminLayout`. |
| Admin reports workflow frontend | ✅ | `/admin/reports`, `/admin/reports/:reportId`; report list/detail, checker, AI summary generation/editing, approval, sending, and PDF download. |
| Admin read-only management lists | ✅ | `/admin/students`, `/admin/parents`, `/admin/teachers`, `/admin/courses`; list pages link to details with `Open →`. |
| Admin read-only management details | ✅ | `/admin/students/:studentId`, `/admin/parents/:parentId`, `/admin/teachers/:teacherId`, `/admin/courses/:courseId`; related read-only data and cross-links. |
| Local demo data script | ✅ | `backend/scripts/create_demo_data.py`; creates/updates demo users, linked student, teacher, course, grades, approved report card, and PDF. |

### Notes

- Parents never see draft report cards or AI warnings (enforced by the backend
  and respected by the frontend).
- The current frontend accepts `parent`, `teacher`, and `admin` users and routes
  each role to its own guarded area.
- Admin management list/detail pages are read-only. Backend CRUD routes still
  exist, but those frontend pages do not expose create, edit, or delete controls.
