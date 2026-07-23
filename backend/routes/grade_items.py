"""Manage grade-item definitions while protecting grading-mode invariants.

French-track Collège courses use notation béninoise and accept only Interro,
Devoir, and Composition items. Those items have no custom category or weight,
and each trimester has exactly one Devoir and one Composition; allowing foreign
types would make the Ministry formula ambiguous. Non-Beninese courses retain
the legacy weighted-item path and cannot set a Beninese ``item_type``.
Trimester locks protect create/update/delete at the server boundary; admin
overrides keep the ordinary audit event plus a conspicuous override event.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import get_current_user, require_admin
from database import get_db
from models import Course, Grade, GradeItem, User
from schemas import GradeItemCreate, GradeItemResponse, GradeItemType, GradeItemUpdate, StatusResponse
from services.grade_calculator import is_beninese_mode
from services.trimester_locks import (
    audit_locked_trimester_override,
    ensure_trimester_write_allowed,
)
from utils import get_current_teacher


router = APIRouter(tags=["grade-items"])


def to_grade_item_response(grade_item: GradeItem) -> GradeItemResponse:
    return GradeItemResponse(
        id=grade_item.id,
        course_id=grade_item.course_id,
        title=grade_item.title,
        category=grade_item.category,
        max_score=grade_item.max_score,
        weight=grade_item.weight,
        item_type=grade_item.item_type,
        term=grade_item.term,
        due_date=grade_item.due_date,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_grade_item_or_404(db: Session, grade_item_id: UUID) -> GradeItem:
    grade_item = db.get(GradeItem, grade_item_id)
    if grade_item is None or grade_item.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade item not found")
    return grade_item


def can_manage_course_grade_items(db: Session, current_user: User, course: Course) -> bool:
    if current_user.role == "admin":
        return True
    if current_user.role != "teacher":
        return False

    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot be empty",
        )
    return cleaned


def validate_grade_item_values(max_score: float | None = None, weight: float | None = None) -> None:
    if max_score is not None and max_score <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_score must be greater than 0")
    if weight is not None and (weight <= 0 or weight > 1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="weight must be greater than 0 and at most 1")


def get_payload_fields(payload) -> set[str]:
    fields = getattr(payload, "model_fields_set", None)
    if fields is None:
        fields = getattr(payload, "__fields_set__", set())
    return fields


def grade_item_audit_value(grade_item: GradeItem) -> dict:
    return {
        "course_id": grade_item.course_id,
        "title": grade_item.title,
        "category": grade_item.category,
        "max_score": grade_item.max_score,
        "weight": grade_item.weight,
        "item_type": grade_item.item_type,
        "term": grade_item.term,
        "due_date": grade_item.due_date,
    }


@router.get("/courses/{course_id}/grade-items", response_model=list[GradeItemResponse])
def list_grade_items(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GradeItemResponse]:
    course = get_course_or_404(db, course_id)
    if not can_manage_course_grade_items(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    grade_items = db.scalars(
        select(GradeItem)
        .where(GradeItem.course_id == course_id, GradeItem.deleted_at.is_(None))
        .order_by(GradeItem.created_at, GradeItem.title)
    ).all()
    return [to_grade_item_response(grade_item) for grade_item in grade_items]


@router.post("/grade-items", response_model=GradeItemResponse, status_code=status.HTTP_201_CREATED)
def create_grade_item(
    payload: GradeItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeItemResponse:
    term = payload.term.value
    course = get_course_or_404(db, payload.course_id)
    if not can_manage_course_grade_items(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    locked_override = ensure_trimester_write_allowed(
        db,
        current_user=current_user,
        school_year=course.school_year,
        term=term,
    )

    beninese = is_beninese_mode(course)

    # This branch is the product boundary that prevents Homework/Exam/Project
    # categories from entering a Ministry-formula course. Do not relax it to
    # make mixed demo data save successfully; mixed modes cannot be calculated.
    if beninese:
        if payload.item_type is None:
            raise HTTPException(
                status_code=422,
                detail="item_type is required for Beninese-mode courses (INTERRO, DEVOIR, or COMPOSITION)",
            )
        title = clean_required_text(payload.title, "title")
        validate_grade_item_values(max_score=payload.max_score)
        category = None
        weight = None
        item_type = payload.item_type.value

        if payload.item_type in (GradeItemType.DEVOIR, GradeItemType.COMPOSITION):
            # One Devoir / one Composition per trimester (not per course): the
            # course spans the year and each trimester gets its own set.
            existing = db.scalar(
                select(GradeItem).where(
                    GradeItem.course_id == course.id,
                    GradeItem.item_type == payload.item_type.value,
                    GradeItem.term == term,
                    GradeItem.deleted_at.is_(None),
                )
            )
            if existing is not None:
                raise HTTPException(
                    status_code=422,
                    detail=f"This course already has a {payload.item_type.value} for {term}. Only one is allowed per term.",
                )
    else:
        if payload.item_type is not None:
            raise HTTPException(
                status_code=422,
                detail="item_type is only valid for Beninese-mode courses (French section, collège level)",
            )
        if payload.weight is None:
            raise HTTPException(status_code=422, detail="weight is required for weighted-mode courses")
        if payload.category is None:
            raise HTTPException(status_code=422, detail="category is required for weighted-mode courses")
        title = clean_required_text(payload.title, "title")
        category = clean_required_text(payload.category, "category")
        validate_grade_item_values(max_score=payload.max_score, weight=payload.weight)
        weight = payload.weight
        item_type = None

    grade_item = GradeItem(
        course=course,
        title=title,
        category=category,
        max_score=payload.max_score,
        weight=weight,
        item_type=item_type,
        term=term,
        due_date=payload.due_date,
    )
    db.add(grade_item)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_item_created",
        entity_type="grade_item",
        entity_id=grade_item.id,
        old_value=None,
        new_value={
            "course_id": grade_item.course_id,
            "title": grade_item.title,
            "category": grade_item.category,
            "max_score": grade_item.max_score,
            "weight": grade_item.weight,
            "item_type": grade_item.item_type,
            "term": grade_item.term,
            "due_date": str(grade_item.due_date) if grade_item.due_date else None,
        },
    )
    if locked_override:
        audit_locked_trimester_override(
            db,
            current_user=current_user,
            entity_type="grade_item",
            entity_id=grade_item.id,
            operation="grade_item_created",
            school_year=course.school_year,
            term=term,
        )
    db.commit()
    db.refresh(grade_item)
    return to_grade_item_response(grade_item)


@router.put("/grade-items/{grade_item_id}", response_model=GradeItemResponse)
def update_grade_item(
    grade_item_id: UUID,
    payload: GradeItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeItemResponse:
    updated_fields = get_payload_fields(payload)
    grade_item = get_grade_item_or_404(db, grade_item_id)
    if not can_manage_course_grade_items(db, current_user, grade_item.course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    source_term = grade_item.term
    target_term = payload.term.value if payload.term is not None else source_term
    locked_override_terms = {
        term
        for term in {source_term, target_term}
        if ensure_trimester_write_allowed(
            db,
            current_user=current_user,
            school_year=grade_item.course.school_year,
            term=term,
        )
    }

    if payload.item_type is not None:
        raise HTTPException(status_code=422, detail="item_type cannot be changed after creation")

    beninese = is_beninese_mode(grade_item.course)

    if beninese:
        validate_grade_item_values(max_score=payload.max_score)
    else:
        validate_grade_item_values(max_score=payload.max_score, weight=payload.weight)

    old_value = grade_item_audit_value(grade_item)

    if payload.title is not None:
        grade_item.title = clean_required_text(payload.title, "title")
    if not beninese and payload.category is not None:
        grade_item.category = clean_required_text(payload.category, "category")
    if payload.max_score is not None:
        grade_item.max_score = payload.max_score
    if not beninese and payload.weight is not None:
        grade_item.weight = payload.weight
    if payload.term is not None and payload.term.value != grade_item.term:
        # Moving a Devoir/Composition into a term that already has one would
        # break the one-per-term rule the create path enforces.
        if grade_item.item_type in (GradeItemType.DEVOIR.value, GradeItemType.COMPOSITION.value):
            existing = db.scalar(
                select(GradeItem).where(
                    GradeItem.course_id == grade_item.course_id,
                    GradeItem.item_type == grade_item.item_type,
                    GradeItem.term == payload.term.value,
                    GradeItem.id != grade_item.id,
                    GradeItem.deleted_at.is_(None),
                )
            )
            if existing is not None:
                raise HTTPException(
                    status_code=422,
                    detail=f"This course already has a {grade_item.item_type} for {payload.term.value}. Only one is allowed per term.",
                )
        grade_item.term = payload.term.value
    if "due_date" in updated_fields:
        grade_item.due_date = payload.due_date

    new_value = grade_item_audit_value(grade_item)
    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="grade_item_updated",
            entity_type="grade_item",
            entity_id=grade_item.id,
            old_value=old_value,
            new_value=new_value,
        )
        for locked_term in locked_override_terms:
            audit_locked_trimester_override(
                db,
                current_user=current_user,
                entity_type="grade_item",
                entity_id=grade_item.id,
                operation="grade_item_updated",
                school_year=grade_item.course.school_year,
                term=locked_term,
            )

    db.commit()
    db.refresh(grade_item)
    return to_grade_item_response(grade_item)


@router.delete("/grade-items/{grade_item_id}", response_model=StatusResponse)
def delete_grade_item(
    grade_item_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    grade_item = get_grade_item_or_404(db, grade_item_id)
    locked_override = ensure_trimester_write_allowed(
        db,
        current_user=current_user,
        school_year=grade_item.course.school_year,
        term=grade_item.term,
    )
    grade_count = db.scalar(
        select(func.count(Grade.id)).where(Grade.grade_item_id == grade_item_id, Grade.deleted_at.is_(None))
    )
    if grade_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Grade item has submitted grades",
                "grade_count": grade_count,
            },
        )

    old_value = grade_item_audit_value(grade_item)
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_item_deleted",
        entity_type="grade_item",
        entity_id=grade_item.id,
        old_value=old_value,
        new_value=None,
    )
    if locked_override:
        audit_locked_trimester_override(
            db,
            current_user=current_user,
            entity_type="grade_item",
            entity_id=grade_item.id,
            operation="grade_item_deleted",
            school_year=grade_item.course.school_year,
            term=grade_item.term,
        )
    grade_item.deleted_at = func.now()
    db.commit()
    return StatusResponse(status="ok", message="Grade item moved to Trash")
