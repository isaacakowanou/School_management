"""Admin-only low-level user account operations beneath role profile workflows.

This router edits active shared ``User`` rows, not teacher/parent profile lifecycle.
Any password assignment passes the universal schema validator and increments
``token_version`` so existing sessions die. Deletion is a guarded hard delete:
database relationships block removal when school/profile records still depend
on the account, which is intentionally distinct from recoverable profile Trash.
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
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
    )


def validate_role(role: str) -> None:
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of: admin, teacher, parent",
        )


def get_user_or_404(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserResponse]:
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
    user = get_user_or_404(db, user_id)
    return to_user_response(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
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
