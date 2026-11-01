"""Manage the recoverable links between active students and courses.

Unenrollment soft-deletes and audits the link instead of erasing academic
history. Roster reads require an active course, student, enrollment, and (for
teachers) ownership of the course, preventing Trash records from resurfacing.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from audit import create_audit_log
from auth import get_current_user, require_admin
from database import get_db
from models import Course, Enrollment, Student, User
from schemas import EnrollmentCreate, EnrollmentResponse, StatusResponse, StudentResponse
from utils import get_current_teacher, to_student_response


router = APIRouter(tags=["enrollments"])


def to_enrollment_response(enrollment: Enrollment) -> EnrollmentResponse:
    """Return the enrollment id and its student/course ids without loading related details."""
    return EnrollmentResponse(
        id=enrollment.id,
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
    )


def get_course_or_404(db: Session, course_id: UUID) -> Course:
    """Return the active course with course_id from db, or raise HTTP 404."""
    course = db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    """Return the active student with student_id from db, or raise HTTP 404."""
    student = db.get(Student, student_id)
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def can_read_course_students(db: Session, current_user: User, course: Course) -> bool:
    """Return whether current_user is an admin or the teacher assigned to course.

    Other roles cannot read this roster. The caller must first validate that
    the course is active; teacher identity comes from the shared lookup.
    """
    if current_user.role == "admin":
        return True
    if current_user.role != "teacher":
        return False

    teacher = get_current_teacher(db, current_user)
    return teacher is not None and course.teacher_id == teacher.id


def get_enrollment_or_404(db: Session, enrollment_id: UUID) -> Enrollment:
    """Return an active enrollment by id, or raise HTTP 404.

    This lookup does not independently check student or course deletion state.
    """
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None or enrollment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    return enrollment


def get_course_student_enrollment_or_404(db: Session, course_id: UUID, student_id: UUID) -> Enrollment | None:
    """Return an active link for course_id and student_id, or None.

    Despite its name, this helper leaves the HTTP 404 response to its caller.
    """
    return db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id,
            Enrollment.student_id == student_id,
            Enrollment.deleted_at.is_(None),
        )
    )


def delete_enrollment_with_audit(db: Session, current_user: User, enrollment: Enrollment) -> None:
    """Audit current_user and timestamp the enrollment as deleted without committing.

    Student/course rows and academic history remain intact; the caller enforces
    permissions and the graduated-student guard before using this helper.
    """
    old_value = {
        "student_id": enrollment.student_id,
        "course_id": enrollment.course_id,
    }
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="student_unenrolled_from_course",
        entity_type="enrollment",
        entity_id=enrollment.id,
        old_value=old_value,
        new_value=None,
    )
    enrollment.deleted_at = datetime.now(timezone.utc)


def ensure_student_can_be_unenrolled(student: Student) -> None:
    # Historical membership stays fixed once the student has graduated.
    """Raise HTTP 409 for a graduated student to preserve historical course membership."""
    if student.academic_status == "graduated":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "graduated_student_unenroll_blocked",
                "message": "Graduated students cannot be unenrolled from historical courses",
            },
        )


@router.get("/courses/{course_id}/students", response_model=list[StudentResponse])
def list_course_students(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StudentResponse]:
    """Return alphabetically ordered active students enrolled in an active course.

    Allow admins and the assigned teacher only; deny other users with HTTP 403.
    Deleted enrollment and student rows are excluded from the roster.
    """
    course = get_course_or_404(db, course_id)
    # Roster access follows course ownership; parent access uses other routes.
    if not can_read_course_students(db, current_user, course):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    students = db.scalars(
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .options(joinedload(Student.school_class))
        .where(
            Enrollment.course_id == course_id,
            Enrollment.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
        .order_by(Student.last_name, Student.first_name)
    ).all()
    return [to_student_response(student) for student in students]


@router.delete("/courses/{course_id}/students/{student_id}", response_model=StatusResponse)
def unenroll_student_from_course(
    course_id: UUID,
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    """Soft-delete a course/student link for an admin, commit, and return OK.

    Require active course, student, and enrollment rows. Block graduated
    students before writing the audit entry or deletion timestamp.
    """
    get_course_or_404(db, course_id)
    student = get_student_or_404(db, student_id)
    ensure_student_can_be_unenrolled(student)
    enrollment = get_course_student_enrollment_or_404(db, course_id, student_id)
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")

    delete_enrollment_with_audit(db, current_user, enrollment)
    db.commit()
    return StatusResponse(status="ok", message="Student unenrolled from course")


@router.post("/enrollments", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment(
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> EnrollmentResponse:
    """Create and audit a new active student/course link for an admin, then commit.

    Reject missing/deleted endpoints and an existing active link. Deleted links
    are not reused by this path. Return the newly persisted enrollment ids.
    """
    student = get_student_or_404(db, payload.student_id)
    course = get_course_or_404(db, payload.course_id)

    existing_enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.course_id == course.id,
            Enrollment.deleted_at.is_(None),
        )
    )
    if existing_enrollment is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student is already enrolled")

    enrollment = Enrollment(student=student, course=course)
    db.add(enrollment)
    db.flush()
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="student_enrolled_in_course",
        entity_type="enrollment",
        entity_id=enrollment.id,
        old_value=None,
        new_value={
            "student_id": student.id,
            "course_id": course.id,
        },
    )
    db.commit()
    db.refresh(enrollment)
    return to_enrollment_response(enrollment)


@router.delete("/enrollments/{enrollment_id}", response_model=StatusResponse)
def delete_enrollment(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StatusResponse:
    """Soft-delete an enrollment by id for an admin, commit, and return OK.

    Require an active enrollment and student, and block graduated students.
    This route does not require the associated course to remain active.
    """
    enrollment = get_enrollment_or_404(db, enrollment_id)
    student = get_student_or_404(db, enrollment.student_id)
    ensure_student_can_be_unenrolled(student)

    delete_enrollment_with_audit(db, current_user, enrollment)
    db.commit()
    return StatusResponse(status="ok", message="Student unenrolled from course")
