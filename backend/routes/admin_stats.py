from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select, union_all
from sqlalchemy.orm import Session

from auth import require_admin
from constants import TRIMESTER_TERMS
from database import get_db
from models import Class, Course, CourseResult, Grade, GradeItem, Parent, ReportCard, Student, Teacher, User
from schemas import AdminStatsBulletins, AdminStatsCurrentTerm, AdminStatsResponse


router = APIRouter(prefix="/admin", tags=["admin stats"])


def _count_active(db: Session, model) -> int:
    return db.scalar(select(func.count(model.id)).where(model.deleted_at.is_(None))) or 0


def _latest_active_school_year(db: Session) -> str | None:
    year_rows = union_all(
        select(Class.school_year.label("school_year")).where(Class.deleted_at.is_(None)),
        select(Course.school_year.label("school_year")).where(Course.deleted_at.is_(None)),
        select(ReportCard.school_year.label("school_year"))
        .join(Student, ReportCard.student_id == Student.id)
        .where(ReportCard.deleted_at.is_(None), Student.deleted_at.is_(None)),
    ).subquery()
    return db.scalar(select(func.max(year_rows.c.school_year)).select_from(year_rows))


def _current_term_for_year(db: Session, school_year: str) -> AdminStatsCurrentTerm:
    # There is no persisted current-term table. A1.7c stores canonical trimester
    # values in term-bearing tables, so pick the latest canonical term with real
    # grade/report activity for the latest active school year.
    activity_terms = union_all(
        select(GradeItem.term.label("term"))
        .join(Course, GradeItem.course_id == Course.id)
        .join(Grade, Grade.grade_item_id == GradeItem.id)
        .join(Student, Grade.student_id == Student.id)
        .where(
            Course.school_year == school_year,
            GradeItem.deleted_at.is_(None),
            Course.deleted_at.is_(None),
            Grade.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        ),
        select(CourseResult.term.label("term"))
        .join(Course, CourseResult.course_id == Course.id)
        .join(Student, CourseResult.student_id == Student.id)
        .where(
            Course.school_year == school_year,
            CourseResult.deleted_at.is_(None),
            Course.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        ),
        select(ReportCard.term.label("term"))
        .join(Student, ReportCard.student_id == Student.id)
        .where(
            ReportCard.school_year == school_year,
            ReportCard.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        ),
    ).subquery()
    terms = set(db.scalars(select(activity_terms.c.term).distinct()).all())
    latest_term = next((term for term in reversed(TRIMESTER_TERMS) if term in terms), TRIMESTER_TERMS[0])
    return AdminStatsCurrentTerm(name=latest_term, trimester=TRIMESTER_TERMS.index(latest_term) + 1)


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
    school_year = _latest_active_school_year(db)
    current_term = _current_term_for_year(db, school_year) if school_year is not None else None
    return AdminStatsResponse(
        students=_count_active(db, Student),
        teachers=_count_active(db, Teacher),
        parents=_count_active(db, Parent),
        classes=_count_active(db, Class),
        current_term=current_term,
        bulletins=_bulletin_counts(db, school_year, current_term.name if current_term else None),
    )
