"""Shared active-entity lookups and stable API response adapters.

The lookup helpers intentionally treat soft-deleted rows as absent so callers
cannot accidentally re-expose Corbeille data through an otherwise normal route.
Response adapters centralize relationship-derived labels and default statistics;
they do not authorize access, which remains the owning route's responsibility.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from models import Class, Course, ReportCard, Student, Subject, Teacher, User
from schemas import CourseResponse, StudentResponse


def get_report_card_or_404(db: Session, report_id) -> ReportCard:
    report_card = db.get(ReportCard, report_id)
    if report_card is None or report_card.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")
    return report_card


def get_class_or_404(db: Session, class_id) -> Class:
    school_class = db.get(Class, class_id)
    if school_class is None or school_class.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return school_class


def get_subject_or_404(db: Session, subject_id) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None or subject.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    return subject


def get_current_teacher(db: Session, current_user: User) -> Teacher | None:
    return db.scalar(select(Teacher).where(Teacher.user_id == current_user.id, Teacher.deleted_at.is_(None)))


def to_student_response(student: Student) -> StudentResponse:
    return StudentResponse(
        id=student.id,
        first_name=student.first_name,
        last_name=student.last_name,
        school_level=student.school_level,
        student_number=student.student_number,
        educmaster_number=student.educmaster_number,
        class_id=student.class_id,
        class_name=student.school_class.name_fr if student.school_class else None,
    )


def to_course_response(course: Course, stats: dict | None = None) -> CourseResponse:
    stats = stats or {}
    return CourseResponse(
        id=course.id,
        name=course.name,
        code=course.code,
        teacher_id=course.teacher_id,
        term=course.term,
        school_year=course.school_year,
        language_group=course.language_group,
        class_id=course.class_id,
        class_name=course.school_class.name_fr if course.school_class else None,
        class_school_level=course.school_class.school_level if course.school_class else None,
        subject_id=course.subject_id,
        coefficient=course.coefficient,
        grading_system=course.grading_system,
        student_count=stats.get("student_count", 0),
        grade_item_count=stats.get("grade_item_count", 0),
        filled_score_count=stats.get("filled_score_count", 0),
        possible_score_count=stats.get("possible_score_count", 0),
    )
