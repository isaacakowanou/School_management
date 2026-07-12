"""Manage the bilingual subject catalog that constrains course setup.

``applicable_classes=null`` deliberately means every class in a level group;
an empty list is rejected because it would be ambiguous. Class-name matching is
taxonomy-normalized, and subjects with active courses cannot be deleted. Safe
deletion is recoverable so catalog references remain available to Trash.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import require_admin
from constants import level_group_for_class_name, normalize_class_name
from database import get_db
from models import Course, Subject, User
from schemas import (
    LanguageGroup,
    StatusResponse,
    SubjectCreate,
    SubjectLevelGroup,
    SubjectResponse,
    SubjectUpdate,
)
from utils import get_class_or_404, get_subject_or_404


router = APIRouter(tags=["subjects"])

# Nursery -> Primary -> Collège 1er cycle -> 2nd cycle, from enum declaration order.
_LEVEL_GROUP_RANK = {group.value: index for index, group in enumerate(SubjectLevelGroup)}


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{field_name} cannot be empty")
    return cleaned


def _clean_applicable_classes(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    cleaned = [name.strip() for name in value if name.strip()]
    if not cleaned:
        raise HTTPException(status_code=422, detail="applicable_classes cannot be empty; send null for the whole level group")
    return cleaned


def _subject_snapshot(subject: Subject) -> dict:
    return {
        "name_fr": subject.name_fr,
        "name_en": subject.name_en,
        "section": subject.section,
        "level_group": subject.level_group,
        "sort_order": subject.sort_order,
        "applicable_classes": subject.applicable_classes,
    }


def _course_counts(db: Session, subject_ids: list[UUID]) -> dict:
    if not subject_ids:
        return {}
    rows = db.execute(
        select(Course.subject_id, func.count(Course.id))
        .where(Course.subject_id.in_(subject_ids), Course.deleted_at.is_(None))
        .group_by(Course.subject_id)
    ).all()
    return dict(rows)


def to_subject_response(subject: Subject, *, course_count: int = 0) -> SubjectResponse:
    return SubjectResponse(
        id=subject.id,
        name_fr=subject.name_fr,
        name_en=subject.name_en,
        section=subject.section,
        level_group=subject.level_group,
        sort_order=subject.sort_order,
        applicable_classes=subject.applicable_classes,
        course_count=course_count,
    )


_DUPLICATE_DETAIL = "A subject with this French name already exists in this level group and section"


@router.get("", response_model=list[SubjectResponse])
def list_subjects(
    section: LanguageGroup | None = None,
    level_group: SubjectLevelGroup | None = None,
    class_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SubjectResponse]:
    query = select(Subject).where(Subject.deleted_at.is_(None))
    if section is not None:
        query = query.where(Subject.section == section.value)
    if level_group is not None:
        query = query.where(Subject.level_group == level_group.value)

    subjects = list(db.scalars(query).all())

    if class_id is not None:
        school_class = get_class_or_404(db, class_id)
        # Both sides are matched accent/case-insensitively: class rows are
        # admin-typed ("6eme"), the taxonomy and applicable_classes are
        # canonical ("6ème"). A class named outside the locked taxonomy has no
        # catalog subjects.
        class_level_group = level_group_for_class_name(school_class.name_fr)
        class_name_key = normalize_class_name(school_class.name_fr)
        subjects = [
            s
            for s in subjects
            if s.level_group == class_level_group
            and (
                s.applicable_classes is None
                or class_name_key in {normalize_class_name(name) for name in s.applicable_classes}
            )
        ]

    # Bulletin order: level group, French section first, then sort_order.
    subjects.sort(
        key=lambda s: (_LEVEL_GROUP_RANK.get(s.level_group, 99), s.section != "FRENCH", s.sort_order)
    )

    course_counts = _course_counts(db, [s.id for s in subjects])
    return [to_subject_response(s, course_count=course_counts.get(s.id, 0)) for s in subjects]


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def create_subject(
    payload: SubjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SubjectResponse:
    subject = Subject(
        name_fr=clean_required_text(payload.name_fr, "name_fr"),
        name_en=clean_required_text(payload.name_en, "name_en"),
        section=payload.section.value,
        level_group=payload.level_group.value,
        sort_order=payload.sort_order,
        applicable_classes=_clean_applicable_classes(payload.applicable_classes),
    )
    db.add(subject)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from exc

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="subject_created",
        entity_type="subject",
        entity_id=subject.id,
        old_value=None,
        new_value=_subject_snapshot(subject),
    )
    db.commit()
    db.refresh(subject)
    return to_subject_response(subject)


@router.get("/{subject_id}", response_model=SubjectResponse)
def get_subject(
    subject_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> SubjectResponse:
    subject = get_subject_or_404(db, subject_id)
    course_counts = _course_counts(db, [subject.id])
    return to_subject_response(subject, course_count=course_counts.get(subject.id, 0))


@router.patch("/{subject_id}", response_model=SubjectResponse)
def update_subject(
    subject_id: UUID,
    payload: SubjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SubjectResponse:
    subject = get_subject_or_404(db, subject_id)
    old_value = _subject_snapshot(subject)

    if payload.name_fr is not None:
        subject.name_fr = clean_required_text(payload.name_fr, "name_fr")
    if payload.name_en is not None:
        subject.name_en = clean_required_text(payload.name_en, "name_en")
    if payload.section is not None:
        subject.section = payload.section.value
    if payload.level_group is not None:
        subject.level_group = payload.level_group.value
    if payload.sort_order is not None:
        subject.sort_order = payload.sort_order
    # applicable_classes is nullable: an explicit null widens the subject to the
    # whole level group; an omitted key leaves the value unchanged.
    if "applicable_classes" in payload.model_fields_set:
        subject.applicable_classes = _clean_applicable_classes(payload.applicable_classes)

    new_value = _subject_snapshot(subject)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_DETAIL) from exc

    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="subject_updated",
            entity_type="subject",
            entity_id=subject.id,
            old_value=old_value,
            new_value=new_value,
        )
    db.commit()
    db.refresh(subject)
    course_counts = _course_counts(db, [subject.id])
    return to_subject_response(subject, course_count=course_counts.get(subject.id, 0))


@router.delete("/{subject_id}", response_model=StatusResponse)
def delete_subject(
    subject_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    subject = get_subject_or_404(db, subject_id)
    course_count = db.scalar(
        select(func.count(Course.id)).where(Course.subject_id == subject_id, Course.deleted_at.is_(None))
    )
    if course_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Subject has courses referencing it",
                "course_count": course_count,
            },
        )

    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="subject_deleted",
        entity_type="subject",
        entity_id=subject.id,
        old_value=_subject_snapshot(subject),
        new_value=None,
    )
    subject.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return StatusResponse(status="ok", message="Subject moved to Trash")
