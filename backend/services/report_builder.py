from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Course, CourseResult, ReportCard, Student
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


def build_report_card_data_from_report_card(db: Session, report_card: ReportCard) -> dict:
    """Reconstruct report_data from a stored ReportCard + ReportCardCourse snapshot.

    Uses only persisted values — no CourseResult recomputation, no OpenAI, no DB
    writes. course_code is resolved from the live Course row (by course_id); a course
    that no longer exists falls back to "N/A".
    """
    student = report_card.student

    course_ids = [course.course_id for course in report_card.courses]
    code_by_course_id: dict = {}
    if course_ids:
        for course in db.scalars(select(Course).where(Course.id.in_(course_ids))).all():
            code_by_course_id[course.id] = course.code

    courses = [
        {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "course_code": code_by_course_id.get(course.course_id, "N/A"),
            "average": course.average,
            "letter_grade": course.letter_grade,
        }
        for course in report_card.courses
    ]
    courses.sort(key=lambda course: (course["course_name"] or "", course["course_code"] or ""))

    generated_date = (
        report_card.created_at.isoformat(timespec="seconds")
        if report_card.created_at is not None
        else None
    )

    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_number": student.student_number,
            "grade_level": student.grade_level,
        },
        "term": report_card.term,
        "school_year": report_card.school_year,
        "courses": courses,
        "overall_average": report_card.overall_average,
        "gpa": report_card.gpa,
        "ai_summary": report_card.ai_summary,
        "status": report_card.status,
        "generated_date": generated_date,
    }
