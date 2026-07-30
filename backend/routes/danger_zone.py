"""Owner Nettoyage preview and recoverable cascade-to-trash operations.

Nettoyage is not a hard-delete API: it computes a dependency plan, requires
typed confirmation, tags every selected row with one ``DeletionBatch``, and
leaves restoration to the unified Corbeille. Production requires the explicit
``ENABLE_DANGER_ZONE`` opt-in. Student/class/parent boundaries are deliberately
conservative so a broad setup cleanup does not silently include unrelated
people. Trashing teacher/parent profiles soft-deletes their one-to-one login
accounts and invalidates sessions through the token-version mechanism in
``auth.py``. Restore uses unified Corbeille conflict checks and never revives
an old JWT.
"""

import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from auth import invalidate_user_sessions, require_admin
from database import get_db
from models import (
    AIWarning,
    Class,
    Course,
    CourseResult,
    DeletionBatch,
    Enrollment,
    Grade,
    GradeItem,
    Parent,
    ReportCard,
    ReportCardCourse,
    ReportConductItem,
    ReportWorkHabitItem,
    Student,
    StudentParent,
    Teacher,
    User,
)
from schemas import (
    DangerZoneBatchResponse,
    DangerZoneDeleteRequest,
    DangerZoneDeleteResponse,
    DangerZonePreviewResponse,
    DangerZoneSearchResult,
    StatusResponse,
)
from services.account_lifecycle import soft_delete_profile_account
from services.trash import restore_batch_entry


router = APIRouter(prefix="/admin/danger-zone", tags=["danger zone"])

RECOVERABLE_MODELS = {
    "classes": Class,
    "students": Student,
    "parents": Parent,
    "student_parents": StudentParent,
    "teachers": Teacher,
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

ENTITY_TYPES = {"student", "parent", "teacher", "class", "course", "grade_item", "report"}


def _danger_zone_enabled() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or os.getenv("ENV") or "development").lower()
    if env in {"production", "prod"}:
        return os.getenv("ENABLE_DANGER_ZONE", "").lower() == "true"
    return True


def _ensure_enabled() -> None:
    if not _danger_zone_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Danger Zone is disabled in production",
        )


def _active(query):
    return query.where(query.column_descriptions[0]["entity"].deleted_at.is_(None))


def _ids(rows) -> set[UUID]:
    return {row.id for row in rows}


def _rows_by_ids(db: Session, model, ids: set[UUID]):
    if not ids:
        return []
    return list(db.scalars(select(model).where(model.id.in_(ids))).all())


def _target_or_404(db: Session, entity_type: str, entity_id: UUID):
    model_by_type = {
        "student": Student,
        "parent": Parent,
        "teacher": Teacher,
        "class": Class,
        "course": Course,
        "grade_item": GradeItem,
        "report": ReportCard,
    }
    model = model_by_type.get(entity_type)
    if model is None:
        raise HTTPException(status_code=422, detail="Unsupported entity_type")
    target = db.get(model, entity_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return target


def _label(target) -> str:
    if isinstance(target, Student):
        return f"{target.first_name} {target.last_name} #{target.student_number}"
    if isinstance(target, Parent):
        return f"{target.user.name} ({target.user.email or 'no email'})"
    if isinstance(target, Teacher):
        return f"{target.user.name} #{target.employee_number}"
    if isinstance(target, Class):
        return f"{target.name_fr} {target.school_year}"
    if isinstance(target, Course):
        return f"{target.name} ({target.code})"
    if isinstance(target, GradeItem):
        return f"{target.title} ({target.course.code})"
    if isinstance(target, ReportCard):
        return f"Report {target.term} {target.school_year}"
    return str(target.id)


def _school_level_label(value: str | None) -> str:
    labels = {"maternelle": "Maternelle", "primaire": "Primaire", "college": "Collège"}
    return labels.get(value or "", value or "")


def _report_status_label(value: str) -> str:
    return {"draft": "Draft", "approved": "Approved", "sent": "Sent"}.get(value, value.title())


def _search_pattern(q: str) -> str:
    return f"%{q.strip()}%"


def _student_label(student: Student) -> str:
    return f"{student.first_name} {student.last_name}"


def _student_subtitle(student: Student) -> str:
    parts = [student.student_number]
    if student.school_class is not None:
        parts.append(student.school_class.name_fr)
    return " · ".join(parts)


def _class_label(school_class: Class) -> str:
    return school_class.name_fr


def _class_subtitle(school_class: Class) -> str:
    parts = [school_class.school_year, _school_level_label(school_class.school_level)]
    return " · ".join(part for part in parts if part)


def _course_subtitle(course: Course) -> str:
    parts = []
    if course.school_class is not None:
        parts.append(course.school_class.name_fr)
    parts.append(course.school_year)
    if course.teacher is not None and course.teacher.user is not None:
        parts.append(course.teacher.user.email or course.teacher.user.name)
    return " · ".join(part for part in parts if part)


def _search_results(db: Session, entity_type: str, q: str) -> list[DangerZoneSearchResult]:
    pattern = _search_pattern(q)
    if entity_type == "student":
        rows = db.scalars(
            select(Student)
            .options(joinedload(Student.school_class))
            .where(
                Student.deleted_at.is_(None),
                or_(
                    Student.first_name.ilike(pattern),
                    Student.last_name.ilike(pattern),
                    Student.student_number.ilike(pattern),
                ),
            )
            .order_by(Student.last_name, Student.first_name)
            .limit(20)
        ).all()
        return [
            DangerZoneSearchResult(
                id=row.id,
                label=_student_label(row),
                subtitle=_student_subtitle(row),
                entity_type=entity_type,
            )
            for row in rows
        ]

    if entity_type == "parent":
        rows = db.scalars(
            select(Parent)
            .join(Parent.user)
            .options(joinedload(Parent.user))
            .where(
                Parent.deleted_at.is_(None),
                or_(User.name.ilike(pattern), User.email.ilike(pattern), Parent.phone.ilike(pattern)),
            )
            .order_by(User.name)
            .limit(20)
        ).all()
        return [
            DangerZoneSearchResult(id=row.id, label=row.user.name, subtitle=row.user.email or row.user.name, entity_type=entity_type)
            for row in rows
        ]

    if entity_type == "teacher":
        rows = db.scalars(
            select(Teacher)
            .join(Teacher.user)
            .options(joinedload(Teacher.user))
            .where(
                Teacher.deleted_at.is_(None),
                or_(User.name.ilike(pattern), User.email.ilike(pattern), Teacher.employee_number.ilike(pattern)),
            )
            .order_by(User.name)
            .limit(20)
        ).all()
        return [
            DangerZoneSearchResult(id=row.id, label=row.user.name, subtitle=row.user.email or row.employee_number, entity_type=entity_type)
            for row in rows
        ]

    if entity_type == "class":
        rows = db.scalars(
            select(Class)
            .where(
                Class.deleted_at.is_(None),
                or_(
                    Class.name_fr.ilike(pattern),
                    Class.name_en.ilike(pattern),
                    Class.school_year.ilike(pattern),
                    Class.school_level.ilike(pattern),
                ),
            )
            .order_by(Class.school_year.desc(), Class.sort_order)
            .limit(20)
        ).all()
        return [
            DangerZoneSearchResult(
                id=row.id,
                label=_class_label(row),
                subtitle=_class_subtitle(row),
                entity_type=entity_type,
            )
            for row in rows
        ]

    if entity_type == "course":
        rows = db.scalars(
            select(Course)
            .join(Course.teacher)
            .join(Teacher.user)
            .outerjoin(Course.school_class)
            .options(joinedload(Course.teacher).joinedload(Teacher.user), joinedload(Course.school_class))
            .where(
                Course.deleted_at.is_(None),
                Teacher.deleted_at.is_(None),
                or_(
                    Course.name.ilike(pattern),
                    Course.code.ilike(pattern),
                    Course.school_year.ilike(pattern),
                    User.name.ilike(pattern),
                    User.email.ilike(pattern),
                    Class.name_fr.ilike(pattern),
                ),
            )
            .order_by(Course.school_year.desc(), Course.name, Course.code)
            .limit(20)
        ).all()
        return [
            DangerZoneSearchResult(id=row.id, label=row.name, subtitle=_course_subtitle(row), entity_type=entity_type)
            for row in rows
        ]

    if entity_type == "grade_item":
        rows = db.scalars(
            select(GradeItem)
            .join(GradeItem.course)
            .options(joinedload(GradeItem.course))
            .where(
                GradeItem.deleted_at.is_(None),
                Course.deleted_at.is_(None),
                or_(GradeItem.title.ilike(pattern), GradeItem.category.ilike(pattern), Course.name.ilike(pattern), Course.code.ilike(pattern)),
            )
            .order_by(Course.name, GradeItem.created_at)
            .limit(20)
        ).all()
        return [
            DangerZoneSearchResult(
                id=row.id,
                label=row.title,
                subtitle=f"{row.course.name} · {row.term}",
                entity_type=entity_type,
            )
            for row in rows
        ]

    if entity_type == "report":
        rows = db.scalars(
            select(ReportCard)
            .join(ReportCard.student)
            .options(joinedload(ReportCard.student))
            .where(
                ReportCard.deleted_at.is_(None),
                Student.deleted_at.is_(None),
                or_(
                    Student.first_name.ilike(pattern),
                    Student.last_name.ilike(pattern),
                    Student.student_number.ilike(pattern),
                    ReportCard.term.ilike(pattern),
                    ReportCard.school_year.ilike(pattern),
                    ReportCard.status.ilike(pattern),
                ),
            )
            .order_by(ReportCard.created_at.desc())
            .limit(20)
        ).all()
        return [
            DangerZoneSearchResult(
                id=row.id,
                label=_student_label(row.student),
                subtitle=f"{row.term} · {row.school_year} · {_report_status_label(row.status)}",
                entity_type=entity_type,
            )
            for row in rows
        ]

    raise HTTPException(status_code=422, detail="Unsupported entity_type")


def _empty_plan() -> dict[str, set[UUID]]:
    return {name: set() for name in RECOVERABLE_MODELS}


def _add_report(plan: dict[str, set[UUID]], db: Session, report_ids: set[UUID]) -> None:
    report_ids = set(report_ids)
    report_ids -= plan["report_cards"]
    if not report_ids:
        return
    plan["report_cards"].update(report_ids)
    plan["report_card_courses"].update(
        db.scalars(
            select(ReportCardCourse.id).where(
                ReportCardCourse.report_card_id.in_(report_ids),
                ReportCardCourse.deleted_at.is_(None),
            )
        ).all()
    )
    plan["report_conduct_items"].update(
        db.scalars(
            select(ReportConductItem.id).where(
                ReportConductItem.report_card_id.in_(report_ids),
                ReportConductItem.deleted_at.is_(None),
            )
        ).all()
    )
    plan["report_work_habit_items"].update(
        db.scalars(
            select(ReportWorkHabitItem.id).where(
                ReportWorkHabitItem.report_card_id.in_(report_ids),
                ReportWorkHabitItem.deleted_at.is_(None),
            )
        ).all()
    )
    plan["ai_warnings"].update(
        db.scalars(
            select(AIWarning.id).where(
                AIWarning.report_card_id.in_(report_ids),
                AIWarning.deleted_at.is_(None),
            )
        ).all()
    )


def _add_courses(plan: dict[str, set[UUID]], db: Session, course_ids: set[UUID]) -> None:
    course_ids = set(course_ids)
    course_ids -= plan["courses"]
    if not course_ids:
        return
    plan["courses"].update(course_ids)
    plan["enrollments"].update(
        db.scalars(select(Enrollment.id).where(Enrollment.course_id.in_(course_ids), Enrollment.deleted_at.is_(None))).all()
    )
    grade_item_ids = set(
        db.scalars(select(GradeItem.id).where(GradeItem.course_id.in_(course_ids), GradeItem.deleted_at.is_(None))).all()
    )
    _add_grade_items(plan, db, grade_item_ids)
    plan["course_results"].update(
        db.scalars(
            select(CourseResult.id).where(CourseResult.course_id.in_(course_ids), CourseResult.deleted_at.is_(None))
        ).all()
    )
    report_ids = set(
        db.scalars(
            select(ReportCardCourse.report_card_id).where(
                ReportCardCourse.course_id.in_(course_ids),
                ReportCardCourse.deleted_at.is_(None),
            )
        ).all()
    )
    _add_report(plan, db, report_ids)


def _add_grade_items(plan: dict[str, set[UUID]], db: Session, grade_item_ids: set[UUID]) -> None:
    grade_item_ids = set(grade_item_ids)
    grade_item_ids -= plan["grade_items"]
    if not grade_item_ids:
        return
    plan["grade_items"].update(grade_item_ids)
    plan["grades"].update(
        db.scalars(select(Grade.id).where(Grade.grade_item_id.in_(grade_item_ids), Grade.deleted_at.is_(None))).all()
    )


def _build_plan(db: Session, entity_type: str, entity_id: UUID) -> tuple[object, str, dict[str, set[UUID]], list[str]]:
    target = _target_or_404(db, entity_type, entity_id)
    plan = _empty_plan()
    warnings: list[str] = []

    if entity_type == "student":
        plan["students"].add(entity_id)
        plan["student_parents"].update(
            db.scalars(select(StudentParent.id).where(StudentParent.student_id == entity_id, StudentParent.deleted_at.is_(None))).all()
        )
        plan["enrollments"].update(
            db.scalars(select(Enrollment.id).where(Enrollment.student_id == entity_id, Enrollment.deleted_at.is_(None))).all()
        )
        plan["grades"].update(
            db.scalars(select(Grade.id).where(Grade.student_id == entity_id, Grade.deleted_at.is_(None))).all()
        )
        plan["course_results"].update(
            db.scalars(select(CourseResult.id).where(CourseResult.student_id == entity_id, CourseResult.deleted_at.is_(None))).all()
        )
        _add_report(
            plan,
            db,
            set(db.scalars(select(ReportCard.id).where(ReportCard.student_id == entity_id, ReportCard.deleted_at.is_(None))).all()),
        )
        warnings.append("Parent profiles are not moved when deleting a student.")
    elif entity_type == "parent":
        plan["parents"].add(entity_id)
        plan["student_parents"].update(
            db.scalars(select(StudentParent.id).where(StudentParent.parent_id == entity_id, StudentParent.deleted_at.is_(None))).all()
        )
        warnings.append("Students are not moved when deleting a parent.")
    elif entity_type == "teacher":
        plan["teachers"].add(entity_id)
        _add_courses(
            plan,
            db,
            set(db.scalars(select(Course.id).where(Course.teacher_id == entity_id, Course.deleted_at.is_(None))).all()),
        )
        plan["grades"].update(
            db.scalars(select(Grade.id).where(Grade.submitted_by_teacher_id == entity_id, Grade.deleted_at.is_(None))).all()
        )
    elif entity_type == "class":
        plan["classes"].add(entity_id)
        _add_courses(
            plan,
            db,
            set(db.scalars(select(Course.id).where(Course.class_id == entity_id, Course.deleted_at.is_(None))).all()),
        )
        warnings.append("Students assigned to this class are not moved automatically.")
    elif entity_type == "course":
        _add_courses(plan, db, {entity_id})
    elif entity_type == "grade_item":
        _add_grade_items(plan, db, {entity_id})
    elif entity_type == "report":
        _add_report(plan, db, {entity_id})
    else:
        raise HTTPException(status_code=422, detail="Unsupported entity_type")

    return target, _label(target), plan, warnings


def _counts(plan: dict[str, set[UUID]]) -> dict[str, int]:
    return {table: len(ids) for table, ids in plan.items() if ids}


def _mark_plan(db: Session, plan: dict[str, set[UUID]], *, batch_id: UUID, deleted_at: datetime) -> dict[str, int]:
    counts = {}
    for table, ids in plan.items():
        if not ids:
            continue
        model = RECOVERABLE_MODELS[table]
        rows = _rows_by_ids(db, model, ids)
        for row in rows:
            row.deleted_at = deleted_at
            row.deleted_batch_id = batch_id
            # See auth.py for the token-version contract. Restoring the profile
            # clears trash fields only; previously issued sessions stay dead.
            if isinstance(row, (Teacher, Parent)):
                soft_delete_profile_account(row, deleted_at)
                invalidate_user_sessions(row.user)
        counts[table] = len(rows)
    return counts


def _batch_response(batch: DeletionBatch) -> DangerZoneBatchResponse:
    return DangerZoneBatchResponse(
        id=batch.id,
        entity_type=batch.entity_type,
        entity_id=batch.entity_id,
        target_label=batch.target_label,
        reason=batch.reason,
        deleted_by_user_id=batch.deleted_by_user_id,
        deleted_at=batch.deleted_at,
        restored_at=batch.restored_at,
        restored_by_user_id=batch.restored_by_user_id,
        counts=batch.counts_json,
    )


@router.get("/search", response_model=list[DangerZoneSearchResult])
def search_danger_zone_targets(
    entity_type: str = Query(...),
    q: str = Query(""),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DangerZoneSearchResult]:
    _ensure_enabled()
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported entity_type")
    return _search_results(db, entity_type, q)


@router.get("/preview", response_model=DangerZonePreviewResponse)
def preview_danger_zone_delete(
    entity_type: str = Query(...),
    entity_id: UUID = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DangerZonePreviewResponse:
    _ensure_enabled()
    target, target_label, plan, warnings = _build_plan(db, entity_type, entity_id)
    return DangerZonePreviewResponse(
        entity_type=entity_type,
        entity_id=target.id,
        target_label=target_label,
        counts=_counts(plan),
        warnings=warnings,
    )


@router.post("/delete", response_model=DangerZoneDeleteResponse)
def move_danger_zone_batch_to_trash(
    payload: DangerZoneDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DangerZoneDeleteResponse:
    _ensure_enabled()
    target, target_label, plan, warnings = _build_plan(db, payload.entity_type, payload.entity_id)
    accepted = {"MOVE TO TRASH", f"MOVE {target_label} TO TRASH"}
    if payload.confirmation.strip() not in accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation does not match")

    deleted_at = datetime.now(timezone.utc)
    batch = DeletionBatch(
        entity_type=payload.entity_type,
        entity_id=target.id,
        target_label=target_label,
        reason=payload.reason,
        deleted_by_user_id=current_user.id,
        deleted_at=deleted_at,
        counts_json=_counts(plan),
    )
    db.add(batch)
    db.flush()
    counts = _mark_plan(db, plan, batch_id=batch.id, deleted_at=deleted_at)
    batch.counts_json = counts
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="danger_zone_moved_to_trash",
        entity_type=payload.entity_type,
        entity_id=target.id,
        old_value={"target_label": target_label},
        new_value={"batch_id": batch.id, "counts": counts, "warnings": warnings},
    )
    db.commit()
    return DangerZoneDeleteResponse(status="ok", batch_id=batch.id, target_label=target_label, counts=counts)


@router.get("/batches", response_model=list[DangerZoneBatchResponse])
def list_deletion_batches(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DangerZoneBatchResponse]:
    _ensure_enabled()
    batches = db.scalars(select(DeletionBatch).order_by(DeletionBatch.deleted_at.desc())).all()
    return [_batch_response(batch) for batch in batches]


@router.get("/batches/{batch_id}", response_model=DangerZoneBatchResponse)
def get_deletion_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> DangerZoneBatchResponse:
    _ensure_enabled()
    batch = db.get(DeletionBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion batch not found")
    return _batch_response(batch)


@router.post("/batches/{batch_id}/restore", response_model=StatusResponse)
def restore_deletion_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    _ensure_enabled()
    batch = db.get(DeletionBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion batch not found")
    restore_batch_entry(db, batch_id=batch_id, current_user=current_user)
    db.commit()
    return StatusResponse(status="ok", message="Deletion batch restored")
