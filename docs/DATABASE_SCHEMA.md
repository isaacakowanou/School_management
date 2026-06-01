# Database Schema

All models are defined in [`backend/models.py`](../backend/models.py) using
SQLAlchemy's declarative `Base`. The database is SQLite by default
(`sqlite:///./school_ai.db`); all tables are created by the single Alembic
migration `ba9dbad0d63e_create_initial_tables.py`.

Conventions: every table uses a UUID primary key (`id`). Timestamp columns are
listed per table below; most primary domain tables carry `created_at` /
`updated_at` server-default timestamps.

## Tables

### `users`
Application accounts for all roles.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | str(255) | |
| email | str(255) | unique, indexed |
| password_hash | str(255) | bcrypt hash |
| role | str(20) | `admin` \| `teacher` \| `parent` |
| created_at / updated_at | datetime | |

Relationships: optional `parent_profile` (Parent) and `teacher_profile`
(Teacher); `approved_report_cards` (report cards this admin approved);
`audit_logs` (actions this user performed).

### `students`
A student record (independent of any user account).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| first_name / last_name | str(100) | |
| grade_level | str(50) | |
| student_number | str(50) | unique, indexed |
| created_at / updated_at | datetime | |

Relationships: `parent_links` (StudentParent), `enrollments`, `grades`,
`course_results`, `report_cards`.

### `parents`
Parent profile, one-to-one with a `users` row (role `parent`).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK→users, unique |
| phone | str(30) | nullable |
| created_at / updated_at | datetime | |

Relationships: `user`; `student_links` (StudentParent).

### `student_parents`
Many-to-many link between students and parents.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| student_id | UUID | FK→students |
| parent_id | UUID | FK→parents |
| relationship | str(50) | nullable, e.g. "Guardian" |

Unique constraint: `(student_id, parent_id)`.

### `teachers`
Teacher profile, one-to-one with a `users` row (role `teacher`).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK→users, unique |
| employee_number | str(50) | unique, indexed |
| created_at / updated_at | datetime | |

Relationships: `user`; `courses`; `submitted_grades` (grades they entered).

### `courses`
A course taught by one teacher in a term/year.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | str(200) | |
| code | str(50) | unique, indexed |
| teacher_id | UUID | FK→teachers |
| grade_level | str(50) | |
| term | str(50) | |
| school_year | str(20) | |
| created_at / updated_at | datetime | |

Relationships: `teacher`; `enrollments`; `grade_items`; `course_results`;
`report_card_courses`.

### `enrollments`
A student's enrollment in a course.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| student_id | UUID | FK→students |
| course_id | UUID | FK→courses |
| created_at | datetime | |

Unique constraint: `(student_id, course_id)`.

### `grade_items`
A graded component within a course (e.g. Homework, Midterm, Final).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| course_id | UUID | FK→courses |
| title | str(200) | |
| category | str(100) | |
| max_score | float | |
| weight | float | fraction of course grade |
| term | str(50) | |
| due_date | date | nullable |
| created_at / updated_at | datetime | |

Relationships: `course`; `grades`.

### `grades`
A student's score on one grade item.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| student_id | UUID | FK→students |
| grade_item_id | UUID | FK→grade_items |
| score | float | |
| submitted_by_teacher_id | UUID | FK→teachers |
| created_at / updated_at | datetime | |

Unique constraint: `(student_id, grade_item_id)`.

### `course_results`
A computed per-term result for a student in a course.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| student_id | UUID | FK→students |
| course_id | UUID | FK→courses |
| term | str(50) | |
| average | float | weighted course average |
| letter_grade | str(5) | |
| calculated_at | datetime | |

Unique constraint: `(student_id, course_id, term)`.

### `report_cards`
A generated report card for a student/term, with a review lifecycle.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| student_id | UUID | FK→students |
| term | str(50) | |
| school_year | str(20) | |
| overall_average | float | |
| gpa | float | nullable |
| status | str(20) | `draft` → `approved` → `sent` (default `draft`) |
| ai_summary | text | nullable |
| pdf_url | str(500) | nullable; server path to generated PDF |
| approved_by_admin_id | UUID | FK→users, nullable |
| approved_at | datetime | nullable |
| sent_at | datetime | nullable |
| created_at / updated_at | datetime | |

Relationships: `student`; `approved_by_admin` (User); `courses`
(ReportCardCourse); `ai_warnings` (AIWarning). Parents may only see report cards
with status `approved` or `sent`.

### `report_card_courses`
A per-course line on a report card (denormalized snapshot at generation time).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| report_card_id | UUID | FK→report_cards |
| course_id | UUID | FK→courses |
| course_name | str(200) | snapshot |
| average | float | |
| letter_grade | str(5) | |

### `ai_warnings`
Warnings produced by the deterministic AI checker for a report card. (Admin/teacher
facing only — never exposed to parents.)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| report_card_id | UUID | FK→report_cards |
| warning_type | str(100) | |
| message | text | |
| severity | str(20) | |
| created_at | datetime | |

### `audit_logs`
Immutable record of audited grade, course-result, and report-card actions.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| actor_user_id | UUID | FK→users |
| action | str(100) | e.g. `grade_submitted`, `course_results_calculated`, `summary_edited`, `report_approved`, `report_sent` |
| entity_type | str(100) | e.g. `grade`, `course`, `report_card` |
| entity_id | UUID | id of the affected entity |
| old_value | JSON | nullable |
| new_value | JSON | nullable |
| created_at | datetime | |

## Relationship summary

- `User` 1–1 `Parent` / `Teacher` (by role).
- `Student` *–* `Parent` via `StudentParent`.
- `Teacher` 1–* `Course`; `Student` *–* `Course` via `Enrollment`.
- `Course` 1–* `GradeItem` 1–* `Grade` (*–1 `Student`, *–1 `Teacher`).
- `(Student, Course, term)` → one `CourseResult`.
- `ReportCard` 1–* `ReportCardCourse`, 1–* `AIWarning`; approved by a `User` (admin).
- `AuditLog` *–1 `User` (actor).
