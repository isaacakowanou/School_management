"""Keep login accounts and parent/teacher profile deletion states coordinated.

Email uniqueness spans active users of every role; employee-number uniqueness
spans active teachers, and unlinking a child does not release either identity.
Restore checks active-row conflicts before clearing linked User deletion markers;
the caller restores profile rows and commits both together.
Restore never rolls token_version back, so previously revoked sessions stay dead.
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
    """Return the active account with this exact email, or None.

    An optional excluded user ID allows edits to keep their own email. Deleted
    accounts do not reserve email addresses, and this check spans all roles.
    """
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
    """Return the active teacher using this employee number, or None.

    Exclude the supplied teacher ID during edits; deleted profiles do not reserve
    employee numbers.
    """
    query = select(Teacher).where(
        Teacher.employee_number == employee_number,
        Teacher.deleted_at.is_(None),
    )
    if exclude_teacher_id is not None:
        query = query.where(Teacher.id != exclude_teacher_id)
    return db.scalar(query)


def soft_delete_profile_account(profile: RoleProfile, deleted_at: datetime) -> None:
    """Mark a parent/teacher profile and its linked user deleted at the given time.

    This stages changes only. Session-version invalidation and committing remain
    the caller's responsibility; unlinking a child must not call this helper.
    """
    profile.deleted_at = deleted_at
    profile.user.deleted_at = deleted_at


def _restore_conflict(code: str, message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


def validate_profile_account_restores(db: Session, profiles: Iterable[RoleProfile]) -> list[RoleProfile]:
    """Return the profiles after checking their emails and employee numbers for conflicts.

    Compare each against active database rows before restoration. A conflict raises
    409 without restoring anything; this helper does not commit.
    """
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
    """Validate the profiles and clear deletion markers on their linked user accounts.

    The caller restores the profile rows themselves and commits the transaction.
    Token versions are deliberately unchanged so previously revoked JWTs stay dead.
    """
    profile_rows = validate_profile_account_restores(db, profiles)
    for profile in profile_rows:
        profile.user.deleted_at = None
