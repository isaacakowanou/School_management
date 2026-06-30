from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import create_audit_log
from auth import get_current_user, require_admin
from database import get_db
from models import Course, Teacher, User
from schemas import CourseCreate, CourseResponse, CourseUpdate, StatusResponse
from utils import get_current_teacher, to_course_response


router = APIRouter(tags=["courses"])


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_teacher_or_404(db: Session, teacher_id: UUID) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    return teacher


def teacher_can_read_course(db: Session, current_user: User, course: Course) -> bool:
    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def ensure_unique_course_code(db: Session, code: str, course_id: UUID | None = None) -> None:
    query = select(Course).where(Course.code == code)
    if course_id is not None:
        query = query.where(Course.id != course_id)

    existing_course = db.scalar(query)
    if existing_course is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course code already exists")


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot be empty",
        )
    return cleaned


@router.get("", response_model=list[CourseResponse])
def list_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseResponse]:
    if current_user.role == "admin":
        courses = db.scalars(select(Course).order_by(Course.name, Course.code)).all()
        return [to_course_response(course) for course in courses]

    if current_user.role == "teacher":
        teacher = get_current_teacher(db, current_user)
        if teacher is None:
            return []
        courses = db.scalars(
            select(Course).where(Course.teacher_id == teacher.id).order_by(Course.name, Course.code)
        ).all()
        return [to_course_response(course) for course in courses]

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CourseResponse:
    name = clean_required_text(payload.name, "name")
    code = clean_required_text(payload.code, "code")
    grade_level = clean_required_text(payload.grade_level, "grade_level")
    term = clean_required_text(payload.term, "term")
    school_year = clean_required_text(payload.school_year, "school_year")
    language_group = payload.language_group.value if payload.language_group is not None else None

    get_teacher_or_404(db, payload.teacher_id)
    ensure_unique_course_code(db, code)

    course = Course(
        name=name,
        code=code,
        teacher_id=payload.teacher_id,
        grade_level=grade_level,
        term=term,
        school_year=school_year,
        language_group=language_group,
    )
    db.add(course)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="course_created",
        entity_type="course",
        entity_id=course.id,
        old_value=None,
        new_value={
            "name": course.name,
            "code": course.code,
            "teacher_id": course.teacher_id,
            "grade_level": course.grade_level,
            "term": course.term,
            "school_year": course.school_year,
            "language_group": course.language_group,
        },
    )
    db.commit()
    db.refresh(course)
    return to_course_response(course)


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseResponse:
    course = get_course_or_404(db, course_id)
    if current_user.role == "admin" or (
        current_user.role == "teacher" and teacher_can_read_course(db, current_user, course)
    ):
        return to_course_response(course)

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.put("/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> CourseResponse:
    course = get_course_or_404(db, course_id)
    old_value = {
        "name": course.name,
        "code": course.code,
        "teacher_id": course.teacher_id,
        "grade_level": course.grade_level,
        "term": course.term,
        "school_year": course.school_year,
        "language_group": course.language_group,
    }

    if payload.code is not None:
        code = clean_required_text(payload.code, "code")
        ensure_unique_course_code(db, code, course_id=course_id)
        course.code = code
    if payload.teacher_id is not None:
        get_teacher_or_404(db, payload.teacher_id)
        course.teacher_id = payload.teacher_id
    if payload.name is not None:
        course.name = clean_required_text(payload.name, "name")
    if payload.grade_level is not None:
        course.grade_level = clean_required_text(payload.grade_level, "grade_level")
    if payload.term is not None:
        course.term = clean_required_text(payload.term, "term")
    if payload.school_year is not None:
        course.school_year = clean_required_text(payload.school_year, "school_year")
    # language_group is nullable: an explicit null clears the tag, while omitting
    # the key leaves it unchanged. The `is not None` guard used for the required
    # fields above can't express "clear", so key off whether the client actually
    # sent the field.
    if "language_group" in payload.model_fields_set:
        course.language_group = (
            payload.language_group.value if payload.language_group is not None else None
        )

    new_value = {
        "name": course.name,
        "code": course.code,
        "teacher_id": course.teacher_id,
        "grade_level": course.grade_level,
        "term": course.term,
        "school_year": course.school_year,
        "language_group": course.language_group,
    }
    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="course_updated",
            entity_type="course",
            entity_id=course.id,
            old_value=old_value,
            new_value=new_value,
        )

    db.commit()
    db.refresh(course)
    return to_course_response(course)


@router.delete("/{course_id}", response_model=StatusResponse)
def delete_course(
    course_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StatusResponse:
    course = get_course_or_404(db, course_id)
    db.delete(course)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Course cannot be deleted because related records still exist",
        ) from exc

    return StatusResponse(status="ok", message="Course deleted")
