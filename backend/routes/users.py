"""Admin-only low-level user account operations beneath role profile workflows.

This router edits active shared ``User`` rows, not teacher/parent profile lifecycle.
Supplied passwords pass schema validation and are hashed. Updating a password
increments ``token_version`` to invalidate existing sessions; account creation
uses model defaults. Hard deletion reports database integrity failures as
conflicts and does not use the recoverable profile Trash workflow.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import hash_password, invalidate_user_sessions, require_admin
from database import get_db
from models import User
from schemas import StatusResponse, UserCreate, UserResponse, UserUpdate
from services.account_lifecycle import active_user_by_email


router = APIRouter(tags=["users"])

VALID_ROLES = {"admin", "teacher", "parent"}


def to_user_response(user: User) -> UserResponse:
    """Return public identity fields from a user row without exposing credential fields."""
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
    )


def validate_role(role: str) -> None:
    """Accept admin, teacher, or parent; raise HTTP 400 for any other role string."""
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of: admin, teacher, parent",
        )


def get_user_or_404(db: Session, user_id: UUID) -> User:
    """Return an active user by id from db, or raise HTTP 404 for missing/deleted rows."""
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserResponse]:
    """Return active account summaries to an admin, ordered by creation time and email."""
    users = db.scalars(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at, User.email)
    ).all()
    return [to_user_response(user) for user in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
    """Create and commit a schema-validated account for an admin, returning its summary.

    Validate the role and reject an email already used by an active account.
    Hash the supplied password; this route creates no teacher or parent profile
    and sends no account notification.
    """
    validate_role(payload.role)

    existing_user = active_user_by_email(db, payload.email)
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_user_response(user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
    """Return an active account summary to an admin, or raise HTTP 404."""
    user = get_user_or_404(db, user_id)
    return to_user_response(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
    """Apply non-null account fields for an admin, commit, and return the refreshed summary.

    Validate supplied roles and active-email uniqueness. A supplied password is
    hashed and invalidates existing sessions; other edits do not bump the token
    version here. This route does not synchronize role-specific profiles.
    """
    user = get_user_or_404(db, user_id)

    if payload.role is not None:
        validate_role(payload.role)
        user.role = payload.role
    if payload.name is not None:
        user.name = payload.name
    if payload.email is not None:
        existing_user = active_user_by_email(db, payload.email, exclude_user_id=user_id)
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        user.email = payload.email
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        # A password replacement revokes sessions issued for the old credential.
        invalidate_user_sessions(user)

    db.commit()
    db.refresh(user)
    return to_user_response(user)


@router.delete("/{user_id}", response_model=StatusResponse)
def delete_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StatusResponse:
    """Hard-delete an active account for an admin and return OK after committing.

    Roll back database integrity failures and return HTTP 409 for remaining
    references. This route does not perform recoverable profile deletion,
    explicit self-deletion checks, or the shared Trash account cleanup.
    """
    user = get_user_or_404(db, user_id)
    db.delete(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User cannot be deleted because related records still exist",
        ) from exc

    return StatusResponse(status="ok", message="User deleted")
