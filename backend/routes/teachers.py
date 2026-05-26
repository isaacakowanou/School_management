from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user, require_admin
from database import get_db
from models import Course, Teacher, User
from schemas import CourseResponse, TeacherCreate, TeacherResponse, TeacherUpdate


router = APIRouter(tags=["teachers"])


def to_teacher_response(teacher: Teacher) -> TeacherResponse:
    return TeacherResponse(
        id=teacher.id,
        user_id=teacher.user_id,
        name=teacher.user.name,
        email=teacher.user.email,
        employee_number=teacher.employee_number,
    )


def to_course_response(course: Course) -> CourseResponse:
    return CourseResponse(
        id=course.id,
        name=course.name,
        code=course.code,
        teacher_id=course.teacher_id,
        grade_level=course.grade_level,
        term=course.term,
        school_year=course.school_year,
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


@router.get("", response_model=list[TeacherResponse])
def list_teachers(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[TeacherResponse]:
    teachers = db.scalars(select(Teacher).join(User).order_by(User.name)).all()
    return [to_teacher_response(teacher) for teacher in teachers]


@router.post("", response_model=TeacherResponse, status_code=status.HTTP_201_CREATED)
def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> TeacherResponse:
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role != "teacher":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User must have teacher role")

    existing_teacher = db.scalar(select(Teacher).where(Teacher.user_id == payload.user_id))
    if existing_teacher is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Teacher profile already exists")

    existing_employee_number = db.scalar(
        select(Teacher).where(Teacher.employee_number == payload.employee_number)
    )
    if existing_employee_number is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee number already exists")

    teacher = Teacher(user=user, employee_number=payload.employee_number)
    db.add(teacher)
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
    _: User = Depends(require_admin),
) -> TeacherResponse:
    teacher = get_teacher_or_404(db, teacher_id)

    existing_teacher = db.scalar(
        select(Teacher).where(
            Teacher.employee_number == payload.employee_number,
            Teacher.id != teacher_id,
        )
    )
    if existing_teacher is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee number already exists")

    teacher.employee_number = payload.employee_number
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
