"""Manage GGFK classes and class-wide setup operations.

Bulk creation is anchored to the locked bilingual taxonomy, while bulk
enrollment previews the exact missing links before creating them idempotently.
Class deletion remains guarded by active students/courses and uses recoverable
soft deletion because class ownership affects broad academic history.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import require_admin
from constants import GGFK_CLASSES, normalize_class_name
from database import get_db
from models import Class, Course, Enrollment, Student, User
from schemas import (
    ClassBulkCreateRequest,
    ClassBulkCreateResponse,
    ClassBulkEnrollResponse,
    ClassCreate,
    ClassEnrollmentPreviewResponse,
    ClassResponse,
    ClassUpdate,
    SchoolLevel,
    StatusResponse,
)
from utils import get_class_or_404


router = APIRouter(tags=["classes"])

# Nursery -> Primary -> Collège, taken from the SchoolLevel enum declaration order.
_SCHOOL_LEVEL_RANK = {level.value: index for index, level in enumerate(SchoolLevel)}


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{field_name} cannot be empty")
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _class_snapshot(school_class: Class) -> dict:
    return {
        "name_fr": school_class.name_fr,
        "name_en": school_class.name_en,
        "school_level": school_class.school_level,
        "stream": school_class.stream,
        "sort_order": school_class.sort_order,
        "school_year": school_class.school_year,
    }


def _counts_for_classes(db: Session, class_ids: list[UUID]) -> tuple[dict, dict]:
    if not class_ids:
        return {}, {}
    student_rows = db.execute(
        select(Student.class_id, func.count(Student.id))
        .where(
            Student.class_id.in_(class_ids),
            Student.deleted_at.is_(None),
        )
        .group_by(Student.class_id)
    ).all()
    course_rows = db.execute(
        select(Course.class_id, func.count(Course.id))
        .where(Course.class_id.in_(class_ids))
        .where(Course.deleted_at.is_(None))
        .group_by(Course.class_id)
    ).all()
    return dict(student_rows), dict(course_rows)


def to_class_response(
    school_class: Class, *, student_count: int = 0, course_count: int = 0
) -> ClassResponse:
    return ClassResponse(
        id=school_class.id,
        name_fr=school_class.name_fr,
        name_en=school_class.name_en,
        school_level=school_class.school_level,
        stream=school_class.stream,
        sort_order=school_class.sort_order,
        school_year=school_class.school_year,
        student_count=student_count,
        course_count=course_count,
    )


def _response_with_counts(db: Session, school_class: Class) -> ClassResponse:
    student_counts, course_counts = _counts_for_classes(db, [school_class.id])
    return to_class_response(
        school_class,
        student_count=student_counts.get(school_class.id, 0),
        course_count=course_counts.get(school_class.id, 0),
    )


_DUPLICATE_DETAIL = "A class with this name already exists for this school year"


@router.get("", response_model=list[ClassResponse])
def list_classes(
    school_year: str | None = None,
    school_level: SchoolLevel | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ClassResponse]:
    query = select(Class).where(Class.deleted_at.is_(None))
    if school_year is not None:
        query = query.where(Class.school_year == school_year)
    if school_level is not None:
        query = query.where(Class.school_level == school_level.value)

    classes = list(db.scalars(query).all())
    # Sort by school level (nursery -> primary -> collège) then sort_order.
    classes.sort(key=lambda c: (_SCHOOL_LEVEL_RANK.get(c.school_level, 99), c.sort_order))

    student_counts, course_counts = _counts_for_classes(db, [c.id for c in classes])
    return [
        to_class_response(
            c,
            student_count=student_counts.get(c.id, 0),
            course_count=course_counts.get(c.id, 0),
        )
        for c in classes
    ]


@router.post("", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassResponse:
    school_class = Class(
        name_fr=clean_required_text(payload.name_fr, "name_fr"),
        name_en=_clean_optional_text(payload.name_en),
        school_level=payload.school_level.value,
        stream=_clean_optional_text(payload.stream),
        sort_order=payload.sort_order,
        school_year=clean_required_text(payload.school_year, "school_year"),
    )
    db.add(school_class)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from exc

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="class_created",
        entity_type="class",
        entity_id=school_class.id,
        old_value=None,
        new_value=_class_snapshot(school_class),
    )
    db.commit()
    db.refresh(school_class)
    return to_class_response(school_class)


@router.post("/bulk-create", response_model=ClassBulkCreateResponse)
def bulk_create_classes(
    payload: ClassBulkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassBulkCreateResponse:
    """Create all 18 GGFK taxonomy classes for a school year (A1.10).

    Idempotent: classes already present for the year (matched accent/case-
    insensitively, so a hand-typed "6eme" counts as 6ème) are skipped, not
    duplicated and not errored.
    """
    school_year = clean_required_text(payload.school_year, "school_year")

    existing_keys = {
        normalize_class_name(name)
        for name in db.scalars(
            select(Class.name_fr).where(Class.school_year == school_year, Class.deleted_at.is_(None))
        ).all()
    }

    created: list[str] = []
    skipped: list[str] = []
    for entry in GGFK_CLASSES:
        if normalize_class_name(entry["name_fr"]) in existing_keys:
            skipped.append(entry["name_fr"])
            continue
        db.add(
            Class(
                name_fr=entry["name_fr"],
                name_en=entry["name_en"],
                school_level=entry["school_level"],
                stream=entry["stream"],
                sort_order=entry["sort_order"],
                school_year=school_year,
            )
        )
        created.append(entry["name_fr"])

    if created:
        db.flush()
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="classes_bulk_created",
            entity_type="class_bulk_create",
            entity_id=uuid4(),
            old_value=None,
            new_value={
                "school_year": school_year,
                "created": created,
                "skipped": skipped,
            },
        )
        db.commit()

    return ClassBulkCreateResponse(status="ok", created=created, skipped=skipped)


def _compute_class_enrollment_plan(db: Session, school_class: Class) -> dict:
    """Shared work for the preview and the write action.

    Both must scope courses to class.school_year (guards against a course
    accidentally tagged with the right class but created for the wrong year);
    both need the same counts. Returns the raw student / course id lists plus
    a set of existing (student_id, course_id) enrollment pairs so the write
    path can insert only the missing ones.
    """
    student_ids = list(
        db.scalars(
            select(Student.id).where(
                Student.class_id == school_class.id,
                Student.deleted_at.is_(None),
            )
        ).all()
    )
    course_ids = list(
        db.scalars(
            select(Course.id).where(
                Course.class_id == school_class.id,
                Course.school_year == school_class.school_year,
                Course.deleted_at.is_(None),
            )
        ).all()
    )
    existing_pairs: set[tuple[UUID, UUID]] = set()
    if student_ids and course_ids:
        existing_pairs = {
            (student_id, course_id)
            for student_id, course_id in db.execute(
                select(Enrollment.student_id, Enrollment.course_id).where(
                    Enrollment.student_id.in_(student_ids),
                    Enrollment.course_id.in_(course_ids),
                    Enrollment.deleted_at.is_(None),
                )
            ).all()
        }
    return {
        "student_ids": student_ids,
        "course_ids": course_ids,
        "existing_pairs": existing_pairs,
    }


@router.get("/{class_id}/enrollment-preview", response_model=ClassEnrollmentPreviewResponse)
def preview_class_enrollments(
    class_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ClassEnrollmentPreviewResponse:
    """Counts the bulk-enroll action would produce (no writes, no audit)."""
    school_class = get_class_or_404(db, class_id)
    plan = _compute_class_enrollment_plan(db, school_class)
    students = len(plan["student_ids"])
    courses = len(plan["course_ids"])
    total_pairs = students * courses
    already = len(plan["existing_pairs"])

    return ClassEnrollmentPreviewResponse(
        status="ok" if students and courses else "empty",
        class_id=school_class.id,
        school_year=school_class.school_year,
        students_in_class=students,
        courses_in_class=courses,
        enrollments_to_create=total_pairs - already,
        enrollments_already_existing=already,
    )


@router.post("/{class_id}/bulk-enroll", response_model=ClassBulkEnrollResponse)
def bulk_enroll_class_students(
    class_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassBulkEnrollResponse:
    """Enroll every student in the class into every course in the class (A1.11).

    Scope: students with student.class_id == class_id, courses with
    course.class_id == class_id AND course.school_year == class.school_year.
    Idempotent — existing (student_id, course_id) pairs are skipped, no
    duplicate rows, no 409. Empty class (0 students or 0 courses) returns 200
    with status="empty" and the two counts so callers can be specific.
    """
    school_class = get_class_or_404(db, class_id)
    plan = _compute_class_enrollment_plan(db, school_class)
    students = len(plan["student_ids"])
    courses = len(plan["course_ids"])

    if not students or not courses:
        return ClassBulkEnrollResponse(
            status="empty",
            class_id=school_class.id,
            school_year=school_class.school_year,
            students_in_class=students,
            courses_in_class=courses,
            enrollments_created=0,
            enrollments_skipped=0,
        )

    existing = plan["existing_pairs"]
    to_create = [
        Enrollment(student_id=student_id, course_id=course_id)
        for student_id in plan["student_ids"]
        for course_id in plan["course_ids"]
        if (student_id, course_id) not in existing
    ]
    skipped = students * courses - len(to_create)

    if to_create:
        db.add_all(to_create)
        db.flush()
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="class_students_bulk_enrolled",
            entity_type="class_bulk_enroll",
            entity_id=uuid4(),
            old_value=None,
            new_value={
                "class_id": school_class.id,
                "school_year": school_class.school_year,
                "students_in_class": students,
                "courses_in_class": courses,
                "enrollments_created": len(to_create),
                "enrollments_skipped": skipped,
            },
        )
        db.commit()

    return ClassBulkEnrollResponse(
        status="ok",
        class_id=school_class.id,
        school_year=school_class.school_year,
        students_in_class=students,
        courses_in_class=courses,
        enrollments_created=len(to_create),
        enrollments_skipped=skipped,
    )


@router.get("/{class_id}", response_model=ClassResponse)
def get_class(
    class_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ClassResponse:
    school_class = get_class_or_404(db, class_id)
    return _response_with_counts(db, school_class)


@router.patch("/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: UUID,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassResponse:
    school_class = get_class_or_404(db, class_id)
    old_value = _class_snapshot(school_class)

    if payload.name_fr is not None:
        school_class.name_fr = clean_required_text(payload.name_fr, "name_fr")
    if payload.school_level is not None:
        school_class.school_level = payload.school_level.value
    if payload.sort_order is not None:
        school_class.sort_order = payload.sort_order
    if payload.school_year is not None:
        school_class.school_year = clean_required_text(payload.school_year, "school_year")
    # name_en and stream are nullable: an explicit null clears; an omitted key
    # leaves the value unchanged.
    if "name_en" in payload.model_fields_set:
        school_class.name_en = _clean_optional_text(payload.name_en)
    if "stream" in payload.model_fields_set:
        school_class.stream = _clean_optional_text(payload.stream)

    new_value = _class_snapshot(school_class)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from exc

    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="class_updated",
            entity_type="class",
            entity_id=school_class.id,
            old_value=old_value,
            new_value=new_value,
        )
    db.commit()
    db.refresh(school_class)
    return _response_with_counts(db, school_class)


@router.delete("/{class_id}", response_model=StatusResponse)
def delete_class(
    class_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    school_class = get_class_or_404(db, class_id)
    student_count = db.scalar(
        select(func.count(Student.id)).where(Student.class_id == class_id, Student.deleted_at.is_(None))
    )
    course_count = db.scalar(
        select(func.count(Course.id)).where(Course.class_id == class_id, Course.deleted_at.is_(None))
    )
    if student_count or course_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Class has assigned students or courses",
                "student_count": student_count,
                "course_count": course_count,
            },
        )

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="class_deleted",
        entity_type="class",
        entity_id=school_class.id,
        old_value=_class_snapshot(school_class),
        new_value=None,
    )
    school_class.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return StatusResponse(status="ok", message="Class moved to Trash")
