import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager, joinedload

from audit import create_audit_log
from auth import get_current_user, hash_password, require_admin, require_parent
from database import get_db
from models import Parent, Student, StudentParent, User
from schemas import ParentCreate, ParentCreateResponse, ParentResponse, ParentSelfUpdate, ParentUpdate, StatusResponse, StudentResponse
from services.email_service import send_account_created_email
from services.sms_service import send_account_created_sms
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
    if parent is None or parent.deleted_at is not None:
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
        .where(Parent.deleted_at.is_(None))
        .order_by(User.name)
    ).all()
    return [to_parent_response(parent) for parent in parents]


@router.post("", response_model=ParentCreateResponse, status_code=status.HTTP_201_CREATED)
def create_parent(
    payload: ParentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ParentCreateResponse:
    name = clean_required_text(payload.name, "name")
    email = (payload.email or "").strip() or None
    phone = payload.phone.strip() if payload.phone is not None else None
    if phone == "":
        phone = None

    if email is not None:
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    temp_password = secrets.token_urlsafe(9)
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(temp_password),
        role="parent",
        must_change_password=True,
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

    if email:
        try:
            send_account_created_email(name=name, to_email=email, temp_password=temp_password)
        except Exception:
            pass
    elif phone:
        try:
            send_account_created_sms(name=name, phone=phone, temp_password=temp_password)
        except Exception:
            pass

    return ParentCreateResponse(
        id=parent.id,
        user_id=parent.user_id,
        name=user.name,
        email=user.email,
        phone=parent.phone,
        temp_password=temp_password,
    )


@router.get("/me", response_model=ParentResponse)
def get_current_parent_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_parent),
) -> ParentResponse:
    parent = db.scalar(select(Parent).where(Parent.user_id == current_user.id, Parent.deleted_at.is_(None)))
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")
    return to_parent_response(parent)


@router.put("/me", response_model=ParentResponse)
def update_current_parent_profile(
    payload: ParentSelfUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_parent),
) -> ParentResponse:
    parent = db.scalar(select(Parent).where(Parent.user_id == current_user.id, Parent.deleted_at.is_(None)))
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")

    updated_fields = payload.model_fields_set
    if payload.name is not None:
        parent.user.name = clean_required_text(payload.name, "name")
    if "phone" in updated_fields:
        phone = payload.phone.strip() if payload.phone is not None else ""
        parent.phone = phone or None

    db.commit()
    db.refresh(parent)
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
    if "email" in payload.model_fields_set:
        email = (payload.email or "").strip() or None
        if email is not None:
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


@router.delete("/{parent_id}", response_model=StatusResponse)
def delete_parent(
    parent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    parent = get_parent_or_404(db, parent_id)
    active_student_count = db.scalar(
        select(func.count(StudentParent.id))
        .join(Student, StudentParent.student_id == Student.id)
        .where(
            StudentParent.parent_id == parent_id,
            StudentParent.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
    )
    if active_student_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Parent is linked to active students",
                "active_student_count": active_student_count,
            },
        )

    stale_links = db.scalars(
        select(StudentParent).where(StudentParent.parent_id == parent_id, StudentParent.deleted_at.is_(None))
    ).all()
    user = parent.user
    old_value = {
        "user_id": parent.user_id,
        "name": user.name,
        "email": user.email,
        "phone": parent.phone,
        "removed_inactive_student_link_count": len(stale_links),
    }
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="parent_deleted",
        entity_type="parent",
        entity_id=parent.id,
        old_value=old_value,
        new_value=None,
    )
    deleted_at = datetime.now(timezone.utc)
    for link in stale_links:
        link.deleted_at = deleted_at
    parent.deleted_at = deleted_at
    db.commit()
    return StatusResponse(status="ok", message="Parent moved to Trash")


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
        .options(joinedload(StudentParent.student).joinedload(Student.school_class))
        .where(
            StudentParent.parent_id == parent_id,
            StudentParent.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
    ).all()
    return [to_student_response(link.student) for link in links]
