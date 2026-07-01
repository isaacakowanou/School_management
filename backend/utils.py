from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from models import Class, Course, ReportCard, Student, Teacher, User
from schemas import CourseResponse, StudentResponse


def get_report_card_or_404(db: Session, report_id) -> ReportCard:
    report_card = db.get(ReportCard, report_id)
    if report_card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")
    return report_card


def get_class_or_404(db: Session, class_id) -> Class:
    school_class = db.get(Class, class_id)
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return school_class


def get_current_teacher(db: Session, current_user: User) -> Teacher | None:
    return db.scalar(select(Teacher).where(Teacher.user_id == current_user.id))


def to_student_response(student: Student) -> StudentResponse:
    return StudentResponse(
        id=student.id,
        first_name=student.first_name,
        last_name=student.last_name,
        grade_level=student.grade_level,
        school_level=student.school_level,
        student_number=student.student_number,
        class_id=student.class_id,
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
        language_group=course.language_group,
        class_id=course.class_id,
    )
