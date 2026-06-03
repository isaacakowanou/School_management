from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, joinedload

from auth import get_current_user, require_admin, require_parent
from database import get_db
from models import Parent, StudentParent, User
from schemas import ParentCreate, ParentResponse, ParentUpdate, StudentResponse
from utils import to_student_response


router = APIRouter(tags=["parents"])


def to_parent_response(parent: Parent) -> ParentResponse:
    return ParentResponse(
        id=parent.id,
        user_id=parent.user_id,
        name=parent.user.name,
        email=parent.user.email,
        phone=parent.phone,
    )


def get_parent_or_404(db: Session, parent_id: UUID) -> Parent:
    parent = db.get(Parent, parent_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")
    return parent


def can_read_parent(current_user: User, parent: Parent) -> bool:
    return current_user.role == "admin" or (
        current_user.role == "parent" and parent.user_id == current_user.id
    )


@router.get("", response_model=list[ParentResponse])
def list_parents(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ParentResponse]:
    parents = db.scalars(
        select(Parent)
        .join(Parent.user)
        .options(contains_eager(Parent.user))
        .order_by(User.name)
    ).all()
    return [to_parent_response(parent) for parent in parents]


@router.post("", response_model=ParentResponse, status_code=status.HTTP_201_CREATED)
def create_parent(
    payload: ParentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ParentResponse:
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role != "parent":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must have parent role")

    existing_parent = db.scalar(select(Parent).where(Parent.user_id == payload.user_id))
    if existing_parent is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parent profile already exists")

    parent = Parent(user=user, phone=payload.phone)
    db.add(parent)
    db.commit()
    db.refresh(parent)
    return to_parent_response(parent)


@router.get("/me", response_model=ParentResponse)
def get_current_parent_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_parent),
) -> ParentResponse:
    parent = db.scalar(select(Parent).where(Parent.user_id == current_user.id))
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")
    return to_parent_response(parent)


@router.get("/{parent_id}", response_model=ParentResponse)
def get_parent(
    parent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ParentResponse:
    parent = get_parent_or_404(db, parent_id)
    if not can_read_parent(current_user, parent):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return to_parent_response(parent)


@router.put("/{parent_id}", response_model=ParentResponse)
def update_parent(
    parent_id: UUID,
    payload: ParentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ParentResponse:
    parent = get_parent_or_404(db, parent_id)
    parent.phone = payload.phone
    db.commit()
    db.refresh(parent)
    return to_parent_response(parent)


@router.get("/{parent_id}/students", response_model=list[StudentResponse])
def list_parent_students(
    parent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StudentResponse]:
    parent = get_parent_or_404(db, parent_id)
    if not can_read_parent(current_user, parent):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    links = db.scalars(
        select(StudentParent)
        .options(joinedload(StudentParent.student))
        .where(StudentParent.parent_id == parent_id)
    ).all()
    return [to_student_response(link.student) for link in links]
