from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, joinedload

from audit import create_audit_log
from auth import get_current_user, hash_password, require_admin, require_parent
from database import get_db
from models import Parent, Student, StudentParent, User
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


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot be empty",
        )
    return cleaned


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
    current_user: User = Depends(require_admin),
) -> ParentResponse:
    name = clean_required_text(payload.name, "name")
    email = clean_required_text(payload.email, "email")
    password = clean_required_text(payload.password, "password")
    phone = payload.phone.strip() if payload.phone is not None else None
    if phone == "":
        phone = None

    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role="parent",
    )
    parent = Parent(user=user, phone=phone)
    db.add_all([user, parent])
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="parent_created",
        entity_type="parent",
        entity_id=parent.id,
        old_value=None,
        new_value={
            "user_id": parent.user_id,
            "name": user.name,
            "email": user.email,
            "phone": parent.phone,
        },
    )
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
    current_user: User = Depends(require_admin),
) -> ParentResponse:
    parent = get_parent_or_404(db, parent_id)
    updated_fields = getattr(payload, "model_fields_set", None)
    if updated_fields is None:
        updated_fields = getattr(payload, "__fields_set__", set())
    old_value = {
        "user_id": parent.user_id,
        "name": parent.user.name,
        "email": parent.user.email,
        "phone": parent.phone,
    }

    if payload.name is not None:
        parent.user.name = clean_required_text(payload.name, "name")
    if payload.email is not None:
        email = clean_required_text(payload.email, "email")
        existing_user = db.scalar(select(User).where(User.email == email, User.id != parent.user_id))
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        parent.user.email = email
    if "phone" in updated_fields:
        phone = payload.phone.strip() if payload.phone is not None else ""
        parent.phone = phone or None

    new_value = {
        "user_id": parent.user_id,
        "name": parent.user.name,
        "email": parent.user.email,
        "phone": parent.phone,
    }
    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="parent_updated",
            entity_type="parent",
            entity_id=parent.id,
            old_value=old_value,
            new_value=new_value,
        )

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
        .join(StudentParent.student)
        .options(joinedload(StudentParent.student))
        .where(
            StudentParent.parent_id == parent_id,
            Student.deleted_at.is_(None),
        )
    ).all()
    return [to_student_response(link.student) for link in links]
