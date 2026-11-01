"""Manage year-scoped GGFK class instances and class-wide setup operations.

Class taxonomy names are permanent catalog data, while each ``Class`` row and
student assignment belongs to one school year. Class rosters and counts resolve
through ``StudentClassAssignment``; they never infer a year from the student's
temporary live ``class_id`` pointer.

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
from constants import normalize_class_name
from database import get_db
from models import Class, Course, Enrollment, Student, StudentClassAssignment, User
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
from services.school_year_rollover import clean_school_year, create_ggfk_classes_for_year
from services.student_assignments import sync_class_assignment_snapshots
from utils import get_class_or_404


router = APIRouter(tags=["classes"])

# Nursery -> Primary -> Collège, taken from the SchoolLevel enum declaration order.
_SCHOOL_LEVEL_RANK = {level.value: index for index, level in enumerate(SchoolLevel)}


def clean_required_text(value: str, field_name: str) -> str:
    """Trim a required class field through the shared cleaner, raising HTTP 422 if empty.

    Despite the delegated helper name, this does not validate a year format.
    """
    return clean_school_year(value, field_name)


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
    """Return student-count and course-count mappings for the supplied class ids.

    Count nondeleted, academically active students through assignment rows and
    nondeleted courses through their class ids. Missing groups are omitted;
    callers supply zero defaults. No additional school-year predicate is used.
    """
    if not class_ids:
        return {}, {}
    student_rows = db.execute(
        select(StudentClassAssignment.class_id, func.count(Student.id))
        .join(Student, StudentClassAssignment.student_id == Student.id)
        .where(
            StudentClassAssignment.class_id.in_(class_ids),
            Student.deleted_at.is_(None),
            Student.academic_status == "active",
        )
        .group_by(StudentClassAssignment.class_id)
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
    """Serialize a class with supplied student/course counts, defaulting both counts to zero."""
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
    """Return one class summary populated with current assignment and course counts."""
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
    """Return active class summaries and counts for an admin.

    Apply optional exact year and school-level filters, then order by school
    level and sort_order. Student counts exclude graduated and deleted students.
    """
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
    """Create, audit, and commit an admin-supplied class, returning its summary.

    Trim required fields and normalize blank optional text to null. Report
    flush-time integrity failures as HTTP 409; a new class returns zero counts.
    """
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
    """Create missing GGFK catalog classes for an admin-selected school year.

    Skip active classes with matching normalized names, including accent and
    case variants. Return created/skipped names; audit and commit only when
    at least one class is created. Deleted classes are not considered matches.
    """
    school_year = clean_required_text(payload.school_year, "school_year")

    created, skipped = create_ggfk_classes_for_year(db, school_year)

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
            select(Student.id)
            .join(StudentClassAssignment, StudentClassAssignment.student_id == Student.id)
            .where(
                StudentClassAssignment.class_id == school_class.id,
                StudentClassAssignment.school_year == school_class.school_year,
                Student.deleted_at.is_(None),
                Student.academic_status == "active",
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
    """Return enrollment counts for an active class to an admin without writes.

    Use the shared year-scoped plan and return status="empty" when no eligible
    students or courses exist. The write endpoint recomputes this plan.
    """
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
    """Create missing class enrollment pairs for an admin and return created/skipped counts.

    Include nondeleted, academically active students assigned for the class
    year and nondeleted courses matching both class and year. Skip existing
    active pairs; deleted links do not count as existing. Recompute the plan
    on each call, auditing and committing only when new rows are added.
    Return status="empty" when no eligible students or courses exist.
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
    """Return an active class summary and counts to an admin, or raise HTTP 404."""
    school_class = get_class_or_404(db, class_id)
    return _response_with_counts(db, school_class)


@router.patch("/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: UUID,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassResponse:
    """Apply an admin partial class update, synchronize assignments, and return counts.

    Explicit null clears name_en/stream; omitted fields stay unchanged. Update
    assignment years/name snapshots, converting assignment conflicts and flush
    integrity errors to HTTP 409. Audit changed class fields and commit.
    """
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
        sync_class_assignment_snapshots(db, school_class)
        db.flush()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
    """Soft-delete and audit an active class for an admin, commit, and return OK.

    Block deletion when nondeleted students have assignments to the class or
    nondeleted courses reference it. Unlike displayed student counts, this
    guard also includes graduated students with retained assignments.
    """
    school_class = get_class_or_404(db, class_id)
    student_count = db.scalar(
        select(func.count(StudentClassAssignment.id))
        .join(Student, StudentClassAssignment.student_id == Student.id)
        .where(StudentClassAssignment.class_id == class_id, Student.deleted_at.is_(None))
    )
    course_count = db.scalar(
        select(func.count(Course.id)).where(Course.class_id == class_id, Course.deleted_at.is_(None))
    )
    # Retained graduate assignments also protect the class from deletion,
    # even though graduates are omitted from the displayed active-student count.
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
