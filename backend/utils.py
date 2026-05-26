from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Course, Student, Teacher, User
from schemas import CourseResponse, StudentResponse


def get_current_teacher(db: Session, current_user: User) -> Teacher | None:
    return db.scalar(select(Teacher).where(Teacher.user_id == current_user.id))


def to_student_response(student: Student) -> StudentResponse:
    return StudentResponse(
        id=student.id,
        first_name=student.first_name,
        last_name=student.last_name,
        grade_level=student.grade_level,
        student_number=student.student_number,
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
