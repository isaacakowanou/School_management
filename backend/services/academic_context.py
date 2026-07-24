"""Shared academic year and trimester selection helpers.

Academic views default to the latest school year that has classes and the first
unlocked trimester for that year. Historical data remains reachable by passing
explicit year/term filters; these helpers only choose defaults.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constants import TRIMESTER_TERMS
from models import Class, TrimesterLock


def available_school_years(db: Session) -> list[str]:
    years = db.scalars(
        select(Class.school_year)
        .where(Class.deleted_at.is_(None))
        .distinct()
        .order_by(Class.school_year.desc())
    ).all()
    return list(years)


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
