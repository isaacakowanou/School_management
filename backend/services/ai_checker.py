"""Return deterministic advisory warnings about course data and report snapshots.

Read enrollments, items, scores, results, and snapshot rows without changing any
of them or using an LLM. Callers enforce authorization and choose whether to
store warnings; optional report course scoping prevents a teacher's check from
exposing other teachers' data. Weight checks ignore unweighted items and validate
each trimester independently; other course checks still inspect all active items.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Course, CourseResult, Enrollment, Grade, GradeItem, ReportCard, ReportCardCourse, Student
from services.grade_calculator import WEIGHT_TOLERANCE_MAX, WEIGHT_TOLERANCE_MIN


def _warning(
    warning_type: str,
    message: str,
    severity: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
) -> dict:
    return {
        "warning_type": warning_type,
        "message": message,
        "severity": severity,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }


def check_course_grade_data(db: Session, course_id: UUID) -> list[dict]:
    """Return deterministic warning dictionaries for a non-deleted course's data.

    Inspect active items, enrolled students, scores, and missing current-term
    results without changing them. Check numeric weight totals separately for
    each trimester; null weights mean no weight and are omitted. A trimester
    containing only unweighted items has no weight-total requirement here.
    A missing course raises ValueError. The caller must enforce access control.
    """
    course = db.get(Course, course_id)
    if course is None or course.deleted_at is not None:
        raise ValueError("Course not found")

    warnings = []
    grade_items = db.scalars(
        select(GradeItem)
        .where(GradeItem.course_id == course.id, GradeItem.deleted_at.is_(None))
        .order_by(GradeItem.created_at)
    ).all()
    enrollments = db.scalars(
        select(Enrollment)
        .join(Student, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id == course.id, Enrollment.deleted_at.is_(None), Student.deleted_at.is_(None))
    ).all()

    # Beninese items have no weight. Totals from independently valid trimesters
    # must never be combined into a false course-wide weight warning.
    weights_by_term = {}
    for item in grade_items:
        if item.weight is not None:
            weights_by_term[item.term] = weights_by_term.get(item.term, 0.0) + item.weight
    for term, total_weight in weights_by_term.items():
        if not WEIGHT_TOLERANCE_MIN <= total_weight <= WEIGHT_TOLERANCE_MAX:
            warnings.append(
                _warning(
                    warning_type="grade_weight_total",
                    message=f"{course.name} ({term}) grade item weights total {total_weight:.2f}, not 1.00.",
                    severity="high",
                    entity_type="course",
                    entity_id=course.id,
                )
            )

    grades = db.scalars(
        select(Grade)
        .join(GradeItem, Grade.grade_item_id == GradeItem.id)
        .where(GradeItem.course_id == course.id, GradeItem.deleted_at.is_(None), Grade.deleted_at.is_(None))
    ).all()
    grades_by_student_item = {(grade.student_id, grade.grade_item_id): grade for grade in grades}

    for grade in grades:
        if grade.score < 0:
            warnings.append(
                _warning(
                    warning_type="negative_score",
                    message=f"Score is below 0 for grade item {grade.grade_item.title}.",
                    severity="high",
                    entity_type="grade",
                    entity_id=grade.id,
                )
            )
        if grade.score > grade.grade_item.max_score:
            warnings.append(
                _warning(
                    warning_type="score_above_max",
                    message=(
                        f"Score {grade.score} exceeds max score {grade.grade_item.max_score} "
                        f"for {grade.grade_item.title}."
                    ),
                    severity="high",
                    entity_type="grade",
                    entity_id=grade.id,
                )
            )

    for enrollment in enrollments:
        student = enrollment.student
        missing_items = [
            item for item in grade_items if (student.id, item.id) not in grades_by_student_item
        ]
        if missing_items:
            warnings.append(
                _warning(
                    warning_type="missing_grades",
                    message=(
                        f"{student.first_name} {student.last_name} is missing grades for: "
                        + ", ".join(item.title for item in missing_items)
                    ),
                    severity="medium",
                    entity_type="student",
                    entity_id=student.id,
                )
            )
            continue

        if grade_items:
            course_result = db.scalar(
                select(CourseResult).where(
                    CourseResult.student_id == student.id,
                    CourseResult.course_id == course.id,
                    CourseResult.term == course.term,
                    CourseResult.deleted_at.is_(None),
                )
            )
            if course_result is None:
                warnings.append(
                    _warning(
                        warning_type="missing_course_result",
                        message=(
                            f"{student.first_name} {student.last_name} has complete grades "
                            f"but no calculated course result for {course.name}."
                        ),
                        severity="medium",
                        entity_type="student",
                        entity_id=student.id,
                    )
                )

    return warnings


def check_report_card_data(
    db: Session, report_card_id: UUID, *, course_ids: set[UUID] | None = None
) -> list[dict]:
    """Optional course scope excludes both foreign courses and report-wide warnings."""
    report_card = db.get(ReportCard, report_card_id)
    if report_card is None or report_card.deleted_at is not None:
        raise ValueError("Report card not found")

    warnings = []

    if course_ids is None and report_card.status == "draft" and not report_card.courses:
        warnings.append(
            _warning(
                warning_type="report_missing_courses",
                message="Draft report card has no course rows.",
                severity="high",
                entity_type="report_card",
                entity_id=report_card.id,
            )
        )

    # Out-of-range bound depends on the report's grade scale: historical /100
    # reports allow up to 100, while current /20 reports allow up to 20.
    max_average = 100 if report_card.scale == "100" else 20

    for report_course in report_card.courses:
        if course_ids is not None and report_course.course_id not in course_ids:
            continue
        if report_course.average < 0 or report_course.average > max_average:
            warnings.append(
                _warning(
                    warning_type="report_course_average_out_of_range",
                    message=f"{report_course.course_name} average is outside the 0-{max_average} range.",
                    severity="high",
                    entity_type="report_card_course",
                    entity_id=report_course.id,
                )
            )

        if not report_course.letter_grade:
            warnings.append(
                _warning(
                    warning_type="report_course_missing_letter_grade",
                    message=f"{report_course.course_name} is missing a letter grade.",
                    severity="high",
                    entity_type="report_card_course",
                    entity_id=report_course.id,
                )
            )

    checked_course_ids = {report_course.course_id for report_course in report_card.courses}
    if course_ids is not None:
        checked_course_ids &= course_ids
    for course_id in checked_course_ids:
        warnings.extend(check_course_grade_data(db, course_id))

    return warnings
