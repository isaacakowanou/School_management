from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Course, CourseResult, Student
from services.grade_calculator import calculate_gpa, calculate_overall_average


def build_report_card_data(db: Session, student_id: UUID, term: str, school_year: str) -> dict:
    student = db.get(Student, student_id)
    if student is None:
        raise ValueError("Student not found")

    course_results = db.scalars(
        select(CourseResult)
        .join(Course, CourseResult.course_id == Course.id)
        .where(
            CourseResult.student_id == student.id,
            CourseResult.term == term,
            Course.school_year == school_year,
        )
        .order_by(Course.name, Course.code)
    ).all()
    if not course_results:
        raise ValueError("Student has no course results for the requested term and school year")

    courses = [
        {
            "course_id": course_result.course_id,
            "course_name": course_result.course.name,
            "course_code": course_result.course.code,
            "average": course_result.average,
            "letter_grade": course_result.letter_grade,
        }
        for course_result in course_results
    ]
    course_averages = [course["average"] for course in courses]

    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_number": student.student_number,
            "grade_level": student.grade_level,
        },
        "term": term,
        "school_year": school_year,
        "courses": courses,
        "overall_average": calculate_overall_average(course_averages),
        "gpa": calculate_gpa(course_averages),
    }
