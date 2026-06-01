# API Routes

All routes are served under `/api/v1` (see `main.py` mount prefixes). Access
reflects the code as read from `backend/routes/*.py`:

- **Public** — no authentication.
- **Authenticated** — any valid token; the handler then applies an
  ownership/role check (described in "Access").
- **Admin / Teacher / Parent** — the named role (enforced via `require_*` or an
  in-handler check).

Report-card status lifecycle: `draft` → `approved` → `sent`. Parents may only
view report cards with status `approved` or `sent`.

There is also `GET /health` (public) for a liveness check.

## Auth — `/api/v1/auth`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| POST | `/login` | Public | Authenticate (JSON `{email,password}` or form). Returns `access_token`, `token_type`, `role`, `user_id`. |
| GET | `/me` | Authenticated | Current user `{id, name, email, role}`. |
| POST | `/logout` | Public | Stateless no-op (client discards token). |

## Users — `/api/v1/users`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `` | Admin | List users. |
| POST | `` | Admin | Create user. |
| GET | `/{user_id}` | Admin | Get a user. |
| PUT | `/{user_id}` | Admin | Update a user. |
| DELETE | `/{user_id}` | Admin | Delete a user. |

## Students — `/api/v1/students`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `` | Admin | List students. |
| POST | `` | Admin | Create student. |
| GET | `/{student_id}` | Admin, or a teacher who teaches the student | Get a student. |
| PUT | `/{student_id}` | Admin | Update a student. |
| DELETE | `/{student_id}` | Admin | Delete a student. |
| GET | `/{student_id}/parents` | Admin | List a student's linked parents. |
| POST | `/{student_id}/parents` | Admin | Link a parent to the student. |
| DELETE | `/{student_id}/parents/{parent_id}` | Admin | Unlink a parent. |

## Parents — `/api/v1/parents`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `` | Admin | List parents. |
| POST | `` | Admin | Create a parent profile for a user. |
| GET | `/me` | Parent | The signed-in parent's own profile (used by the portal to get `parent_id`). |
| GET | `/{parent_id}` | Admin, or the parent themselves | Get a parent profile. |
| PUT | `/{parent_id}` | Admin | Update a parent (phone). |
| GET | `/{parent_id}/students` | Admin, or the parent themselves | List a parent's linked students. |

## Teachers — `/api/v1/teachers`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `` | Admin | List teachers. |
| POST | `` | Admin | Create a teacher profile for a user. |
| GET | `/{teacher_id}` | Admin, or the teacher themselves | Get a teacher profile. |
| PUT | `/{teacher_id}` | Admin | Update a teacher. |
| GET | `/{teacher_id}/courses` | Admin, or the teacher themselves | List a teacher's courses. |

## Courses — `/api/v1/courses`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `` | Authenticated (admin → all; teacher → own) | List courses. |
| POST | `` | Admin | Create course. |
| GET | `/{course_id}` | Admin, or the course's teacher | Get a course. |
| PUT | `/{course_id}` | Admin | Update a course. |
| DELETE | `/{course_id}` | Admin | Delete a course. |

## Enrollments — `/api/v1`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `/courses/{course_id}/students` | Admin, or the course's teacher | List students enrolled in a course. |
| POST | `/enrollments` | Admin | Enroll a student in a course. |
| DELETE | `/enrollments/{enrollment_id}` | Admin | Remove an enrollment. |

## Grade items — `/api/v1`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `/courses/{course_id}/grade-items` | Admin, or the course's teacher | List a course's grade items. |
| POST | `/grade-items` | Admin, or the course's teacher | Create a grade item. |
| PUT | `/grade-items/{grade_item_id}` | Admin, or the course's teacher | Update a grade item. |
| DELETE | `/grade-items/{grade_item_id}` | Admin, or the course's teacher | Delete a grade item. |

## Grades — `/api/v1`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `/courses/{course_id}/grades` | Admin, or the course's teacher | List grades for a course. |
| POST | `/grades` | The course's teacher | Enter a grade (score) for an enrolled student. |
| PUT | `/grades/{grade_id}` | The course's teacher | Update a grade. |
| DELETE | `/grades/{grade_id}` | Admin | Delete a grade. |

## Course results — `/api/v1`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| POST | `/course-results/calculate/{course_id}` | Admin, or the course's teacher | Compute & store per-term course results for the course; reports skipped students. |
| GET | `/course-results/student/{student_id}` | Admin (all); teacher (only for courses they teach) | A student's course results. |
| GET | `/course-results/{course_id}` | Admin, or the course's teacher | All course results for a course. |

## Reports — `/api/v1/reports`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| POST | `/generate/{student_id}` | Admin | Generate a draft report card (builds data + PDF). |
| GET | `` | Admin | List all report cards. |
| GET | `/student/{student_id}` | Admin (all); parent (linked student, approved/sent only) | List a student's report cards. |
| PUT | `/{report_id}/review` | Admin | Review a draft (edit AI summary); audited. Draft only. |
| PUT | `/{report_id}/summary` | Admin | Update the AI summary; audited. Draft only. |
| POST | `/{report_id}/approve` | Admin | Approve a draft → `approved`; audited. |
| POST | `/{report_id}/send` | Admin | Email approved report to linked parents → `sent`; audited. |
| GET | `/{report_id}/pdf` | Admin, or parent (linked, approved/sent) | Download the report-card PDF. |
| GET | `/{report_id}` | Admin, or parent (linked, approved/sent) | Get a single report card. |

## AI — `/api/v1/ai`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| POST | `/check-report/{report_card_id}` | Admin | Run deterministic checks on a report card; stores `AIWarning`s. |
| POST | `/check-grades/{student_id}` | Admin, or a teacher who teaches the student | Check the student's latest draft report; stores warnings. |
| POST | `/generate-summary/{report_card_id}` | Admin | Generate & store an OpenAI summary for a report card. |
| POST | `/summary/{student_id}` | Admin | Generate a summary for the student's latest draft report card. |

## Audit logs — `/api/v1`

| Method | Path | Access | Purpose |
|--------|------|--------|---------|
| GET | `/audit-logs` | Admin | List audit log entries. Optional filters: `entity_type`, `entity_id` (UUID), `actor_user_id` (UUID). Ordered newest-first. |
