"""Compute the admin dashboard's live, soft-delete-aware school summary.

The dashboard uses the shared academic context: current year is the newest
year with classes, while current trimester is the first unlocked trimester for
that year. Counts use SQL aggregates and exclude trashed profiles, students,
classes, courses, and bulletins so cleanup does not leave misleading dashboard
totals.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from auth import require_admin
from constants import TRIMESTER_TERMS
from database import get_db
from models import Class, Parent, ReportCard, Student, Teacher, User
from schemas import AdminStatsBulletins, AdminStatsCurrentTerm, AdminStatsResponse
from services.academic_context import current_school_year, current_term_for_year


router = APIRouter(prefix="/admin", tags=["admin stats"])


def _count_active(db: Session, model) -> int:
    return db.scalar(select(func.count(model.id)).where(model.deleted_at.is_(None))) or 0


def _current_term_response_for_year(db: Session, school_year: str) -> AdminStatsCurrentTerm:
    term = current_term_for_year(db, school_year)
    trimester = TRIMESTER_TERMS.index(term) + 1 if term in TRIMESTER_TERMS else 1
    return AdminStatsCurrentTerm(name=term, trimester=trimester)


def _bulletin_counts(db: Session, school_year: str | None, term: str | None) -> AdminStatsBulletins:
    if school_year is None or term is None:
        return AdminStatsBulletins(generated=0, approved=0, sent=0)

    row = db.execute(
        select(
            func.count(ReportCard.id),
            func.coalesce(func.sum(case((ReportCard.status == "approved", 1), else_=0)), 0),
            func.coalesce(func.sum(case((ReportCard.status == "sent", 1), else_=0)), 0),
        )
        .join(Student, ReportCard.student_id == Student.id)
        .where(
            ReportCard.school_year == school_year,
            ReportCard.term == term,
            ReportCard.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
    ).one()
    return AdminStatsBulletins(generated=row[0] or 0, approved=row[1] or 0, sent=row[2] or 0)


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminStatsResponse:
    school_year = current_school_year(db)
    current_term = _current_term_response_for_year(db, school_year) if school_year is not None else None
    return AdminStatsResponse(
        students=_count_active(db, Student),
        teachers=_count_active(db, Teacher),
        parents=_count_active(db, Parent),
        classes=_count_active(db, Class),
        current_term=current_term,
        bulletins=_bulletin_counts(db, school_year, current_term.name if current_term else None),
    )
