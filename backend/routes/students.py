"""Manage permanent student identity and year-scoped academic context.

Students belong to the school and list membership is never filtered by school
year. Class assignments belong to one year and only decorate/filter the list
when a year is selected. Grades and bulletin-related reads are historical and
must not fall back to the student's current live class pointer.

Normal lookups reject trashed students, while the separate "any student" lookup
exists only for restore semantics. Student deletion preserves parent links and
all academic history; deleted-student views are compatibility/filter surfaces
over the same recoverable state. Teachers may read only students reached through
active assigned-course enrollment, and cross-course grade detail is admin-only.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from auth import get_current_user, require_admin
from constants import TRIMESTER_TERMS
from database import get_db
from models import Course, Enrollment, Grade, GradeItem, Parent, Student, StudentClassAssignment, StudentParent, Teacher, User
from schemas import (
    DeletedStudentResponse,
    LinkedParentResponse,
    ParentGradeResponse,
    StatusResponse,
    StudentCreate,
    StudentParentLinkCreate,
    StudentResponse,
    StudentUpdate,
)
from services.academic_context import current_school_year, current_term_for_year
from services.student_assignments import (
    assignments_for_students,
    clear_student_assignment,
    set_student_assignment,
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


def generate_student_number(db: Session, year: int) -> str:
    prefix = f"STU-{year}-"
    last = db.scalar(
        select(Student.student_number)
        .where(Student.student_number.like(f"{prefix}%"))
        .order_by(Student.student_number.desc())
        .limit(1)
    )
    try:
        n = int(last[len(prefix):]) + 1 if last else 1
    except (ValueError, TypeError):
        n = 1
    while True:
        candidate = f"{prefix}{n:04d}"
        if not db.scalar(select(Student).where(Student.student_number == candidate)):
            return candidate
        n += 1


def latest_grade_period_for_student(
    db: Session,
    student_id: UUID,
    school_year: str | None = None,
    term: str | None = None,
) -> tuple[str, str] | None:
    query = (
        select(Course.school_year, GradeItem.term)
        .join(GradeItem, GradeItem.course_id == Course.id)
        .join(Grade, Grade.grade_item_id == GradeItem.id)
        .where(
            Grade.student_id == student_id,
            Grade.deleted_at.is_(None),
            GradeItem.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
        .distinct()
    )
    if school_year is not None:
        query = query.where(Course.school_year == school_year)
    if term is not None:
        query = query.where(GradeItem.term == term)

    periods = db.execute(query).all()
    if not periods:
        return None

    def sort_key(period: tuple[str, str]) -> tuple[str, int]:
        year, period_term = period
        try:
            term_index = TRIMESTER_TERMS.index(period_term)
        except ValueError:
            term_index = -1
        return year, term_index

    return max(periods, key=sort_key)


@router.get("", response_model=list[StudentResponse])
def list_students(
    academic_status: str = "active",
    school_year: str | None = None,
    class_id: UUID | None = None,
    unassigned: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[StudentResponse]:
    if class_id is not None and unassigned:
        raise HTTPException(status_code=422, detail="class_id and unassigned cannot be combined")
    if class_id is not None:
        selected_class = get_class_or_404(db, class_id)
        if school_year is not None and selected_class.school_year != school_year:
            raise HTTPException(status_code=422, detail="class_id does not belong to school_year")
        school_year = school_year or selected_class.school_year
    if unassigned and school_year is None:
        raise HTTPException(status_code=422, detail="school_year is required for unassigned filtering")

    query = (
        select(Student)
        .options(joinedload(Student.school_class))
        .where(Student.deleted_at.is_(None))
        .order_by(Student.last_name, Student.first_name)
    )
    if academic_status != "all":
        if academic_status not in {"active", "graduated"}:
            raise HTTPException(status_code=422, detail="academic_status must be active, graduated, or all")
        query = query.where(Student.academic_status == academic_status)
    if school_year is not None and (class_id is not None or unassigned):
        query = query.outerjoin(
            StudentClassAssignment,
            (StudentClassAssignment.student_id == Student.id)
            & (StudentClassAssignment.school_year == school_year),
        )
        if class_id is not None:
            query = query.where(StudentClassAssignment.class_id == class_id)
        else:
            query = query.where(StudentClassAssignment.id.is_(None))
    students = db.scalars(query).all()
    assignment_by_student = (
        assignments_for_students(db, [student.id for student in students], school_year)
        if school_year is not None
        else {}
    )
    return [
        to_student_response(
            student,
            assignment=assignment_by_student.get(student.id),
            assignment_school_year=school_year,
        )
        for student in students
    ]


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
    school_level = payload.school_level.value if payload.school_level is not None else None

    raw_number = (payload.student_number or "").strip()
    if raw_number:
        existing_student = db.scalar(select(Student).where(Student.student_number == raw_number))
        if existing_student is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student number already exists")
        student_number = raw_number
    else:
        student_number = generate_student_number(db, datetime.now(timezone.utc).year)

    educmaster_number = (payload.educmaster_number or "").strip() or None

    school_class = get_class_or_404(db, payload.class_id) if payload.class_id is not None else None

    student = Student(
        first_name=first_name,
        last_name=last_name,
        school_level=school_level,
        student_number=student_number,
        educmaster_number=educmaster_number,
        class_id=payload.class_id,
    )
    db.add(student)
    db.flush()
    if school_class is not None:
        set_student_assignment(db, student, school_class)
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
            "school_level": student.school_level,
            "student_number": student.student_number,
            "educmaster_number": student.educmaster_number,
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
        "school_level": student.school_level,
        "student_number": student.student_number,
        "educmaster_number": student.educmaster_number,
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
    # Nullable fields: explicit null clears, omitting leaves unchanged.
    if "school_level" in payload.model_fields_set:
        student.school_level = (
            payload.school_level.value if payload.school_level is not None else None
        )
    if "educmaster_number" in payload.model_fields_set:
        student.educmaster_number = (payload.educmaster_number or "").strip() or None
    if "class_id" in payload.model_fields_set:
        previous_class = student.school_class
        if payload.class_id is not None:
            school_class = get_class_or_404(db, payload.class_id)
            set_student_assignment(db, student, school_class)
        else:
            assignment_year = (payload.class_school_year or "").strip() or (
                previous_class.school_year if previous_class is not None else None
            )
            if assignment_year is not None:
                clear_student_assignment(db, student.id, assignment_year)
        student.class_id = payload.class_id
    elif payload.class_school_year is not None:
        raise HTTPException(status_code=422, detail="class_school_year requires class_id")

    new_value = {
        "first_name": student.first_name,
        "last_name": student.last_name,
        "school_level": student.school_level,
        "student_number": student.student_number,
        "educmaster_number": student.educmaster_number,
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


@router.get("/{student_id}/grades", response_model=list[ParentGradeResponse])
def list_student_grades_admin(
    student_id: UUID,
    term: str | None = None,
    school_year: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ParentGradeResponse]:
    get_student_or_404(db, student_id)

    if term is not None and term not in TRIMESTER_TERMS:
        raise HTTPException(status_code=422, detail="term must be a canonical trimester")

    selected_period = latest_grade_period_for_student(db, student_id, school_year, term)
    if selected_period is not None:
        school_year = school_year or selected_period[0]
        selected_term = term or selected_period[1]
    else:
        school_year = school_year or current_school_year(db)
        selected_term = term or (current_term_for_year(db, school_year) if school_year is not None else None)

    if school_year is None:
        return []
    if selected_term is None:
        return []

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


@router.get("/{student_id}/parents", response_model=list[LinkedParentResponse])
def list_student_parents(
    student_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[LinkedParentResponse]:
    get_student_or_404(db, student_id)
    links = db.scalars(
        select(StudentParent)
        .join(Parent, StudentParent.parent_id == Parent.id)
        .options(joinedload(StudentParent.parent).joinedload(Parent.user))
        .where(StudentParent.student_id == student_id, StudentParent.deleted_at.is_(None), Parent.deleted_at.is_(None))
    ).all()
    unique_links = {}
    for link in links:
        unique_links.setdefault(link.parent_id, link)
    return [to_linked_parent_response(link) for link in unique_links.values()]


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

    deleted_link = db.scalar(
        select(StudentParent)
        .where(
            StudentParent.student_id == student.id,
            StudentParent.parent_id == parent.id,
            StudentParent.deleted_at.is_not(None),
        )
        .order_by(StudentParent.deleted_at.desc())
    )
    if deleted_link is not None:
        link = deleted_link
        link.deleted_at = None
        link.deleted_batch_id = None
        link.relationship = relationship
    else:
        link = StudentParent(student=student, parent=parent, relationship=relationship)
        db.add(link)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Parent is already linked to student",
        ) from exc
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
    links = db.scalars(
        select(StudentParent).where(
            StudentParent.student_id == student_id,
            StudentParent.parent_id == parent_id,
            StudentParent.deleted_at.is_(None),
        )
    ).all()
    if not links:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent link not found")

    deleted_at = datetime.now(timezone.utc)
    for link in links:
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
        link.deleted_at = deleted_at
    db.commit()
    return StatusResponse(status="ok", message="Parent unlinked from student")
