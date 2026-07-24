"""Fresh class-statistics for the report-card bulletin (A1.7b).

Per language track, the highest and lowest average across the student's class
for a given (term, school_year). Read-only and best-effort — it must never
raise for the PDF path; missing data yields None, which the template renders
as "-".
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ReportCard, Student, StudentClassAssignment
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
    """Return {track: {"highest", "lowest"}} across the student's class.

    Considers every ReportCard for (term, school_year) belonging to a student in
    the same class (including this student's own). Edge cases:
      - student has no class -> all None
      - class of one / no peers with a report yet -> highest == lowest == self
      - a track with no values anywhere -> None / None
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
            ReportCard.deleted_at.is_(None),
        )
    ).all()

    stats = {}
    for track, field in _TRACK_FIELDS.items():
        values = [getattr(report, field) for report in reports if getattr(report, field) is not None]
        stats[track] = {"highest": max(values), "lowest": min(values)} if values else {"highest": None, "lowest": None}
    return stats
