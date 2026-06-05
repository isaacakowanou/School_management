from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from audit import create_audit_log
from auth import get_current_user, hash_password, require_admin
from database import get_db
from models import Course, Teacher, User
from schemas import CourseResponse, TeacherCreate, TeacherResponse, TeacherUpdate
from utils import to_course_response


router = APIRouter(tags=["teachers"])


def to_teacher_response(teacher: Teacher) -> TeacherResponse:
    return TeacherResponse(
        id=teacher.id,
        user_id=teacher.user_id,
        name=teacher.user.name,
        email=teacher.user.email,
        employee_number=teacher.employee_number,
    )


def get_teacher_or_404(db: Session, teacher_id: UUID) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
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


@router.get("", response_model=list[TeacherResponse])
def list_teachers(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[TeacherResponse]:
    teachers = db.scalars(
        select(Teacher)
        .join(Teacher.user)
        .options(contains_eager(Teacher.user))
        .order_by(User.name)
    ).all()
    return [to_teacher_response(teacher) for teacher in teachers]


@router.post("", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> TeacherResponse:
    name = clean_required_text(payload.name, "name")
    email = clean_required_text(payload.email, "email")
    password = clean_required_text(payload.password, "password")
    employee_number = clean_required_text(payload.employee_number, "employee_number")

    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    existing_employee_number = db.scalar(
        select(Teacher).where(Teacher.employee_number == employee_number)
    )
    if existing_employee_number is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee number already exists")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role="teacher",
    )
    teacher = Teacher(user=user, employee_number=employee_number)
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
            "employee_number": teacher.employee_number,
        },
    )
    db.commit()
    db.refresh(teacher)
    return to_teacher_response(teacher)


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
        "employee_number": teacher.employee_number,
    }

    if payload.name is not None:
        teacher.user.name = clean_required_text(payload.name, "name")
    if payload.email is not None:
        email = clean_required_text(payload.email, "email")
        existing_user = db.scalar(select(User).where(User.email == email, User.id != teacher.user_id))
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        teacher.user.email = email
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


@router.get("/{teacher_id}/courses", response_model=list[CourseResponse])
def list_teacher_courses(
    teacher_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseResponse]:
    teacher = get_teacher_or_404(db, teacher_id)
    if not can_read_teacher(current_user, teacher):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    courses = db.scalars(select(Course).where(Course.teacher_id == teacher_id).order_by(Course.name)).all()
    return [to_course_response(course) for course in courses]
