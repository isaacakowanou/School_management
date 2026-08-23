"""Unified Corbeille listing, restore, retention, and permanent purge logic.

The bin deliberately merges two existing sources: recoverable
``DeletionBatch`` bundles created by Nettoyage and unbatched rows whose
``deleted_at`` is set without a batch id. Reading both avoided migrating old
soft-deletes or rewriting the already-working batch restore path; entity pages
such as deleted students are filters over this same service.

Unbatched child restoration validates that required parents are active, because
restoring an orphan would make normal routes inconsistent. Permanent purge is
flush-explicit and FK-safe child-first, restricted to IDs in the selected
deleted entry's ownership closure, and wrapped in a nested transaction per
entry. Closure never follows shared references into unrelated live entities:
student purges stop at courses/classes/teachers/parents, course purges stop at
students/teachers/classes/subjects/reports, and report purges stop at
students/courses. Parent and teacher profile purges include their one-to-one
``User`` account and reset tokens; audit history is retained with actor
references nulled. Purged entries have no recovery path.
Retention is 30 days from ``deleted_at``; restore clears that clock, and a later
deletion starts a fresh window. Cleanup is lazy on Corbeille access because the
app has no scheduler (FastAPI BackgroundTasks are request-bound); indexed
``deleted_at`` columns keep the sweep bounded.

Parent/teacher restore also restores the linked login account only after its
email (and teacher employee number) passes active-identity conflict checks.
Restore never rewinds ``token_version``, so sessions issued before deletion
remain invalid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from services.account_lifecycle import restore_profile_accounts
from models import (
    AIWarning,
    AuditLog,
    Class,
    Course,
    CourseResult,
    DeletionBatch,
    Enrollment,
    Grade,
    GradeItem,
    Parent,
    PasswordResetToken,
    PdfJob,
    ReportCard,
    ReportCardCourse,
    ReportConductItem,
    ReportWorkHabitItem,
    Student,
    StudentClassAssignment,
    StudentParent,
    StudentPassageDecision,
    Subject,
    Teacher,
    User,
)


RETENTION_DAYS = 30


RECOVERABLE_MODELS = {
    "classes": Class,
    "students": Student,
    "parents": Parent,
    "student_parents": StudentParent,
    "teachers": Teacher,
    "subjects": Subject,
    "courses": Course,
    "enrollments": Enrollment,
    "grade_items": GradeItem,
    "grades": Grade,
    "course_results": CourseResult,
    "report_cards": ReportCard,
    "report_card_courses": ReportCardCourse,
    "report_conduct_items": ReportConductItem,
    "report_work_habit_items": ReportWorkHabitItem,
    "ai_warnings": AIWarning,
}

# Hard-purge-only children do not appear independently in Corbeille and cannot
# be restored, but their non-nullable ownership FKs must participate in purge.
PURGE_ONLY_MODELS = {
    "pdf_jobs": PdfJob,
    "student_class_assignments": StudentClassAssignment,
    "student_passage_decisions": StudentPassageDecision,
}
PURGE_MODELS = {**RECOVERABLE_MODELS, **PURGE_ONLY_MODELS}

PURGE_ORDER = [
    "ai_warnings",
    "report_work_habit_items",
    "report_conduct_items",
    "report_card_courses",
    "report_cards",
    "course_results",
    "grades",
    "grade_items",
    "enrollments",
    "student_parents",
    "student_class_assignments",
    "student_passage_decisions",
    "courses",
    "students",
    "parents",
    "teachers",
    "pdf_jobs",
    "classes",
    "subjects",
    "users",
]

ROW_ENTRY_PREFIX = "row:"
BATCH_ENTRY_PREFIX = "batch:"


@dataclass
class TrashEntry:
    id: str
    source: str
    entity_type: str
    entity_id: UUID
    target_label: str
    deleted_at: datetime
    counts: dict[str, int]
    metadata: dict[str, str | None] | None = None
    restored_at: datetime | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _display_deleted_at(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _row_entry_id(table: str, entity_id: UUID) -> str:
    return f"{ROW_ENTRY_PREFIX}{table}:{entity_id}"


def _batch_entry_id(batch_id: UUID) -> str:
    return f"{BATCH_ENTRY_PREFIX}{batch_id}"


def parse_entry_id(entry_id: str) -> tuple[str, str | None, UUID]:
    if entry_id.startswith(BATCH_ENTRY_PREFIX):
        return "batch", None, UUID(entry_id.removeprefix(BATCH_ENTRY_PREFIX))
    if entry_id.startswith(ROW_ENTRY_PREFIX):
        rest = entry_id.removeprefix(ROW_ENTRY_PREFIX)
        table, raw_id = rest.rsplit(":", 1)
        if table not in RECOVERABLE_MODELS:
            raise ValueError
        return "row", table, UUID(raw_id)
    raise ValueError


def _user_label(user: User | None) -> str:
    if user is None:
        return "Unknown user"
    return user.name if user.email is None else f"{user.name} ({user.email})"


def row_label(row) -> str:
    if isinstance(row, Student):
        return f"{row.first_name} {row.last_name} #{row.student_number}"
    if isinstance(row, Parent):
        return _user_label(row.user)
    if isinstance(row, Teacher):
        return f"{_user_label(row.user)} #{row.employee_number}"
    if isinstance(row, Class):
        return f"{row.name_fr} {row.school_year}"
    if isinstance(row, Subject):
        return f"{row.name_fr} / {row.name_en}"
    if isinstance(row, Course):
        return f"{row.name} ({row.code})"
    if isinstance(row, Enrollment):
        return f"Enrollment {row.student_id} -> {row.course_id}"
    if isinstance(row, GradeItem):
        return f"{row.title} ({row.course.name if row.course else row.course_id})"
    if isinstance(row, Grade):
        return f"Grade {row.score:g}"
    if isinstance(row, CourseResult):
        return f"Result {row.term}"
    if isinstance(row, ReportCard):
        student = row.student
        student_name = f"{student.first_name} {student.last_name}" if student is not None else str(row.student_id)
        return f"{student_name} · {row.term} · {row.school_year}"
    if isinstance(row, ReportCardCourse):
        return row.course_name
    if isinstance(row, (ReportConductItem, ReportWorkHabitItem)):
        return row.item_key
    if isinstance(row, AIWarning):
        return row.warning_type
    return str(row.id)


def row_metadata(row) -> dict[str, str | None]:
    if isinstance(row, Student):
        return {
            "student_number": row.student_number,
            "class_name": row.school_class.name_fr if row.school_class is not None else None,
        }
    if isinstance(row, Course):
        return {"code": row.code, "school_year": row.school_year, "term": row.term}
    if isinstance(row, Subject):
        return {"section": row.section, "level_group": row.level_group}
    return {}


def _entity_type_for_table(table: str) -> str:
    return {
        "classes": "class",
        "students": "student",
        "parents": "parent",
        "student_parents": "student_parent_link",
        "teachers": "teacher",
        "subjects": "subject",
        "courses": "course",
        "enrollments": "enrollment",
        "grade_items": "grade_item",
        "grades": "grade",
        "course_results": "course_result",
        "report_cards": "report",
        "report_card_courses": "report_course",
        "report_conduct_items": "report_conduct",
        "report_work_habit_items": "report_work_habit",
        "ai_warnings": "ai_warning",
    }[table]


def _deleted_rows_query(table: str, model):
    query = select(model).where(model.deleted_at.is_not(None), model.deleted_batch_id.is_(None))
    if table == "students":
        query = query.options(joinedload(Student.school_class))
    elif table in {"parents", "teachers"}:
        query = query.options(joinedload(model.user))
    elif table == "grade_items":
        query = query.options(joinedload(GradeItem.course))
    elif table == "report_cards":
        query = query.options(joinedload(ReportCard.student))
    return query.order_by(model.deleted_at.desc())


def list_trash_entries(db: Session, *, entity_type: str | None = None) -> list[TrashEntry]:
    # Do not collapse this into one source unless historical soft-deletes are
    # migrated first: batch rows and standalone deleted rows have different,
    # already-proven restore semantics but intentionally share one UI/API.
    entries: list[TrashEntry] = []
    batches = db.scalars(
        select(DeletionBatch)
        .where(DeletionBatch.restored_at.is_(None))
        .order_by(DeletionBatch.deleted_at.desc())
    ).all()
    for batch in batches:
        if entity_type is not None and batch.entity_type != entity_type:
            continue
        entries.append(
            TrashEntry(
                id=_batch_entry_id(batch.id),
                source="batch",
                entity_type=batch.entity_type,
                entity_id=batch.entity_id,
                target_label=batch.target_label,
                deleted_at=_display_deleted_at(batch.deleted_at),
                counts=batch.counts_json or {},
                restored_at=batch.restored_at,
            )
        )

    for table, model in RECOVERABLE_MODELS.items():
        row_entity_type = _entity_type_for_table(table)
        if entity_type is not None and row_entity_type != entity_type:
            continue
        rows = db.scalars(_deleted_rows_query(table, model)).all()
        for row in rows:
            entries.append(
                TrashEntry(
                    id=_row_entry_id(table, row.id),
                    source="row",
                    entity_type=row_entity_type,
                    entity_id=row.id,
                    target_label=row_label(row),
                    deleted_at=_display_deleted_at(row.deleted_at),
                    counts={table: 1},
                    metadata=row_metadata(row),
                )
            )

    entries.sort(key=lambda item: item.deleted_at, reverse=True)
    return entries


def trash_summary(entries: list[TrashEntry]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for entry in entries:
        summary[entry.entity_type] = summary.get(entry.entity_type, 0) + 1
    return summary


def _parent_deleted(parent, parent_table: str, parent_label: str) -> bool:
    if parent is None:
        return True
    return getattr(parent, "deleted_at", None) is not None


def _restore_conflict(parent_label: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "restore_parent_deleted",
            "message": f"Restore {parent_label} first.",
            "parent": parent_label,
        },
    )


def _validate_course_setup_restore_conflict(db: Session, row) -> None:
    if not isinstance(row, Course) or row.class_id is None or row.subject_id is None:
        return
    duplicate = db.scalar(
        select(Course.id).where(
            Course.school_year == row.school_year,
            Course.class_id == row.class_id,
            Course.subject_id == row.subject_id,
            Course.deleted_at.is_(None),
            Course.id != row.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "restore_course_setup_conflict",
                "message": "An active course already uses this class and subject for the school year",
            },
        )


def validate_restore_dependencies(db: Session, row) -> None:
    # A soft-deleted child may be individually visible in Corbeille even while
    # its parent remains deleted. Returning 409 preserves referential meaning
    # and tells the admin to restore the ownership chain first.
    if isinstance(row, Student) and row.school_class is not None and row.school_class.deleted_at is not None:
        _restore_conflict("class")
    if isinstance(row, Course):
        if _parent_deleted(row.teacher, "teachers", "teacher"):
            _restore_conflict("teacher")
        if row.school_class is not None and row.school_class.deleted_at is not None:
            _restore_conflict("class")
        if row.subject is not None and row.subject.deleted_at is not None:
            _restore_conflict("subject")
        _validate_course_setup_restore_conflict(db, row)
    if isinstance(row, Enrollment):
        if _parent_deleted(row.student, "students", "student"):
            _restore_conflict("student")
        if _parent_deleted(row.course, "courses", "course"):
            _restore_conflict("course")
    if isinstance(row, GradeItem) and _parent_deleted(row.course, "courses", "course"):
        _restore_conflict("course")
    if isinstance(row, Grade):
        if _parent_deleted(row.student, "students", "student"):
            _restore_conflict("student")
        if _parent_deleted(row.grade_item, "grade_items", "grade item"):
            _restore_conflict("grade item")
        if _parent_deleted(row.submitted_by_teacher, "teachers", "teacher"):
            _restore_conflict("teacher")
    if isinstance(row, CourseResult):
        if _parent_deleted(row.student, "students", "student"):
            _restore_conflict("student")
        if _parent_deleted(row.course, "courses", "course"):
            _restore_conflict("course")
    if isinstance(row, ReportCard) and _parent_deleted(row.student, "students", "student"):
        _restore_conflict("student")
    if isinstance(row, ReportCardCourse):
        if _parent_deleted(row.report_card, "report_cards", "report"):
            _restore_conflict("report")
        if _parent_deleted(row.course, "courses", "course"):
            _restore_conflict("course")
    if isinstance(row, (ReportConductItem, ReportWorkHabitItem, AIWarning)):
        if _parent_deleted(row.report_card, "report_cards", "report"):
            _restore_conflict("report")


def restore_row_entry(db: Session, *, table: str, entity_id: UUID, current_user: User) -> str:
    model = RECOVERABLE_MODELS[table]
    row = db.get(model, entity_id)
    if row is None or row.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found")
    validate_restore_dependencies(db, row)
    if isinstance(row, (Parent, Teacher)):
        restore_profile_accounts(db, [row])
    old_deleted_at = row.deleted_at
    row.deleted_at = None
    row.deleted_batch_id = None
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="trash_restored",
        entity_type=_entity_type_for_table(table),
        entity_id=row.id,
        old_value={"deleted_at": old_deleted_at},
        new_value={"deleted_at": None},
    )
    return row_label(row)


def restore_batch_entry(db: Session, *, batch_id: UUID, current_user: User) -> tuple[str, dict[str, int]]:
    batch = db.get(DeletionBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found")
    if batch.restored_at is not None:
        return batch.target_label, {}

    rows_by_table: dict[str, list] = {}
    for table, model in RECOVERABLE_MODELS.items():
        rows = db.scalars(select(model).where(model.deleted_batch_id == batch_id)).all()
        if not rows:
            continue
        rows_by_table[table] = rows

    # Batch-owned parent/child rows are restored together, so single-row parent
    # guards do not apply. Only check conflicts against live course setup.
    for course in rows_by_table.get("courses", []):
        _validate_course_setup_restore_conflict(db, course)

    profiles = [
        row
        for rows in rows_by_table.values()
        for row in rows
        if isinstance(row, (Parent, Teacher))
    ]
    restore_profile_accounts(db, profiles)

    restored_counts: dict[str, int] = {}
    for table, rows in rows_by_table.items():
        for row in rows:
            row.deleted_at = None
            row.deleted_batch_id = None
        restored_counts[table] = len(rows)
    batch.restored_at = _now()
    batch.restored_by_user_id = current_user.id
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="danger_zone_restored",
        entity_type=batch.entity_type,
        entity_id=batch.entity_id,
        old_value={"batch_id": batch.id, "target_label": batch.target_label},
        new_value={"restored_counts": restored_counts},
    )
    return batch.target_label, restored_counts


def _add_ids(plan: dict[str, set[UUID]], table: str, ids) -> None:
    plan[table].update(ids)


def _empty_purge_plan() -> dict[str, set[UUID]]:
    return {**{name: set() for name in PURGE_MODELS}, "users": set()}


def _add_profile_users_to_plan(db: Session, plan: dict[str, set[UUID]]) -> None:
    parent_ids = plan.get("parents") or set()
    if parent_ids:
        _add_ids(plan, "users", db.scalars(select(Parent.user_id).where(Parent.id.in_(parent_ids))).all())
    teacher_ids = plan.get("teachers") or set()
    if teacher_ids:
        _add_ids(plan, "users", db.scalars(select(Teacher.user_id).where(Teacher.id.in_(teacher_ids))).all())


def _add_reports_to_plan(db: Session, plan: dict[str, set[UUID]], report_ids: set[UUID]) -> None:
    if not report_ids:
        return
    _add_ids(plan, "report_cards", report_ids)
    _add_ids(plan, "report_card_courses", db.scalars(select(ReportCardCourse.id).where(ReportCardCourse.report_card_id.in_(report_ids))).all())
    _add_ids(plan, "report_conduct_items", db.scalars(select(ReportConductItem.id).where(ReportConductItem.report_card_id.in_(report_ids))).all())
    _add_ids(plan, "report_work_habit_items", db.scalars(select(ReportWorkHabitItem.id).where(ReportWorkHabitItem.report_card_id.in_(report_ids))).all())
    _add_ids(plan, "ai_warnings", db.scalars(select(AIWarning.id).where(AIWarning.report_card_id.in_(report_ids))).all())


def _add_grade_items_to_plan(db: Session, plan: dict[str, set[UUID]], grade_item_ids: set[UUID]) -> None:
    if not grade_item_ids:
        return
    _add_ids(plan, "grade_items", grade_item_ids)
    _add_ids(plan, "grades", db.scalars(select(Grade.id).where(Grade.grade_item_id.in_(grade_item_ids))).all())


def _add_courses_to_plan(db: Session, plan: dict[str, set[UUID]], course_ids: set[UUID]) -> None:
    if not course_ids:
        return
    _add_ids(plan, "courses", course_ids)
    _add_ids(plan, "enrollments", db.scalars(select(Enrollment.id).where(Enrollment.course_id.in_(course_ids))).all())
    _add_grade_items_to_plan(db, plan, set(db.scalars(select(GradeItem.id).where(GradeItem.course_id.in_(course_ids))).all()))
    _add_ids(plan, "course_results", db.scalars(select(CourseResult.id).where(CourseResult.course_id.in_(course_ids))).all())
    # Report cards belong to students, not courses. Remove only the snapshot
    # links that carry the course FK; never consume the surrounding report.
    _add_ids(
        plan,
        "report_card_courses",
        db.scalars(select(ReportCardCourse.id).where(ReportCardCourse.course_id.in_(course_ids))).all(),
    )


def _expand_purge_plan_dependencies(db: Session, plan: dict[str, set[UUID]]) -> None:
    """Expand non-nullable ownership edges without crossing shared boundaries.

    * Student owns links, enrollments, grades, results, and reports. Closure
      stops at parent, course, grade item, teacher, and class rows.
    * Parent owns student-parent links and its role account. Closure stops at
      students.
    * Teacher owns submitted grades, assigned courses, and its role account.
      Course closure then stops at students, class, subject, and report roots.
    * Course owns enrollments, grade items/grades, results, and report-course
      snapshot links. It never deletes students, teachers, classes, subjects,
      or the report cards around those snapshot links.
    * Grade item owns grades. Report owns its snapshot/conduct/work/warning
      children. Class owns transient PDF jobs; student/course class references
      are nullable and handled separately. Subject owns no course rows.
    """
    teacher_ids = plan["teachers"]
    if teacher_ids:
        _add_ids(
            plan,
            "grades",
            db.scalars(select(Grade.id).where(Grade.submitted_by_teacher_id.in_(teacher_ids))).all(),
        )
        _add_courses_to_plan(
            db,
            plan,
            set(db.scalars(select(Course.id).where(Course.teacher_id.in_(teacher_ids))).all()),
        )

    student_ids = plan["students"]
    if student_ids:
        _add_ids(
            plan,
            "student_parents",
            db.scalars(select(StudentParent.id).where(StudentParent.student_id.in_(student_ids))).all(),
        )
        _add_ids(
            plan,
            "enrollments",
            db.scalars(select(Enrollment.id).where(Enrollment.student_id.in_(student_ids))).all(),
        )
        _add_ids(plan, "grades", db.scalars(select(Grade.id).where(Grade.student_id.in_(student_ids))).all())
        _add_ids(
            plan,
            "course_results",
            db.scalars(select(CourseResult.id).where(CourseResult.student_id.in_(student_ids))).all(),
        )
        _add_reports_to_plan(
            db,
            plan,
            set(db.scalars(select(ReportCard.id).where(ReportCard.student_id.in_(student_ids))).all()),
        )
        _add_ids(
            plan,
            "student_class_assignments",
            db.scalars(
                select(StudentClassAssignment.id).where(
                    StudentClassAssignment.student_id.in_(student_ids)
                )
            ).all(),
        )
        _add_ids(
            plan,
            "student_passage_decisions",
            db.scalars(select(StudentPassageDecision.id).where(StudentPassageDecision.student_id.in_(student_ids))).all(),
        )

    parent_ids = plan["parents"]
    if parent_ids:
        _add_ids(
            plan,
            "student_parents",
            db.scalars(select(StudentParent.id).where(StudentParent.parent_id.in_(parent_ids))).all(),
        )

    # Courses may have been present initially or added by teacher closure.
    _add_courses_to_plan(db, plan, set(plan["courses"]))
    _add_grade_items_to_plan(db, plan, set(plan["grade_items"]))
    _add_reports_to_plan(db, plan, set(plan["report_cards"]))

    class_ids = plan["classes"]
    if class_ids:
        _add_ids(plan, "pdf_jobs", db.scalars(select(PdfJob.id).where(PdfJob.class_id.in_(class_ids))).all())

    _add_profile_users_to_plan(db, plan)


def purge_plan_for_row(db: Session, *, table: str, entity_id: UUID) -> dict[str, set[UUID]]:
    plan = _empty_purge_plan()
    row = db.get(RECOVERABLE_MODELS[table], entity_id)
    if row is None or row.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found")
    _add_ids(plan, table, [entity_id])
    _expand_purge_plan_dependencies(db, plan)
    return plan


def purge_plan_for_batch(db: Session, batch_id: UUID) -> dict[str, set[UUID]]:
    batch = db.get(DeletionBatch, batch_id)
    if batch is None or batch.restored_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found")
    plan = _empty_purge_plan()
    for table, model in RECOVERABLE_MODELS.items():
        plan[table].update(db.scalars(select(model.id).where(model.deleted_batch_id == batch_id)).all())
    # Legacy batches can contain only their root while newer dependent rows have
    # no batch tag. Expand from every selected row before any physical delete.
    _expand_purge_plan_dependencies(db, plan)
    return plan


def purge_user_accounts(
    db: Session,
    user_ids: set[UUID],
    *,
    protected_user_id: UUID | None = None,
) -> dict[str, int]:
    if not user_ids:
        return {}
    if protected_user_id in user_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "purge_current_user_blocked", "message": "The current account cannot purge itself"},
        )

    owned_batch_ids = set(
        db.scalars(select(DeletionBatch.id).where(DeletionBatch.deleted_by_user_id.in_(user_ids))).all()
    )
    if owned_batch_ids:
        # deleted_by_user_id is intentionally non-nullable historical provenance.
        # A parent/teacher can reach this state only after an unusual role change;
        # never rewrite or delete those batches silently.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "purge_user_owns_deletion_batches",
                "message": "Account owns deletion history and cannot be purged automatically",
                "deletion_batch_count": len(owned_batch_ids),
            },
        )

    reset_tokens = db.scalars(
        select(PasswordResetToken).where(PasswordResetToken.user_id.in_(user_ids))
    ).all()
    for token in reset_tokens:
        db.delete(token)
    db.flush()

    # Preserve historical records while removing their nullable account links.
    db.execute(update(AuditLog).where(AuditLog.actor_user_id.in_(user_ids)).values(actor_user_id=None))
    db.execute(
        update(ReportCard)
        .where(ReportCard.approved_by_admin_id.in_(user_ids))
        .values(approved_by_admin_id=None)
    )
    db.execute(
        update(DeletionBatch)
        .where(DeletionBatch.restored_by_user_id.in_(user_ids))
        .values(restored_by_user_id=None)
    )
    db.execute(
        update(StudentPassageDecision)
        .where(StudentPassageDecision.decided_by_admin_id.in_(user_ids))
        .values(decided_by_admin_id=None)
    )
    db.flush()

    users = db.scalars(select(User).where(User.id.in_(user_ids))).all()
    for user in users:
        db.delete(user)
    db.flush()
    counts = {"users": len(users)}
    if reset_tokens:
        counts["password_reset_tokens"] = len(reset_tokens)
    return counts


def _null_external_references(db: Session, plan: dict[str, set[UUID]]) -> None:
    """Detach nullable references from live rows outside the ownership closure."""
    class_ids = plan["classes"]
    if class_ids:
        student_update = update(Student).where(Student.class_id.in_(class_ids))
        if plan["students"]:
            student_update = student_update.where(Student.id.not_in(plan["students"]))
        db.execute(student_update.values(class_id=None))

        course_update = update(Course).where(Course.class_id.in_(class_ids))
        if plan["courses"]:
            course_update = course_update.where(Course.id.not_in(plan["courses"]))
        db.execute(course_update.values(class_id=None))
        db.execute(
            update(StudentClassAssignment)
            .where(StudentClassAssignment.class_id.in_(class_ids))
            .values(class_id=None)
        )
        db.execute(
            update(StudentPassageDecision)
            .where(StudentPassageDecision.from_class_id.in_(class_ids))
            .values(from_class_id=None)
        )
        db.execute(
            update(StudentPassageDecision)
            .where(StudentPassageDecision.result_class_id.in_(class_ids))
            .values(result_class_id=None)
        )

    subject_ids = plan["subjects"]
    if subject_ids:
        course_update = update(Course).where(Course.subject_id.in_(subject_ids))
        if plan["courses"]:
            course_update = course_update.where(Course.id.not_in(plan["courses"]))
        db.execute(course_update.values(subject_id=None))

    db.flush()


def purge_plan(
    db: Session,
    plan: dict[str, set[UUID]],
    *,
    protected_user_id: UUID | None = None,
) -> dict[str, int]:
    # PURGE_ORDER is child-first to satisfy foreign keys. Only precomputed IDs
    # belonging to this deleted entry are touched; do not broaden these queries
    # to relationship-wide deletes that could consume active school data.
    _null_external_references(db, plan)
    counts: dict[str, int] = {}
    for table in PURGE_ORDER:
        if table == "users":
            counts.update(
                purge_user_accounts(
                    db,
                    plan.get("users") or set(),
                    protected_user_id=protected_user_id,
                )
            )
            continue
        ids = plan.get(table) or set()
        if not ids:
            continue
        model = PURGE_MODELS[table]
        rows = db.scalars(select(model).where(model.id.in_(ids))).all()
        for row in rows:
            db.delete(row)
        # Make each FK layer disappear physically before its parent layer.
        # The flush also keeps constraint failures inside purge_entry's savepoint.
        db.flush()
        counts[table] = len(rows)
    return counts


def purge_batch_entry(
    db: Session,
    *,
    batch_id: UUID,
    protected_user_id: UUID | None = None,
) -> tuple[str, dict[str, int]]:
    batch = db.get(DeletionBatch, batch_id)
    if batch is None or batch.restored_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found")
    label = batch.target_label
    plan = purge_plan_for_batch(db, batch_id)
    counts = purge_plan(db, plan, protected_user_id=protected_user_id)
    for model in RECOVERABLE_MODELS.values():
        remaining = db.scalar(select(func.count()).select_from(model).where(model.deleted_batch_id == batch_id))
        if remaining:
            raise RuntimeError(f"Purge plan left {remaining} batch reference(s) in {model.__tablename__}")
    db.delete(batch)
    db.flush()
    return label, counts


def purge_row_entry(
    db: Session,
    *,
    table: str,
    entity_id: UUID,
    protected_user_id: UUID | None = None,
) -> tuple[str, dict[str, int]]:
    row = db.get(RECOVERABLE_MODELS[table], entity_id)
    if row is None or row.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found")
    label = row_label(row)
    plan = purge_plan_for_row(db, table=table, entity_id=entity_id)
    counts = purge_plan(db, plan, protected_user_id=protected_user_id)
    return label, counts


def purge_entry(db: Session, *, entry_id: str, current_user: User, audit_action: str = "trash_entry_purged") -> tuple[str, dict[str, int]]:
    try:
        source, table, entity_id = parse_entry_id(entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash entry not found") from exc

    # One savepoint per entry prevents a failed cascade from leaving a partially
    # purged tree while still allowing empty-trash/retention sweeps to iterate.
    with db.begin_nested():
        if source == "batch":
            label, counts = purge_batch_entry(db, batch_id=entity_id, protected_user_id=current_user.id)
            entity_type = "deletion_batch"
        else:
            assert table is not None
            label, counts = purge_row_entry(
                db,
                table=table,
                entity_id=entity_id,
                protected_user_id=current_user.id,
            )
            entity_type = _entity_type_for_table(table)
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action=audit_action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value={"entry_id": entry_id, "target_label": label},
            new_value={"counts": counts},
        )
    return label, counts


def purge_expired_entries(db: Session, *, current_user: User) -> dict[str, int]:
    # The retention clock is the entry's deleted_at, not batch creation or last
    # access. restore clears deleted_at, so re-deletion naturally gets 30 days.
    cutoff = _now() - timedelta(days=RETENTION_DAYS)
    expired = [entry for entry in list_trash_entries(db) if entry.deleted_at < cutoff]
    aggregate: dict[str, int] = {}
    for entry in expired:
        try:
            _, counts = purge_entry(db, entry_id=entry.id, current_user=current_user, audit_action="trash_auto_purged")
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                continue
            raise
        for table, count in counts.items():
            aggregate[table] = aggregate.get(table, 0) + count
    return aggregate


def purge_all_entries(db: Session, *, current_user: User) -> dict[str, int]:
    entries = list_trash_entries(db)
    aggregate: dict[str, int] = {}
    for entry in entries:
        try:
            _, counts = purge_entry(db, entry_id=entry.id, current_user=current_user, audit_action="trash_purged")
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                continue
            raise
        for table, count in counts.items():
            aggregate[table] = aggregate.get(table, 0) + count
    return aggregate
