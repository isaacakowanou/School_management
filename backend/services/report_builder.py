from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Course, CourseResult, ReportCard, ReportCardCourse, Student
from services.grade_calculator import calculate_gpa, calculate_overall_average


STALE_FLOAT_TOLERANCE = 0.005


@dataclass(frozen=True)
class ReportCardStaleness:
    is_stale: bool
    reason: str
    snapshot_overall_average: float
    current_overall_average: float | None
    snapshot_gpa: float | None
    current_gpa: float | None


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


def _numbers_match(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(float(left) - float(right)) <= STALE_FLOAT_TOLERANCE


def _snapshot_courses_by_id(report_card: ReportCard) -> dict[UUID, ReportCardCourse]:
    return {course.course_id: course for course in report_card.courses}


def _current_courses_by_id(report_data: dict) -> dict[UUID, dict]:
    return {course["course_id"]: course for course in report_data["courses"]}


def get_report_card_staleness(db: Session, report_card: ReportCard) -> ReportCardStaleness:
    try:
        current_data = build_report_card_data(
            db,
            report_card.student_id,
            report_card.term,
            report_card.school_year,
        )
    except ValueError as exc:
        return ReportCardStaleness(
            is_stale=True,
            reason=f"Current report data could not be built: {exc}",
            snapshot_overall_average=report_card.overall_average,
            current_overall_average=None,
            snapshot_gpa=report_card.gpa,
            current_gpa=None,
        )

    reasons: list[str] = []
    if not _numbers_match(report_card.overall_average, current_data["overall_average"]):
        reasons.append("overall_average changed")
    if not _numbers_match(report_card.gpa, current_data["gpa"]):
        reasons.append("gpa changed")

    snapshot_courses = _snapshot_courses_by_id(report_card)
    current_courses = _current_courses_by_id(current_data)
    if set(snapshot_courses) != set(current_courses):
        reasons.append("course set changed")
    else:
        for course_id, snapshot_course in snapshot_courses.items():
            current_course = current_courses[course_id]
            if not _numbers_match(snapshot_course.average, current_course["average"]):
                reasons.append(f"course average changed for {snapshot_course.course_name}")
            if snapshot_course.letter_grade != current_course["letter_grade"]:
                reasons.append(f"letter grade changed for {snapshot_course.course_name}")

    return ReportCardStaleness(
        is_stale=bool(reasons),
        reason="; ".join(reasons) if reasons else "Report snapshot matches current course results.",
        snapshot_overall_average=report_card.overall_average,
        current_overall_average=current_data["overall_average"],
        snapshot_gpa=report_card.gpa,
        current_gpa=current_data["gpa"],
    )


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
