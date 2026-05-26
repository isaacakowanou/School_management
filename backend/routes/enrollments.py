from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user, require_admin
from database import get_db
from models import Course, Enrollment, Student, User
from schemas import EnrollmentCreate, EnrollmentResponse, StatusResponse, StudentResponse
from utils import get_current_teacher, to_student_response


router = APIRouter(tags=["enrollments"])


def to_enrollment_response(enrollment: Enrollment) -> EnrollmentResponse:
    return EnrollmentResponse(
        id=enrollment.id,
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def can_read_course_students(db: Session, current_user: User, course: Course) -> bool:
    if current_user.role == "admin":
        return True
    if current_user.role != "teacher":
        return False

    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


@router.get("/courses/{course_id}/students", response_model=list[StudentResponse])
def list_course_students(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StudentResponse]:
    course = get_course_or_404(db, course_id)
    if not can_read_course_students(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    students = db.scalars(
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id == course_id)
        .order_by(Student.last_name, Student.first_name)
    ).all()
    return [to_student_response(student) for student in students]


@router.post("/enrollments", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment(
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> EnrollmentResponse:
    student = get_student_or_404(db, payload.student_id)
    course = get_course_or_404(db, payload.course_id)

    existing_enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.course_id == course.id,
        )
    )
    if existing_enrollment is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student is already enrolled")

    enrollment = Enrollment(student=student, course=course)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return to_enrollment_response(enrollment)


@router.delete("/enrollments/{enrollment_id}", response_model=StatusResponse)
def delete_enrollment(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> StatusResponse:
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    db.delete(enrollment)
    db.commit()
    return StatusResponse(status="ok", message="Enrollment deleted")
