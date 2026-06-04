from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from auth import get_current_user, require_admin
from database import get_db
from models import Course, Enrollment, Parent, Student, StudentParent, Teacher, User
from schemas import (
    LinkedParentResponse,
    StatusResponse,
    StudentCreate,
    StudentParentLinkCreate,
    StudentResponse,
    StudentUpdate,
)
from utils import to_student_response


router = APIRouter(tags=["students"])


def to_linked_parent_response(link: StudentParent) -> LinkedParentResponse:
    return LinkedParentResponse(
        id=link.parent.id,
        user_id=link.parent.user_id,
        name=link.parent.user.name,
        email=link.parent.user.email,
        phone=link.parent.phone,
        relationship=link.relationship,
    )


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def get_parent_or_404(db: Session, parent_id: UUID) -> Parent:
    parent = db.get(Parent, parent_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")
    return parent


def teacher_can_read_student(db: Session, current_user: User, student_id: UUID) -> bool:
    enrollment = db.scalar(
        select(Enrollment)
        .join(Course, Enrollment.course_id == Course.id)
        .join(Teacher, Course.teacher_id == Teacher.id)
        .where(
            Enrollment.student_id == student_id,
            Teacher.user_id == current_user.id,
        )
    )
    return enrollment is not None


def clean_required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot be empty",
        )
    return cleaned


@router.get("", response_model=list[StudentResponse])
def list_students(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[StudentResponse]:
    students = db.scalars(select(Student).order_by(Student.last_name, Student.first_name)).all()
    return [to_student_response(student) for student in students]


@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StudentResponse:
    first_name = clean_required_text(payload.first_name, "first_name")
    last_name = clean_required_text(payload.last_name, "last_name")
    grade_level = clean_required_text(payload.grade_level, "grade_level")
    student_number = clean_required_text(payload.student_number, "student_number")

    existing_student = db.scalar(select(Student).where(Student.student_number == student_number))
    if existing_student is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student number already exists")

    student = Student(
        first_name=first_name,
        last_name=last_name,
        grade_level=grade_level,
        student_number=student_number,
    )
    db.add(student)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="student_created",
        entity_type="student",
        entity_id=student.id,
        old_value=None,
        new_value={
            "first_name": student.first_name,
            "last_name": student.last_name,
            "grade_level": student.grade_level,
            "student_number": student.student_number,
        },
    )
    db.commit()
    db.refresh(student)
    return to_student_response(student)


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StudentResponse:
    student = get_student_or_404(db, student_id)
    if current_user.role == "admin" or (
        current_user.role == "teacher" and teacher_can_read_student(db, current_user, student_id)
    ):
        return to_student_response(student)

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: UUID,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StudentResponse:
    student = get_student_or_404(db, student_id)

    if payload.student_number is not None:
        existing_student = db.scalar(
            select(Student).where(Student.student_number == payload.student_number, Student.id != student_id)
        )
        if existing_student is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student number already exists")
        student.student_number = payload.student_number
    if payload.first_name is not None:
        student.first_name = payload.first_name
    if payload.last_name is not None:
        student.last_name = payload.last_name
    if payload.grade_level is not None:
        student.grade_level = payload.grade_level

    db.commit()
    db.refresh(student)
    return to_student_response(student)


@router.delete("/{student_id}", response_model=StatusResponse)
def delete_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StatusResponse:
    student = get_student_or_404(db, student_id)
    db.delete(student)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student cannot be deleted because related records still exist",
        ) from exc

    return StatusResponse(status="ok", message="Student deleted")


@router.get("/{student_id}/parents", response_model=list[LinkedParentResponse])
def list_student_parents(
    student_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[LinkedParentResponse]:
    get_student_or_404(db, student_id)
    links = db.scalars(
        select(StudentParent)
        .options(joinedload(StudentParent.parent).joinedload(Parent.user))
        .where(StudentParent.student_id == student_id)
    ).all()
    return [to_linked_parent_response(link) for link in links]


@router.post("/{student_id}/parents", response_model=LinkedParentResponse, status_code=status.HTTP_201_CREATED)
def link_student_parent(
    student_id: UUID,
    payload: StudentParentLinkCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> LinkedParentResponse:
    student = get_student_or_404(db, student_id)
    parent = get_parent_or_404(db, payload.parent_id)

    existing_link = db.scalar(
        select(StudentParent).where(
            StudentParent.student_id == student.id,
            StudentParent.parent_id == parent.id,
        )
    )
    if existing_link is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parent is already linked to student")

    link = StudentParent(student=student, parent=parent, relationship=payload.relationship)
    db.add(link)
    db.commit()
    db.refresh(link)
    return to_linked_parent_response(link)


@router.delete("/{student_id}/parents/{parent_id}", response_model=StatusResponse)
def unlink_student_parent(
    student_id: UUID,
    parent_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StatusResponse:
    get_student_or_404(db, student_id)
    link = db.scalar(
        select(StudentParent).where(
            StudentParent.student_id == student_id,
            StudentParent.parent_id == parent_id,
        )
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent link not found")

    db.delete(link)
    db.commit()
    return StatusResponse(status="ok", message="Parent unlinked from student")
