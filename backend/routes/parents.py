"""Manage parent profiles, active student links, and score-only parent access.

Every parent-facing student lookup requires an active profile, active link, and
active student. Mid-trimester grades expose individual scored items for any
canonical term in the latest school year, never CourseResult averages. Profile
deletion is blocked by active links and invalidates sessions; restoring the
profile does not revive its old JWTs.
"""

import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session, contains_eager, joinedload

from audit import create_audit_log
from auth import get_current_user, hash_password, invalidate_user_sessions, require_admin, require_parent
from constants import TRIMESTER_TERMS
from database import get_db
from models import Class, Course, CourseResult, Enrollment, Grade, GradeItem, Parent, ReportCard, Student, StudentParent, User
from schemas import (
    ParentCreate,
    ParentCreateResponse,
    ParentGradeResponse,
    ParentResponse,
    ParentSelfUpdate,
    ParentUpdate,
    StatusResponse,
    StudentResponse,
    AdminPasswordResetResponse,
)
from services.account_security import reset_profile_password
from services.email_service import send_account_created_email
from services.sms_service import send_account_created_sms
from utils import to_student_response


logger = logging.getLogger(__name__)


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


def get_current_parent_or_404(db: Session, current_user: User) -> Parent:
    parent = db.scalar(select(Parent).where(Parent.user_id == current_user.id, Parent.deleted_at.is_(None)))
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")
    return parent


def ensure_parent_linked_to_active_student(db: Session, parent: Parent, student_id: UUID) -> Student:
    link = db.scalar(
        select(StudentParent)
        .join(StudentParent.student)
        .options(joinedload(StudentParent.student))
        .where(
            StudentParent.parent_id == parent.id,
            StudentParent.student_id == student_id,
            StudentParent.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return link.student


def latest_active_school_year(db: Session) -> str | None:
    year_rows = union_all(
        select(Class.school_year.label("school_year")).where(Class.deleted_at.is_(None)),
        select(Course.school_year.label("school_year")).where(Course.deleted_at.is_(None)),
        select(Course.school_year.label("school_year"))
        .join(CourseResult, CourseResult.course_id == Course.id)
        .join(Student, CourseResult.student_id == Student.id)
        .where(CourseResult.deleted_at.is_(None), Course.deleted_at.is_(None), Student.deleted_at.is_(None)),
        select(ReportCard.school_year.label("school_year"))
        .join(Student, ReportCard.student_id == Student.id)
        .where(ReportCard.deleted_at.is_(None), Student.deleted_at.is_(None)),
    ).subquery()
    return db.scalar(select(func.max(year_rows.c.school_year)).select_from(year_rows))


def latest_enrollment_school_year_for_student(db: Session, student_id: UUID) -> str | None:
    return db.scalar(
        select(func.max(Course.school_year))
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(
            Enrollment.student_id == student_id,
            Enrollment.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
    )


def current_term_for_year(db: Session, school_year: str) -> str:
    activity_terms = union_all(
        select(GradeItem.term.label("term"))
        .join(Course, GradeItem.course_id == Course.id)
        .join(Grade, Grade.grade_item_id == GradeItem.id)
        .join(Student, Grade.student_id == Student.id)
        .where(
            Course.school_year == school_year,
            GradeItem.deleted_at.is_(None),
            Course.deleted_at.is_(None),
            Grade.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        ),
        select(ReportCard.term.label("term"))
        .join(Student, ReportCard.student_id == Student.id)
        .where(
            ReportCard.school_year == school_year,
            ReportCard.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        ),
        select(CourseResult.term.label("term"))
        .join(Course, CourseResult.course_id == Course.id)
        .join(Student, CourseResult.student_id == Student.id)
        .where(
            Course.school_year == school_year,
            CourseResult.deleted_at.is_(None),
            Course.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        ),
    ).subquery()
    terms = set(db.scalars(select(activity_terms.c.term).distinct()).all())
    return next((term for term in reversed(TRIMESTER_TERMS) if term in terms), TRIMESTER_TERMS[0])


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
            logger.warning("Account-created email failed for parent %s: %s", parent.id, exc)
    elif phone:
        try:
            results = send_account_created_sms(name=name, phone=phone, temp_password=temp_password)
            sms_sent = any(result.get("success") for result in results)
        except Exception as exc:
            sms_sent = False
            logger.warning("Account-created SMS failed for parent %s: %s", parent.id, exc)

    return ParentCreateResponse(
        id=parent.id,
        user_id=parent.user_id,
        name=user.name,
        email=user.email,
        phone=parent.phone,
        temp_password=temp_password,
        email_sent=email_sent,
        sms_sent=sms_sent,
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


@router.get("/me/students/{student_id}/grades", response_model=list[ParentGradeResponse])
def list_current_parent_student_grades(
    student_id: UUID,
    term: str | None = None,
    school_year: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_parent),
) -> list[ParentGradeResponse]:
    parent = get_current_parent_or_404(db, current_user)
    ensure_parent_linked_to_active_student(db, parent, student_id)

    if term is not None and term not in TRIMESTER_TERMS:
        raise HTTPException(status_code=422, detail="term must be a canonical trimester")
    school_year = school_year or latest_enrollment_school_year_for_student(db, student_id) or latest_active_school_year(db)
    if school_year is None:
        return []

    selected_term = term or current_term_for_year(db, school_year)

    # Parent mid-trimester access intentionally exposes atomic scores only.
    # Do not join CourseResult or add aggregates here: running averages and
    # rankings become parent-visible only through the approved/sent bulletin
    # pipeline. A withdrawn needs_review bulletin is therefore not replaceable
    # by a live-average back door on this endpoint.
    grades = db.scalars(
        select(Grade)
        .join(Grade.grade_item)
        .join(GradeItem.course)
        .where(
            Grade.student_id == student_id,
            Grade.deleted_at.is_(None),
            GradeItem.deleted_at.is_(None),
            Course.deleted_at.is_(None),
            Course.school_year == school_year,
            GradeItem.term == selected_term,
        )
        .order_by(Grade.updated_at.desc(), Grade.created_at.desc(), Course.name, GradeItem.created_at)
    ).all()

    return [
        ParentGradeResponse(
            course_id=grade.grade_item.course_id,
            course_name=grade.grade_item.course.name,
            grade_item_id=grade.grade_item_id,
            item_title=grade.grade_item.title,
            item_type=grade.grade_item.item_type,
            category=grade.grade_item.category,
            score=grade.score,
            max_score=grade.grade_item.max_score,
            term=grade.grade_item.term,
            school_year=grade.grade_item.course.school_year,
            created_at=grade.created_at,
            updated_at=grade.updated_at,
        )
        for grade in grades
    ]


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


@router.post("/{parent_id}/reset-password", response_model=AdminPasswordResetResponse)
def reset_parent_password(
    parent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> AdminPasswordResetResponse:
    parent = get_parent_or_404(db, parent_id)
    return AdminPasswordResetResponse(
        **reset_profile_password(
            db, profile=parent, actor=current_user, entity_type="parent"
        )
    )


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
    invalidate_user_sessions(user)
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

    students = db.scalars(
        select(Student)
        .join(StudentParent, StudentParent.student_id == Student.id)
        .options(joinedload(Student.school_class))
        .where(
            StudentParent.parent_id == parent_id,
            StudentParent.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
        .distinct()
    ).all()
    return [to_student_response(student) for student in students]
