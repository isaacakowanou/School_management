from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import get_current_user
from database import get_db
from models import Course, GradeItem, User
from schemas import GradeItemCreate, GradeItemResponse, GradeItemUpdate, StatusResponse
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
        term=grade_item.term,
        due_date=grade_item.due_date,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_grade_item_or_404(db: Session, grade_item_id: UUID) -> GradeItem:
    grade_item = db.get(GradeItem, grade_item_id)
    if grade_item is None:
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
        select(GradeItem).where(GradeItem.course_id == course_id).order_by(GradeItem.created_at, GradeItem.title)
    ).all()
    return [to_grade_item_response(grade_item) for grade_item in grade_items]


@router.post("/grade-items", response_model=GradeItemResponse, status_code=status.HTTP_201_CREATED)
def create_grade_item(
    payload: GradeItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeItemResponse:
    title = clean_required_text(payload.title, "title")
    category = clean_required_text(payload.category, "category")
    term = clean_required_text(payload.term, "term")
    validate_grade_item_values(max_score=payload.max_score, weight=payload.weight)
    course = get_course_or_404(db, payload.course_id)
    if not can_manage_course_grade_items(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    grade_item = GradeItem(
        course=course,
        title=title,
        category=category,
        max_score=payload.max_score,
        weight=payload.weight,
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
            "term": grade_item.term,
            "due_date": str(grade_item.due_date) if grade_item.due_date else None,
        },
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
    validate_grade_item_values(max_score=payload.max_score, weight=payload.weight)
    grade_item = get_grade_item_or_404(db, grade_item_id)
    if not can_manage_course_grade_items(db, current_user, grade_item.course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    if payload.title is not None:
        grade_item.title = payload.title
    if payload.category is not None:
        grade_item.category = payload.category
    if payload.max_score is not None:
        grade_item.max_score = payload.max_score
    if payload.weight is not None:
        grade_item.weight = payload.weight
    if payload.term is not None:
        grade_item.term = payload.term
    if payload.due_date is not None:
        grade_item.due_date = payload.due_date

    db.commit()
    db.refresh(grade_item)
    return to_grade_item_response(grade_item)


@router.delete("/grade-items/{grade_item_id}", response_model=StatusResponse)
def delete_grade_item(
    grade_item_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StatusResponse:
    grade_item = get_grade_item_or_404(db, grade_item_id)
    if not can_manage_course_grade_items(db, current_user, grade_item.course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    db.delete(grade_item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Grade item cannot be deleted because related records still exist",
        ) from exc

    return StatusResponse(status="ok", message="Grade item deleted")
