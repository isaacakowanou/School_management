from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from auth import get_current_user, require_admin
from database import get_db
from models import Course, Enrollment, Parent, Student, StudentParent, Teacher, User
from schemas import (
    DeletedStudentResponse,
    LinkedParentResponse,
    StatusResponse,
    StudentCreate,
    StudentParentLinkCreate,
    StudentResponse,
    StudentUpdate,
)
from utils import get_class_or_404, to_student_response


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
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def get_any_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def get_parent_or_404(db: Session, parent_id: UUID) -> Parent:
    parent = db.get(Parent, parent_id)
    if parent is None or parent.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent not found")
    return parent


def teacher_can_read_student(db: Session, current_user: User, student_id: UUID) -> bool:
    enrollment = db.scalar(
        select(Enrollment)
        .join(Course, Enrollment.course_id == Course.id)
        .join(Teacher, Course.teacher_id == Teacher.id)
        .join(Student, Enrollment.student_id == Student.id)
        .where(
            Enrollment.student_id == student_id,
            Teacher.user_id == current_user.id,
            Enrollment.deleted_at.is_(None),
            Course.deleted_at.is_(None),
            Teacher.deleted_at.is_(None),
            Student.deleted_at.is_(None),
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
    students = db.scalars(
        select(Student)
        .where(Student.deleted_at.is_(None))
        .order_by(Student.last_name, Student.first_name)
    ).all()
    return [to_student_response(student) for student in students]


@router.get("/trash", response_model=list[DeletedStudentResponse])
def list_deleted_students(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[DeletedStudentResponse]:
    students = db.scalars(
        select(Student)
        .options(joinedload(Student.school_class))
        .where(Student.deleted_at.is_not(None))
        .order_by(Student.deleted_at.desc(), Student.last_name, Student.first_name)
    ).all()
    return [
        DeletedStudentResponse(
            **to_student_response(student).model_dump(),
            class_name=student.school_class.name_fr if student.school_class else None,
            deleted_at=student.deleted_at,
        )
        for student in students
        if student.deleted_at is not None
    ]


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
    school_level = payload.school_level.value if payload.school_level is not None else None

    existing_student = db.scalar(select(Student).where(Student.student_number == student_number))
    if existing_student is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student number already exists")

    if payload.class_id is not None:
        get_class_or_404(db, payload.class_id)

    student = Student(
        first_name=first_name,
        last_name=last_name,
        grade_level=grade_level,
        school_level=school_level,
        student_number=student_number,
        class_id=payload.class_id,
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
            "school_level": student.school_level,
            "student_number": student.student_number,
            "class_id": student.class_id,
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
    current_user: User = Depends(require_admin),
) -> StudentResponse:
    student = get_student_or_404(db, student_id)
    old_value = {
        "first_name": student.first_name,
        "last_name": student.last_name,
        "grade_level": student.grade_level,
        "school_level": student.school_level,
        "student_number": student.student_number,
        "class_id": student.class_id,
    }

    if payload.student_number is not None:
        student_number = clean_required_text(payload.student_number, "student_number")
        existing_student = db.scalar(
            select(Student).where(Student.student_number == student_number, Student.id != student_id)
        )
        if existing_student is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student number already exists")
        student.student_number = student_number
    if payload.first_name is not None:
        student.first_name = clean_required_text(payload.first_name, "first_name")
    if payload.last_name is not None:
        student.last_name = clean_required_text(payload.last_name, "last_name")
    if payload.grade_level is not None:
        student.grade_level = clean_required_text(payload.grade_level, "grade_level")
    # school_level is nullable: an explicit null clears it, while omitting the
    # key leaves it unchanged. The `is not None` guard used for the required
    # fields above can't express "clear", so key off whether the client actually
    # sent the field.
    if "school_level" in payload.model_fields_set:
        student.school_level = (
            payload.school_level.value if payload.school_level is not None else None
        )
    if "class_id" in payload.model_fields_set:
        if payload.class_id is not None:
            get_class_or_404(db, payload.class_id)
        student.class_id = payload.class_id

    new_value = {
        "first_name": student.first_name,
        "last_name": student.last_name,
        "grade_level": student.grade_level,
        "school_level": student.school_level,
        "student_number": student.student_number,
        "class_id": student.class_id,
    }
    if new_value != old_value:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="student_updated",
            entity_type="student",
            entity_id=student.id,
            old_value=old_value,
            new_value=new_value,
        )

    db.commit()
    db.refresh(student)
    return to_student_response(student)


@router.delete("/{student_id}", response_model=StatusResponse)
def delete_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    student = get_student_or_404(db, student_id)
    deleted_at = datetime.now(timezone.utc)
    old_value = {
        "first_name": student.first_name,
        "last_name": student.last_name,
        "grade_level": student.grade_level,
        "school_level": student.school_level,
        "student_number": student.student_number,
        "class_id": student.class_id,
        "deleted_at": student.deleted_at,
    }
    student.deleted_at = deleted_at
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="student_deleted",
        entity_type="student",
        entity_id=student.id,
        old_value=old_value,
        new_value={**old_value, "deleted_at": deleted_at},
    )
    db.commit()

    return StatusResponse(status="ok", message="Student moved to Trash")


@router.post("/{student_id}/restore", response_model=StatusResponse)
def restore_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    student = get_any_student_or_404(db, student_id)
    if student.deleted_at is None:
        return StatusResponse(status="ok", message="Student is already active")

    old_value = {"deleted_at": student.deleted_at}
    student.deleted_at = None
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="student_restored",
        entity_type="student",
        entity_id=student.id,
        old_value=old_value,
        new_value={"deleted_at": None},
    )
    db.commit()
    return StatusResponse(status="ok", message="Student restored")


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
        .where(StudentParent.student_id == student_id, StudentParent.deleted_at.is_(None), Parent.deleted_at.is_(None))
    ).all()
    return [to_linked_parent_response(link) for link in links]


@router.post("/{student_id}/parents", response_model=LinkedParentResponse, status_code=status.HTTP_201_CREATED)
def link_student_parent(
    student_id: UUID,
    payload: StudentParentLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> LinkedParentResponse:
    student = get_student_or_404(db, student_id)
    parent = get_parent_or_404(db, payload.parent_id)
    relationship = payload.relationship.strip() if payload.relationship is not None else None
    if relationship == "":
        relationship = None

    existing_link = db.scalar(
        select(StudentParent).where(
            StudentParent.student_id == student.id,
            StudentParent.parent_id == parent.id,
            StudentParent.deleted_at.is_(None),
        )
    )
    if existing_link is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parent is already linked to student")

    link = StudentParent(student=student, parent=parent, relationship=relationship)
    db.add(link)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="parent_linked_to_student",
        entity_type="student_parent",
        entity_id=link.id,
        old_value=None,
        new_value={
            "student_id": student.id,
            "parent_id": parent.id,
            "relationship": link.relationship,
        },
    )
    db.commit()
    db.refresh(link)
    return to_linked_parent_response(link)


@router.delete("/{student_id}/parents/{parent_id}", response_model=StatusResponse)
def unlink_student_parent(
    student_id: UUID,
    parent_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    get_student_or_404(db, student_id)
    link = db.scalar(
        select(StudentParent).where(
            StudentParent.student_id == student_id,
            StudentParent.parent_id == parent_id,
            StudentParent.deleted_at.is_(None),
        )
    )
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent link not found")

    old_value = {
        "student_id": link.student_id,
        "parent_id": link.parent_id,
        "relationship": link.relationship,
    }
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="parent_unlinked_from_student",
        entity_type="student_parent",
        entity_id=link.id,
        old_value=old_value,
        new_value=None,
    )
    link.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return StatusResponse(status="ok", message="Parent unlinked from student")
