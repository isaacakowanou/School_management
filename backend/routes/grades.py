"""Persist historical teacher-entered scores and availability notices.

Grades remain attached to the year-scoped course/item context in which they
were recorded; year selectors never reinterpret them through a student's live
class assignment.

Only the assigned teacher (or an admin acting through that course) may write
scores for enrolled students. In batch entry, ``score=null`` means an audited
soft deletion so clearing a cell cannot resurrect an old grade. Notifications
are sent per affected student after the save/recalculation workflow and announce
availability without exposing scores or averages outside the parent portal.
School-year trimester locks are enforced before every actual mutation; admins
retain an audited override while teachers receive ``trimester_locked``.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from auth import get_current_user, require_admin
from audit import create_audit_log
from database import get_db
from models import Course, Enrollment, Grade, GradeItem, Student, Teacher, User
from schemas import (
    GradeBatchSaveRequest,
    GradeBatchSaveResponse,
    GradeCreate,
    GradeNotificationResponse,
    GradeResponse,
    GradeUpdate,
    NotifyGradesPayload,
    StatusResponse,
)
from services.email_service import send_grades_notification
from services.trimester_locks import (
    audit_locked_trimester_override,
    ensure_trimester_write_allowed,
)
from utils import get_current_teacher, historical_class_name_for_course

logger = logging.getLogger(__name__)


router = APIRouter(tags=["grades"])


def to_grade_response(grade: Grade) -> GradeResponse:
    student = grade.student
    course = grade.grade_item.course
    return GradeResponse(
        id=grade.id,
        student_id=grade.student_id,
        student_name=f"{student.first_name} {student.last_name}" if student else None,
        student_number=student.student_number if student else None,
        academic_status=student.academic_status if student else None,
        historical_class_name=historical_class_name_for_course(course),
        grade_item_id=grade.grade_item_id,
        course_id=course.id,
        score=grade.score,
        submitted_by_teacher_id=grade.submitted_by_teacher_id,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def get_grade_item_or_404(db: Session, grade_item_id: UUID) -> GradeItem:
    grade_item = db.get(GradeItem, grade_item_id)
    if grade_item is None or grade_item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade item not found")
    return grade_item


def get_grade_or_404(db: Session, grade_id: UUID) -> Grade:
    grade = db.get(Grade, grade_id)
    if grade is None or grade.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade not found")
    return grade


def can_view_course_grades(db: Session, current_user: User, course: Course) -> bool:
    if current_user.role == "admin":
        return True
    if current_user.role != "teacher":
        return False

    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def get_writable_teacher_for_course(db: Session, current_user: User, course: Course) -> Teacher:
    if current_user.role != "teacher":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    teacher = get_current_teacher(db, current_user)
    if teacher is None or course.teacher_id != teacher.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return teacher


def get_submitter_for_course(db: Session, current_user: User, course: Course) -> Teacher:
    if current_user.role == "admin":
        return course.teacher
    return get_writable_teacher_for_course(db, current_user, course)


def ensure_student_enrolled(db: Session, student_id: UUID, course_id: UUID) -> None:
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
            Enrollment.deleted_at.is_(None),
        )
    )
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student is not enrolled in this course")


def validate_score(score: float, max_score: float) -> None:
    if score < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="score must be greater than or equal to 0")
    if score > max_score:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="score cannot exceed max_score")


def soft_delete_grade(db: Session, *, grade: Grade, current_user: User) -> None:
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_deleted",
        entity_type="grade",
        entity_id=grade.id,
        old_value={
            "student_id": grade.student_id,
            "grade_item_id": grade.grade_item_id,
            "score": grade.score,
            "submitted_by_teacher_id": grade.submitted_by_teacher_id,
        },
    )
    grade.deleted_at = datetime.now(timezone.utc)


@router.post("/courses/{course_id}/notify-grades", response_model=GradeNotificationResponse)
def notify_grades(
    course_id: UUID,
    payload: NotifyGradesPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeNotificationResponse:
    course = get_course_or_404(db, course_id)
    if current_user.role != "admin":
        get_writable_teacher_for_course(db, current_user, course)

    enrolled_ids = set(
        db.scalars(
            select(Enrollment.student_id).where(
                Enrollment.course_id == course_id,
                Enrollment.deleted_at.is_(None),
            )
        ).all()
    )

    # This endpoint follows successful save/recalculation and batches delivery
    # by affected student. It announces availability only; exposing an average
    # here would bypass the approved-bulletin publication boundary.
    summary = {
        "recipients": 0,
        "delivered": {"email": 0, "sms": 0},
        "failed": {"email": 0, "sms": 0},
        "skipped": {"email": 0, "sms": 0},
    }
    for student_id in payload.student_ids:
        if student_id not in enrolled_ids:
            continue
        student = db.get(Student, student_id)
        if student is None or student.deleted_at is not None:
            continue
        try:
            result = send_grades_notification(db, course, student)
            summary["recipients"] += result["recipients"]
            for outcome in ("delivered", "failed", "skipped"):
                for channel in ("email", "sms"):
                    summary[outcome][channel] += result[outcome][channel]
        except Exception as exc:
            logger.warning("Grade notification failed for student %s: %s", student_id, exc)

    if sum(summary["failed"].values()) > 0:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="grade_notifications_failed",
            entity_type="course",
            entity_id=course.id,
            new_value={
                "student_count": len(set(payload.student_ids)),
                **summary,
            },
        )
        db.commit()

    return GradeNotificationResponse(**summary)


@router.post("/courses/{course_id}/grades/batch", response_model=GradeBatchSaveResponse)
def save_course_grades_batch(
    course_id: UUID,
    payload: GradeBatchSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeBatchSaveResponse:
    course = get_course_or_404(db, course_id)
    submitter = get_submitter_for_course(db, current_user, course)

    saved_count = 0
    deleted_count = 0
    skipped_count = 0
    saved_grades: list[Grade] = []

    for entry in payload.entries:
        student = get_student_or_404(db, entry.student_id)
        grade_item = get_grade_item_or_404(db, entry.grade_item_id)
        if grade_item.course_id != course.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Grade item does not belong to this course")
        ensure_student_enrolled(db, student.id, course.id)

        grade = db.scalar(
            select(Grade).where(
                Grade.student_id == student.id,
                Grade.grade_item_id == grade_item.id,
            )
        )

        if entry.score is None:
            if grade is None or grade.deleted_at is not None:
                skipped_count += 1
                continue
            locked_override = ensure_trimester_write_allowed(
                db,
                current_user=current_user,
                school_year=course.school_year,
                term=grade_item.term,
            )
            soft_delete_grade(db, grade=grade, current_user=current_user)
            if locked_override:
                audit_locked_trimester_override(
                    db,
                    current_user=current_user,
                    entity_type="grade",
                    entity_id=grade.id,
                    operation="grade_deleted",
                    school_year=course.school_year,
                    term=grade_item.term,
                )
            deleted_count += 1
            continue

        validate_score(entry.score, grade_item.max_score)
        if grade is None:
            locked_override = ensure_trimester_write_allowed(
                db,
                current_user=current_user,
                school_year=course.school_year,
                term=grade_item.term,
            )
            grade = Grade(
                student=student,
                grade_item=grade_item,
                score=entry.score,
                submitted_by_teacher=submitter,
            )
            db.add(grade)
            db.flush()
            create_audit_log(
                db=db,
                actor_user_id=current_user.id,
                action="grade_submitted",
                entity_type="grade",
                entity_id=grade.id,
                new_value={
                    "student_id": grade.student_id,
                    "grade_item_id": grade.grade_item_id,
                    "score": grade.score,
                    "submitted_by_teacher_id": grade.submitted_by_teacher_id,
                },
            )
            if locked_override:
                audit_locked_trimester_override(
                    db,
                    current_user=current_user,
                    entity_type="grade",
                    entity_id=grade.id,
                    operation="grade_submitted",
                    school_year=course.school_year,
                    term=grade_item.term,
                )
            saved_count += 1
            saved_grades.append(grade)
            continue

        old_score = grade.score
        old_deleted_at = grade.deleted_at
        was_deleted = old_deleted_at is not None
        if not was_deleted and float(old_score) == float(entry.score):
            skipped_count += 1
            saved_grades.append(grade)
            continue

        locked_override = ensure_trimester_write_allowed(
            db,
            current_user=current_user,
            school_year=course.school_year,
            term=grade_item.term,
        )

        grade.score = entry.score
        grade.submitted_by_teacher = submitter
        grade.deleted_at = None
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="grade_submitted" if was_deleted else "grade_updated",
            entity_type="grade",
            entity_id=grade.id,
            old_value={"score": old_score, "deleted_at": old_deleted_at.isoformat()} if was_deleted else {"score": old_score},
            new_value={
                "student_id": grade.student_id,
                "grade_item_id": grade.grade_item_id,
                "score": grade.score,
                "submitted_by_teacher_id": grade.submitted_by_teacher_id,
            },
        )
        if locked_override:
            audit_locked_trimester_override(
                db,
                current_user=current_user,
                entity_type="grade",
                entity_id=grade.id,
                operation="grade_submitted" if was_deleted else "grade_updated",
                school_year=course.school_year,
                term=grade_item.term,
            )
        saved_count += 1
        saved_grades.append(grade)

    db.commit()
    for grade in saved_grades:
        db.refresh(grade)

    return GradeBatchSaveResponse(
        status="ok",
        saved_count=saved_count,
        deleted_count=deleted_count,
        skipped_count=skipped_count,
        grades=[to_grade_response(grade) for grade in saved_grades if grade.deleted_at is None],
    )


@router.get("/courses/{course_id}/grades", response_model=list[GradeResponse])
def list_course_grades(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GradeResponse]:
    course = get_course_or_404(db, course_id)
    if not can_view_course_grades(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    grades = db.scalars(
        select(Grade)
        .join(Grade.grade_item)
        .join(Grade.student)
        .options(contains_eager(Grade.grade_item))
        .where(
            GradeItem.course_id == course_id,
            GradeItem.deleted_at.is_(None),
            Grade.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
        .order_by(Grade.created_at)
    ).all()
    return [to_grade_response(grade) for grade in grades]


@router.post("/grades", response_model=GradeResponse, status_code=status.HTTP_201_CREATED)
def create_grade(
    payload: GradeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeResponse:
    student = get_student_or_404(db, payload.student_id)
    grade_item = get_grade_item_or_404(db, payload.grade_item_id)
    course = grade_item.course
    teacher = get_writable_teacher_for_course(db, current_user, course)
    ensure_trimester_write_allowed(
        db,
        current_user=current_user,
        school_year=course.school_year,
        term=grade_item.term,
    )

    ensure_student_enrolled(db, student.id, course.id)
    validate_score(payload.score, grade_item.max_score)

    existing_grade = db.scalar(
        select(Grade).where(
            Grade.student_id == student.id,
            Grade.grade_item_id == grade_item.id,
            Grade.deleted_at.is_(None),
        )
    )
    if existing_grade is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Grade already exists")

    grade = Grade(
        student=student,
        grade_item=grade_item,
        score=payload.score,
        submitted_by_teacher=teacher,
    )
    db.add(grade)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_submitted",
        entity_type="grade",
        entity_id=grade.id,
        new_value={
            "student_id": grade.student_id,
            "grade_item_id": grade.grade_item_id,
            "score": grade.score,
            "submitted_by_teacher_id": grade.submitted_by_teacher_id,
        },
    )
    db.commit()
    db.refresh(grade)
    return to_grade_response(grade)


@router.put("/grades/{grade_id}", response_model=GradeResponse)
def update_grade(
    grade_id: UUID,
    payload: GradeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeResponse:
    grade = get_grade_or_404(db, grade_id)
    if grade.student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade not found")
    grade_item = grade.grade_item
    get_writable_teacher_for_course(db, current_user, grade_item.course)
    ensure_trimester_write_allowed(
        db,
        current_user=current_user,
        school_year=grade_item.course.school_year,
        term=grade_item.term,
    )

    validate_score(payload.score, grade_item.max_score)
    old_score = grade.score
    grade.score = payload.score
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_updated",
        entity_type="grade",
        entity_id=grade.id,
        old_value={"score": old_score},
        new_value={"score": grade.score},
    )
    db.commit()
    db.refresh(grade)
    return to_grade_response(grade)


@router.delete("/grades/{grade_id}", response_model=StatusResponse)
def delete_grade(
    grade_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    grade = get_grade_or_404(db, grade_id)
    if grade.student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade not found")
    grade_item = grade.grade_item
    locked_override = ensure_trimester_write_allowed(
        db,
        current_user=current_user,
        school_year=grade_item.course.school_year,
        term=grade_item.term,
    )
    soft_delete_grade(db, grade=grade, current_user=current_user)
    if locked_override:
        audit_locked_trimester_override(
            db,
            current_user=current_user,
            entity_type="grade",
            entity_id=grade.id,
            operation="grade_deleted",
            school_year=grade_item.course.school_year,
            term=grade_item.term,
        )
    db.commit()
    return StatusResponse(status="ok", message="Grade moved to Trash")
