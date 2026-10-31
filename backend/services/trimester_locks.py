"""Provide school-wide write-lock checks for a school year and trimester.

A missing lock row means unlocked; a locked period rejects non-admin writes
and reports whether an admin is overriding. Routes enforce ownership separately
and call the override-audit helper for actual writes in the same transaction.
These helpers do not normalize term text or commit changes.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import create_audit_log
from models import TrimesterLock, User


LOCKED_ERROR_DETAIL = {
    "code": "trimester_locked",
    "message": "Trimester locked by the administration",
}


def get_lock(db: Session, school_year: str, term: str) -> TrimesterLock | None:
    """Return the lock row for the exact school year and term, or None.

    Callers supply the canonical term; this lookup does not normalize it.
    """
    return db.scalar(
        select(TrimesterLock).where(
            TrimesterLock.school_year == school_year,
            TrimesterLock.term == term,
        )
    )


def is_trimester_locked(db: Session, school_year: str, term: str) -> bool:
    """Return whether the exact year/term pair has a locked row; missing means unlocked."""
    lock = get_lock(db, school_year, term)
    return bool(lock and lock.is_locked)


def ensure_trimester_write_allowed(
    db: Session,
    *,
    current_user: User,
    school_year: str,
    term: str,
) -> bool:
    """Reject a non-admin write to the supplied locked year/term with 403.

    Return True for an admin override and False when unlocked. The caller must
    first check role/course ownership and then audit any actual override.
    """
    locked = is_trimester_locked(db, school_year, term)
    if locked and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=LOCKED_ERROR_DETAIL)
    return locked and current_user.role == "admin"


def audit_locked_trimester_override(
    db: Session,
    *,
    current_user: User,
    entity_type: str,
    entity_id: UUID,
    operation: str,
    school_year: str,
    term: str,
) -> None:
    """Stage an override audit row for the supplied actor, target, operation, and period.

    The caller decides whether this was a locked admin write before calling and
    commits the entry with the mutation; this helper does not repeat that check.
    """
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="locked_trimester_override",
        entity_type=entity_type,
        entity_id=entity_id,
        new_value={
            "operation": operation,
            "school_year": school_year,
            "term": term,
            "locked_trimester_override": True,
        },
    )
