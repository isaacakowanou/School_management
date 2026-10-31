"""Read current class high/low bulletin values for each language track.

Resolve the student's assignment in the requested year and use non-deleted
approved/sent reports for that class and trimester. Missing assignments or
track values yield None, but database errors propagate rather than being hidden.
These are read-time statistics: stored draft/needs_review rows are excluded,
while derived staleness is not checked.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ReportCard, Student, StudentClassAssignment
from services.annual_averages import ANNUAL_REPORT_STATUSES
from services.student_assignments import assignment_for_student_year


# Report-card track -> the ReportCard column holding that track's average.
_TRACK_FIELDS = {
    "french": "french_average",
    "english": "english_average",
    "bilingual": "bilingual_average",
}


def _empty_stats() -> dict:
    return {track: {"highest": None, "lowest": None} for track in _TRACK_FIELDS}


def compute_class_stats(db: Session, student: Student, term: str, school_year: str) -> dict:
    """Return highest/lowest published track values for the student's assigned class and period.

    Resolve the selected year's assignment and include non-deleted approved/sent
    reports from that class. Stored draft/needs_review rows are excluded; derived
    staleness is not evaluated. Missing assignments or track values yield None;
    database errors propagate. These statistics are computed now, not frozen.
    """
    assignment = assignment_for_student_year(db, student.id, school_year)
    if assignment is None:
        return _empty_stats()

    reports = db.scalars(
        select(ReportCard)
        .join(Student, ReportCard.student_id == Student.id)
        .join(StudentClassAssignment, StudentClassAssignment.student_id == Student.id)
        .where(
            StudentClassAssignment.class_id == assignment.class_id,
            StudentClassAssignment.school_year == school_year,
            Student.deleted_at.is_(None),
            ReportCard.term == term,
            ReportCard.school_year == school_year,
            ReportCard.status.in_(ANNUAL_REPORT_STATUSES),
            ReportCard.deleted_at.is_(None),
        )
    ).all()

    stats = {}
    for track, field in _TRACK_FIELDS.items():
        values = [getattr(report, field) for report in reports if getattr(report, field) is not None]
        stats[track] = {"highest": max(values), "lowest": min(values)} if values else {"highest": None, "lowest": None}
    return stats
