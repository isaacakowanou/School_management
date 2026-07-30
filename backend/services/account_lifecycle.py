"""Role-profile and login-account lifecycle invariants.

Parent and teacher profiles own their one-to-one ``User`` login account for
soft-delete and restore purposes. Active email uniqueness is global across all
roles, while employee-number uniqueness is global across active teachers.
Unlinking a parent from a student never changes account state. Restore validates
all identities before mutating any row so a conflict leaves the complete entry
in Corbeille; token versions are deliberately never rolled back on restore.
"""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Parent, Teacher, User


RoleProfile = Parent | Teacher


def active_user_by_email(
    db: Session,
    email: str,
    *,
    exclude_user_id: UUID | None = None,
) -> User | None:
    query = select(User).where(User.email == email, User.deleted_at.is_(None))
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    return db.scalar(query)


def active_teacher_by_employee_number(
    db: Session,
    employee_number: str,
    *,
    exclude_teacher_id: UUID | None = None,
) -> Teacher | None:
    query = select(Teacher).where(
        Teacher.employee_number == employee_number,
        Teacher.deleted_at.is_(None),
    )
    if exclude_teacher_id is not None:
        query = query.where(Teacher.id != exclude_teacher_id)
    return db.scalar(query)


def soft_delete_profile_account(profile: RoleProfile, deleted_at: datetime) -> None:
    profile.deleted_at = deleted_at
    profile.user.deleted_at = deleted_at


def _restore_conflict(code: str, message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


def validate_profile_account_restores(db: Session, profiles: Iterable[RoleProfile]) -> list[RoleProfile]:
    profile_rows = list(profiles)
    for profile in profile_rows:
        email = profile.user.email
        if email and active_user_by_email(db, email, exclude_user_id=profile.user_id) is not None:
            _restore_conflict(
                "restore_email_conflict",
                "This email is already used by an active account.",
            )
        if isinstance(profile, Teacher) and active_teacher_by_employee_number(
            db,
            profile.employee_number,
            exclude_teacher_id=profile.id,
        ) is not None:
            _restore_conflict(
                "restore_employee_number_conflict",
                "This employee number is already used by an active teacher.",
            )
    return profile_rows


def restore_profile_accounts(db: Session, profiles: Iterable[RoleProfile]) -> None:
    profile_rows = validate_profile_account_restores(db, profiles)
    for profile in profile_rows:
        profile.user.deleted_at = None
