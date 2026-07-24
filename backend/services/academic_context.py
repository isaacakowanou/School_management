"""Shared academic year and trimester selection helpers.

``available_school_years`` is the broad selector source: any year with classes,
courses, report cards, enrollments, or student assignments must remain
reachable. ``current_school_year``
is intentionally narrower: only a year with classes can become current, so a
course-only partial setup does not move the live app into that year.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constants import TRIMESTER_TERMS
from models import Class, Course, Enrollment, ReportCard, Student, StudentClassAssignment, TrimesterLock


def available_school_years(db: Session) -> list[str]:
    years = set(
        db.scalars(select(Class.school_year).where(Class.deleted_at.is_(None))).all()
    )
    years.update(
        db.scalars(select(Course.school_year).where(Course.deleted_at.is_(None))).all()
    )
    years.update(db.scalars(select(StudentClassAssignment.school_year)).all())
    years.update(
        db.scalars(
            select(ReportCard.school_year)
            .join(Student, ReportCard.student_id == Student.id)
            .where(ReportCard.deleted_at.is_(None), Student.deleted_at.is_(None))
        ).all()
    )
    years.update(
        db.scalars(
            select(Course.school_year)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.deleted_at.is_(None))
        ).all()
    )
    return sorted((year for year in years if year), reverse=True)


def current_school_year(db: Session) -> str | None:
    return db.scalar(select(func.max(Class.school_year)).where(Class.deleted_at.is_(None)))


def current_term_for_year(db: Session, school_year: str) -> str:
    locked_terms = set(
        db.scalars(
            select(TrimesterLock.term).where(
                TrimesterLock.school_year == school_year,
                TrimesterLock.is_locked.is_(True),
            )
        ).all()
    )
    return next((term for term in TRIMESTER_TERMS if term not in locked_terms), TRIMESTER_TERMS[-1])
