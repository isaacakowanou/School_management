"""Expose current trimester lock state and audited admin-only toggles.

The lock is global for a school year, not class-specific. Teachers may read
state for their course UI; only admins can deliberately lock or unlock it.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import get_current_user, require_admin
from constants import TRIMESTER_TERMS
from database import get_db
from models import TrimesterLock, User
from schemas import TrimesterLockResponse, TrimesterLockUpdate
from services.trimester_locks import get_lock


router = APIRouter(tags=["trimester locks"])


def _response(lock: TrimesterLock | None, school_year: str, term: str) -> TrimesterLockResponse:
    if lock is None:
        return TrimesterLockResponse(school_year=school_year, term=term, is_locked=False)
    return TrimesterLockResponse(
        id=lock.id,
        school_year=lock.school_year,
        term=lock.term,
        is_locked=lock.is_locked,
        updated_by_admin_id=lock.updated_by_admin_id,
        locked_at=lock.locked_at,
        updated_at=lock.updated_at,
    )


@router.get("/trimester-locks", response_model=list[TrimesterLockResponse])
def list_trimester_locks(
    school_year: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TrimesterLockResponse]:
    if current_user.role not in {"admin", "teacher"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    cleaned_year = school_year.strip()
    if not cleaned_year:
        raise HTTPException(status_code=422, detail="school_year cannot be empty")
    return [_response(get_lock(db, cleaned_year, term), cleaned_year, term) for term in TRIMESTER_TERMS]


@router.put("/trimester-locks", response_model=TrimesterLockResponse)
def update_trimester_lock(
    payload: TrimesterLockUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TrimesterLockResponse:
    school_year = payload.school_year.strip()
    if not school_year:
        raise HTTPException(status_code=422, detail="school_year cannot be empty")
    term = payload.term.value
    lock = get_lock(db, school_year, term)
    old_locked = bool(lock and lock.is_locked)
    now = datetime.now(timezone.utc)
    if lock is None:
        lock = TrimesterLock(school_year=school_year, term=term)
        db.add(lock)
        db.flush()

    lock.is_locked = payload.is_locked
    lock.updated_by_admin_id = current_user.id
    lock.locked_at = now if payload.is_locked else None
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="trimester_locked" if payload.is_locked else "trimester_unlocked",
        entity_type="trimester_lock",
        entity_id=lock.id,
        old_value={"school_year": school_year, "term": term, "is_locked": old_locked},
        new_value={
            "school_year": school_year,
            "term": term,
            "is_locked": payload.is_locked,
            "state_changed": old_locked != payload.is_locked,
        },
    )
    db.commit()
    db.refresh(lock)
    return _response(lock, school_year, term)
