from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from auth import get_current_user, require_admin
from audit import create_audit_log
from database import get_db
from models import Course, Enrollment, Grade, GradeItem, Student, Teacher, User
from schemas import GradeCreate, GradeResponse, GradeUpdate, StatusResponse
from utils import get_current_teacher


router = APIRouter(tags=["grades"])


def to_grade_response(grade: Grade) -> GradeResponse:
    return GradeResponse(
        id=grade.id,
        student_id=grade.student_id,
        grade_item_id=grade.grade_item_id,
        course_id=grade.grade_item.course_id,
        score=grade.score,
        submitted_by_teacher_id=grade.submitted_by_teacher_id,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def get_grade_item_or_404(db: Session, grade_item_id: UUID) -> GradeItem:
    grade_item = db.get(GradeItem, grade_item_id)
    if grade_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade item not found")
    return grade_item


def get_grade_or_404(db: Session, grade_id: UUID) -> Grade:
    grade = db.get(Grade, grade_id)
    if grade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade not found")
    return grade


def can_view_course_grades(db: Session, current_user: User, course: Course) -> bool:
    if current_user.role == "admin":
        return True
    if current_user.role != "teacher":
        return False

    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def get_writable_teacher_for_course(db: Session, current_user: User, course: Course) -> Teacher:
    if current_user.role != "teacher":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    teacher = get_current_teacher(db, current_user)
    if teacher is None or course.teacher_id != teacher.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return teacher


def ensure_student_enrolled(db: Session, student_id: UUID, course_id: UUID) -> None:
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
        )
    )
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student is not enrolled in this course")


def validate_score(score: float, max_score: float) -> None:
    if score < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="score must be greater than or equal to 0")
    if score > max_score:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="score cannot exceed max_score")


@router.get("/courses/{course_id}/grades", response_model=list[GradeResponse])
def list_course_grades(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GradeResponse]:
    course = get_course_or_404(db, course_id)
    if not can_view_course_grades(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    grades = db.scalars(
        select(Grade)
        .join(Grade.grade_item)
        .join(Grade.student)
        .options(contains_eager(Grade.grade_item))
        .where(
            GradeItem.course_id == course_id,
            Student.deleted_at.is_(None),
        )
        .order_by(Grade.created_at)
    ).all()
    return [to_grade_response(grade) for grade in grades]


@router.post("/grades", response_model=GradeResponse, status_code=status.HTTP_201_CREATED)
def create_grade(
    payload: GradeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeResponse:
    student = get_student_or_404(db, payload.student_id)
    grade_item = get_grade_item_or_404(db, payload.grade_item_id)
    course = grade_item.course
    teacher = get_writable_teacher_for_course(db, current_user, course)

    ensure_student_enrolled(db, student.id, course.id)
    validate_score(payload.score, grade_item.max_score)

    existing_grade = db.scalar(
        select(Grade).where(
            Grade.student_id == student.id,
            Grade.grade_item_id == grade_item.id,
        )
    )
    if existing_grade is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Grade already exists")

    grade = Grade(
        student=student,
        grade_item=grade_item,
        score=payload.score,
        submitted_by_teacher=teacher,
    )
    db.add(grade)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_submitted",
        entity_type="grade",
        entity_id=grade.id,
        new_value={
            "student_id": grade.student_id,
            "grade_item_id": grade.grade_item_id,
            "score": grade.score,
            "submitted_by_teacher_id": grade.submitted_by_teacher_id,
        },
    )
    db.commit()
    db.refresh(grade)
    return to_grade_response(grade)


@router.put("/grades/{grade_id}", response_model=GradeResponse)
def update_grade(
    grade_id: UUID,
    payload: GradeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeResponse:
    grade = get_grade_or_404(db, grade_id)
    if grade.student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade not found")
    grade_item = grade.grade_item
    get_writable_teacher_for_course(db, current_user, grade_item.course)

    validate_score(payload.score, grade_item.max_score)
    old_score = grade.score
    grade.score = payload.score
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_updated",
        entity_type="grade",
        entity_id=grade.id,
        old_value={"score": old_score},
        new_value={"score": grade.score},
    )
    db.commit()
    db.refresh(grade)
    return to_grade_response(grade)


@router.delete("/grades/{grade_id}", response_model=StatusResponse)
def delete_grade(
    grade_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    grade = get_grade_or_404(db, grade_id)
    if grade.student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grade not found")
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="grade_deleted",
        entity_type="grade",
        entity_id=grade.id,
        old_value={
            "student_id": grade.student_id,
            "grade_item_id": grade.grade_item_id,
            "score": grade.score,
            "submitted_by_teacher_id": grade.submitted_by_teacher_id,
        },
    )
    db.delete(grade)
    db.commit()
    return StatusResponse(status="ok", message="Grade deleted")
