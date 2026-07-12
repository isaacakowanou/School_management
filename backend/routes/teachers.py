"""Manage teacher profiles, generated credentials, and assigned-course visibility.

Teacher creation uses a temporary forced-change credential and reports delivery
outcomes to the admin. Self-read access is limited to the matching profile;
course lists exclude trashed courses. Deletion is blocked while active courses
or submitted academic data depend on the teacher and invalidates existing JWTs.
"""

import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager, joinedload

from audit import create_audit_log
from auth import get_current_user, hash_password, invalidate_user_sessions, require_admin
from database import get_db
from models import Course, Grade, Teacher, User
from schemas import AdminPasswordResetResponse, CourseResponse, StatusResponse, TeacherCreate, TeacherCreateResponse, TeacherResponse, TeacherUpdate
from services.account_security import reset_profile_password
from services.email_service import send_account_created_email
from services.sms_service import send_account_created_sms
from utils import to_course_response


logger = logging.getLogger(__name__)

router = APIRouter(tags=["teachers"])


def to_teacher_response(teacher: Teacher) -> TeacherResponse:
    return TeacherResponse(
        id=teacher.id,
        user_id=teacher.user_id,
        name=teacher.user.name,
        email=teacher.user.email,
        phone=teacher.phone,
        employee_number=teacher.employee_number,
    )


def get_teacher_or_404(db: Session, teacher_id: UUID) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if teacher is None or teacher.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    return teacher


def can_read_teacher(current_user: User, teacher: Teacher) -> bool:
    return current_user.role == "admin" or (
        current_user.role == "teacher" and teacher.user_id == current_user.id
    )


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot be empty",
        )
    return cleaned


def generate_employee_number(db: Session, year: int) -> str:
    prefix = f"TCH-{year}-"
    last = db.scalar(
        select(Teacher.employee_number)
        .where(Teacher.employee_number.like(f"{prefix}%"))
        .order_by(Teacher.employee_number.desc())
        .limit(1)
    )
    try:
        n = int(last[len(prefix):]) + 1 if last else 1
    except (ValueError, TypeError):
        n = 1
    while True:
        candidate = f"{prefix}{n:04d}"
        if not db.scalar(select(Teacher).where(Teacher.employee_number == candidate)):
            return candidate
        n += 1


@router.get("", response_model=list[TeacherResponse])
def list_teachers(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[TeacherResponse]:
    teachers = db.scalars(
        select(Teacher)
        .join(Teacher.user)
        .options(contains_eager(Teacher.user))
        .where(Teacher.deleted_at.is_(None))
        .order_by(User.name)
    ).all()
    return [to_teacher_response(teacher) for teacher in teachers]


@router.post("", response_model=TeacherCreateResponse, status_code=status.HTTP_201_CREATED)
def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TeacherCreateResponse:
    name = clean_required_text(payload.name, "name")
    email = (payload.email or "").strip() or None
    phone = (payload.phone or "").strip() or None

    if email is not None:
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    raw_number = (payload.employee_number or "").strip()
    if raw_number:
        existing_employee_number = db.scalar(
            select(Teacher).where(Teacher.employee_number == raw_number)
        )
        if existing_employee_number is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee number already exists")
        employee_number = raw_number
    else:
        employee_number = generate_employee_number(db, datetime.now(timezone.utc).year)

    temp_password = secrets.token_urlsafe(9)
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(temp_password),
        role="teacher",
        must_change_password=True,
    )
    teacher = Teacher(user=user, employee_number=employee_number, phone=phone)
    db.add_all([user, teacher])
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="teacher_created",
        entity_type="teacher",
        entity_id=teacher.id,
        old_value=None,
        new_value={
            "user_id": teacher.user_id,
            "name": user.name,
            "email": user.email,
            "phone": teacher.phone,
            "employee_number": teacher.employee_number,
        },
    )
    db.commit()
    db.refresh(teacher)

    # Notification outcome is surfaced to the admin (email_sent / sms_sent)
    # so a failed send is visible and the temp password gets handed over
    # directly instead of silently never arriving.
    email_sent: bool | None = None
    sms_sent: bool | None = None
    if email:
        try:
            email_sent = bool(send_account_created_email(name=name, to_email=email, temp_password=temp_password).get("success"))
        except Exception as exc:
            email_sent = False
            logger.warning("Account-created email failed for teacher %s: %s", teacher.id, exc)
    elif phone:
        try:
            results = send_account_created_sms(name=name, phone=phone, temp_password=temp_password)
            sms_sent = any(result.get("success") for result in results)
        except Exception as exc:
            sms_sent = False
            logger.warning("Account-created SMS failed for teacher %s: %s", teacher.id, exc)

    return TeacherCreateResponse(
        id=teacher.id,
        user_id=teacher.user_id,
        name=user.name,
        email=user.email,
        phone=teacher.phone,
        employee_number=teacher.employee_number,
        temp_password=temp_password,
        email_sent=email_sent,
        sms_sent=sms_sent,
    )


@router.get("/{teacher_id}", response_model=TeacherResponse)
def get_teacher(
    teacher_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TeacherResponse:
    teacher = get_teacher_or_404(db, teacher_id)
    if not can_read_teacher(current_user, teacher):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return to_teacher_response(teacher)


@router.put("/{teacher_id}", response_model=TeacherResponse)
def update_teacher(
    teacher_id: UUID,
    payload: TeacherUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TeacherResponse:
    teacher = get_teacher_or_404(db, teacher_id)
    old_value = {
        "user_id": teacher.user_id,
        "name": teacher.user.name,
        "email": teacher.user.email,
        "phone": teacher.phone,
        "employee_number": teacher.employee_number,
    }

    if payload.name is not None:
        teacher.user.name = clean_required_text(payload.name, "name")
    if "email" in payload.model_fields_set:
        email = (payload.email or "").strip() or None
        if email is not None:
            existing_user = db.scalar(select(User).where(User.email == email, User.id != teacher.user_id))
            if existing_user is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        teacher.user.email = email
    if "phone" in payload.model_fields_set:
        teacher.phone = (payload.phone or "").strip() or None
    if payload.employee_number is not None:
        employee_number = clean_required_text(payload.employee_number, "employee_number")
        existing_teacher = db.scalar(
            select(Teacher).where(
                Teacher.employee_number == employee_number,
                Teacher.id != teacher_id,
            )
        )
        if existing_teacher is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee number already exists")
        teacher.employee_number = employee_number

    new_value = {
        "user_id": teacher.user_id,
        "name": teacher.user.name,
        "email": teacher.user.email,
        "phone": teacher.phone,
        "employee_number": teacher.employee_number,
    }
    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="teacher_updated",
            entity_type="teacher",
            entity_id=teacher.id,
            old_value=old_value,
            new_value=new_value,
        )

    db.commit()
    db.refresh(teacher)
    return to_teacher_response(teacher)


@router.post("/{teacher_id}/reset-password", response_model=AdminPasswordResetResponse)
def reset_teacher_password(
    teacher_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> AdminPasswordResetResponse:
    teacher = get_teacher_or_404(db, teacher_id)
    return AdminPasswordResetResponse(
        **reset_profile_password(
            db, profile=teacher, actor=current_user, entity_type="teacher"
        )
    )


@router.delete("/{teacher_id}", response_model=StatusResponse)
def delete_teacher(
    teacher_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    teacher = get_teacher_or_404(db, teacher_id)
    course_count = db.scalar(
        select(func.count(Course.id)).where(Course.teacher_id == teacher_id, Course.deleted_at.is_(None))
    )
    submitted_grade_count = db.scalar(
        select(func.count(Grade.id)).where(Grade.submitted_by_teacher_id == teacher_id, Grade.deleted_at.is_(None))
    )
    if course_count or submitted_grade_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Teacher has courses or submitted grades",
                "course_count": course_count,
                "submitted_grade_count": submitted_grade_count,
            },
        )

    user = teacher.user
    old_value = {
        "user_id": teacher.user_id,
        "name": user.name,
        "email": user.email,
        "employee_number": teacher.employee_number,
    }
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="teacher_deleted",
        entity_type="teacher",
        entity_id=teacher.id,
        old_value=old_value,
        new_value=None,
    )
    teacher.deleted_at = datetime.now(timezone.utc)
    invalidate_user_sessions(user)
    db.commit()
    return StatusResponse(status="ok", message="Teacher moved to Trash")


@router.get("/{teacher_id}/courses", response_model=list[CourseResponse])
def list_teacher_courses(
    teacher_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseResponse]:
    teacher = get_teacher_or_404(db, teacher_id)
    if not can_read_teacher(current_user, teacher):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    courses = db.scalars(
        select(Course)
        .options(joinedload(Course.school_class))
        .where(Course.teacher_id == teacher_id, Course.deleted_at.is_(None))
        .order_by(Course.name)
    ).all()
    return [to_course_response(course) for course in courses]
