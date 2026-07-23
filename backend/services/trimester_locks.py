"""Enforce school-wide trimester write locks at the backend boundary.

Locks are keyed by school year and canonical trimester. Missing state means
unlocked. Teachers are rejected before a grade or grade-item mutation; admins
may override, but every actual override receives a separate conspicuous audit
row in the caller's transaction in addition to the ordinary mutation audit.
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
    return db.scalar(
        select(TrimesterLock).where(
            TrimesterLock.school_year == school_year,
            TrimesterLock.term == term,
        )
    )


def is_trimester_locked(db: Session, school_year: str, term: str) -> bool:
    lock = get_lock(db, school_year, term)
    return bool(lock and lock.is_locked)


def ensure_trimester_write_allowed(
    db: Session,
    *,
    current_user: User,
    school_year: str,
    term: str,
) -> bool:
    """Reject a locked teacher write and return whether an admin is overriding."""
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
