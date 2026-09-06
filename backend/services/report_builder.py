"""Build immutable bulletin snapshots and compare them with current results.

The builder consumes completed ``CourseResult`` rows rather than live grade
items, normalizes historical values to /20, and freezes the values parents
later receive in approved bulletins. It keeps French, English, and bilingual
averages separate because GGFK operates parallel language tracks; bilingual is
the equal blend of the two track averages and is absent until both exist.
Conduct and work-habit letter assessments are snapshot domains distinct from
numeric course averages.

Courses are coefficient-weighted within each track and in the overall average
when an admin configures coefficients; coefficient 1 preserves equal weight,
which is the effective state of all current courses. Coefficients remain
calculation metadata and are intentionally absent from the printed bulletin,
matching the school's official format. Do not add a printed ``Coef`` column.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from constants import (
    CONDUCT_ITEMS,
    FINAL_TRIMESTER_NUMBER,
    GRADING_KEY_LEGEND,
    TERM_ORDINAL_EN,
    TERM_ORDINAL_FR,
    TRIMESTER_DATE_RANGES,
    WORK_HABIT_ITEMS,
    appreciation_for_letter,
    term_number,
)
from models import Course, CourseResult, ReportCard, ReportCardCourse, Student, StudentClassAssignment
from schemas import LanguageGroup
from services.class_stats import compute_class_stats
from services.annual_averages import ANNUAL_REPORT_STATUSES, compute_student_annual_averages
from services.grade_calculator import (
    calculate_gpa,
    calculate_overall_average,
    calculate_weighted_average,
    normalize_average_to_20,
)
from services.student_assignments import assignment_for_student_year


STALE_FLOAT_TOLERANCE = 0.005
REVIEW_REQUIRED_STATUS = "needs_review"


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
    if student is None or student.deleted_at is not None:
        raise ValueError("Student not found")

    course_results = db.scalars(
        select(CourseResult)
        .join(Course, CourseResult.course_id == Course.id)
        .where(
            CourseResult.student_id == student.id,
            CourseResult.term == term,
            Course.school_year == school_year,
            CourseResult.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
        .order_by(Course.name, Course.code)
    ).all()
    if not course_results:
        raise ValueError("Student has no course results for the requested term and school year")

    # Normalize each result to /20 by its stored scale so a report mixing
    # pre-A1.2 (/100) and post-A1.2 (/20) course results is computed on one
    # scale. letter_grade is scale-invariant (A on /100 == A on /20), so the
    # stored letter is kept as-is.
    courses = [
        {
            "course_id": course_result.course_id,
            "course_name": course_result.course.name,
            "course_code": course_result.course.code,
            "average": normalize_average_to_20(course_result.average, course_result.scale),
            "letter_grade": course_result.letter_grade,
            "language_group": course_result.course.language_group,
            "coefficient": course_result.course.coefficient,
            "moy_int": course_result.moy_int,
            "mcc": course_result.mcc,
            "devoir_score": course_result.devoir_score,
            "composition_score": course_result.composition_score,
        }
        for course_result in course_results
    ]
    course_averages = [course["average"] for course in courses]
    coefficients = [course["coefficient"] for course in courses]

    # A1.6 three parallel-track averages. Admin-configured coefficients apply
    # here; coefficient 1 is deliberately ordinary equal weight. The reference
    # coefficient catalog guides upper-class setup but is not auto-loaded,
    # because the admin owns each course's configuration.
    # Untagged (null-language_group) courses are excluded from track averages.
    def _group_average(group: str) -> float | None:
        group_courses = [c for c in courses if c["language_group"] == group]
        if not group_courses:
            return None
        return calculate_weighted_average(
            [c["average"] for c in group_courses],
            [c["coefficient"] for c in group_courses],
        )

    french_average = _group_average(LanguageGroup.FRENCH.value)
    english_average = _group_average(LanguageGroup.ENGLISH.value)
    if french_average is not None and english_average is not None:
        # The two language tracks carry equal institutional weight. Averaging
        # every course together would let the track with more subjects dominate
        # and would no longer represent GGFK's parallel-track design.
        bilingual_average = calculate_overall_average([french_average, english_average])
    else:
        bilingual_average = None

    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_number": student.student_number,
            "class_name": student.school_class.name_fr if student.school_class else None,
        },
        "term": term,
        "school_year": school_year,
        "courses": courses,
        "overall_average": calculate_weighted_average(course_averages, coefficients),
        "french_average": french_average,
        "english_average": english_average,
        "bilingual_average": bilingual_average,
        "gpa": calculate_gpa(course_averages),
        # Live recomputation always yields a /20 report.
        "scale": "20",
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
    """Compare an official snapshot with the result set available now.

    Persisted ``needs_review`` is stale even when numeric values match because
    human-authored bulletin content changed after approval/sending. For other
    statuses, compare snapshot totals, course membership, course averages, and
    letters; inability to rebuild current data is also stale, not "unchanged".
    This conservative rule prevents obsolete or incomplete academic data from
    being re-approved merely because comparison data disappeared.
    """
    if report_card.status == REVIEW_REQUIRED_STATUS:
        return ReportCardStaleness(
            is_stale=True,
            reason="Report content changed after approval or sending.",
            snapshot_overall_average=report_card.overall_average,
            current_overall_average=None,
            snapshot_gpa=report_card.gpa,
            current_gpa=None,
        )

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

    snapshot_scale = report_card.scale or "20"
    reasons: list[str] = []
    if not _numbers_match(normalize_average_to_20(report_card.overall_average, snapshot_scale), current_data["overall_average"]):
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
            snapshot_avg = normalize_average_to_20(snapshot_course.average, snapshot_scale)
            if not _numbers_match(snapshot_avg, current_course["average"]):
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


def _merge_report_items(stored_items, definitions) -> list[dict]:
    """Merge stored conduct/work-habit rows onto the canonical list, so every
    item appears in order with letter_grade None when unassessed (A1.7b)."""
    grade_by_key = {item.item_key: item.letter_grade for item in stored_items}
    return [
        {"key": key, "en_label": en_label, "fr_label": fr_label, "letter_grade": grade_by_key.get(key)}
        for key, en_label, fr_label in definitions
    ]


def build_report_card_data_from_report_card(db: Session, report_card: ReportCard) -> dict:
    """Reconstruct report_data from a stored ReportCard + ReportCardCourse snapshot.

    Uses only persisted values — no CourseResult recomputation, no OpenAI, no DB
    writes. course_code is resolved from the live Course row (by course_id); a course
    that no longer exists falls back to "N/A".
    """
    student = report_card.student

    course_ids = [course.course_id for course in report_card.courses]
    code_by_course_id: dict = {}
    language_by_course_id: dict = {}
    if course_ids:
        for course in db.scalars(
            select(Course).where(Course.id.in_(course_ids), Course.deleted_at.is_(None))
        ).all():
            code_by_course_id[course.id] = course.code
            language_by_course_id[course.id] = course.language_group

    courses = [
        {
            "course_id": course.course_id,
            "course_name": course.course_name,
            "course_code": code_by_course_id.get(course.course_id, "N/A"),
            "average": course.average,
            "letter_grade": course.letter_grade,
            # A1.7b: French appreciation + language track (resolved live, since the
            # snapshot ReportCardCourse rows don't carry language_group).
            "appreciation": appreciation_for_letter(course.letter_grade),
            "language_group": language_by_course_id.get(course.course_id),
            "coefficient": course.coefficient,
            "moy_int": course.moy_int,
            "mcc": course.mcc,
            "devoir_score": course.devoir_score,
            "composition_score": course.composition_score,
        }
        for course in report_card.courses
    ]
    courses.sort(key=lambda course: (course["course_name"] or "", course["course_code"] or ""))

    courses_by_language = {
        "french_courses": [c for c in courses if c["language_group"] == LanguageGroup.FRENCH.value],
        "english_courses": [c for c in courses if c["language_group"] == LanguageGroup.ENGLISH.value],
        "untagged_courses": [
            c
            for c in courses
            if c["language_group"] not in (LanguageGroup.FRENCH.value, LanguageGroup.ENGLISH.value)
        ],
    }

    generated_date = (
        report_card.created_at.isoformat(timespec="seconds")
        if report_card.created_at is not None
        else None
    )

    # --- A1.7b bulletin sections ---
    conduct_items = _merge_report_items(report_card.conduct_items, CONDUCT_ITEMS)
    work_habit_items = _merge_report_items(report_card.work_habit_items, WORK_HABIT_ITEMS)

    current_term_num = term_number(report_card.term)
    class_stats = compute_class_stats(db, student, report_card.term, report_card.school_year)

    def _track_block(source_report, stats, track):
        return {
            "student": getattr(source_report, f"{track}_average"),
            "class_highest": stats[track]["highest"],
            "class_lowest": stats[track]["lowest"],
        }

    three_averages = {
        "term_number": current_term_num,
        "french": _track_block(report_card, class_stats, "french"),
        "english": _track_block(report_card, class_stats, "english"),
        "bilingual": _track_block(report_card, class_stats, "bilingual"),
        "annual": {"french": None, "english": None, "bilingual": None},
    }

    previous_term_averages = []
    prior_reports = db.scalars(
        select(ReportCard).where(
            ReportCard.student_id == student.id,
            ReportCard.school_year == report_card.school_year,
            ReportCard.id != report_card.id,
            ReportCard.status.in_(ANNUAL_REPORT_STATUSES),
            ReportCard.deleted_at.is_(None),
        )
    ).all()
    for prior in prior_reports:
        prior_stats = compute_class_stats(db, student, prior.term, report_card.school_year)
        previous_term_averages.append(
            {
                "term_number": term_number(prior.term),
                "term": prior.term,
                "french": _track_block(prior, prior_stats, "french"),
                "english": _track_block(prior, prior_stats, "english"),
                "bilingual": _track_block(prior, prior_stats, "bilingual"),
            }
        )
    previous_term_averages.sort(key=lambda entry: (entry["term_number"] is None, entry["term_number"] or 0))

    # Annual = mean of the student's own track averages across the year's trims,
    # populated only in the final trimester and only where values exist.
    annual_details = {
        "french": None,
        "english": None,
        "bilingual": None,
        "complete_terms": [],
        "missing_terms": [],
        "complete_term_count": 0,
        "total_term_count": FINAL_TRIMESTER_NUMBER,
        "is_partial": False,
    }
    if current_term_num == FINAL_TRIMESTER_NUMBER:
        annual = compute_student_annual_averages(db, student.id, report_card.school_year)
        annual_details = {
            "french": annual.french,
            "english": annual.english,
            "bilingual": annual.bilingual,
            "complete_terms": annual.complete_terms,
            "missing_terms": annual.missing_terms,
            "complete_term_count": len(annual.complete_terms),
            "total_term_count": FINAL_TRIMESTER_NUMBER,
            "is_partial": len(annual.complete_terms) < FINAL_TRIMESTER_NUMBER,
        }
    three_averages["annual"] = annual_details

    # Template convenience: per-trimester (1..3) track blocks for the averages
    # grid. Reports whose term isn't a recognized trimester simply don't appear.
    trim_lookup = {three_averages["term_number"]: three_averages}
    for entry in previous_term_averages:
        trim_lookup.setdefault(entry["term_number"], entry)
    _empty_track = {"student": None, "class_highest": None, "class_lowest": None}
    averages_grid = {
        trim: {
            track: (trim_lookup[trim][track] if trim in trim_lookup else _empty_track)
            for track in ("french", "english", "bilingual")
        }
        for trim in (1, 2, 3)
    }

    assignment = assignment_for_student_year(db, student.id, report_card.school_year)
    school_class = assignment.school_class if assignment is not None else None
    historical_class_name = assignment.class_name_snapshot if assignment is not None else None
    class_block = None
    class_effectif = None
    if assignment is not None:
        class_block = {
            "name_fr": historical_class_name,
            "name_en": school_class.name_en if school_class is not None else None,
        }
        if assignment.class_id is not None:
            class_effectif = db.scalar(
                select(func.count(StudentClassAssignment.id)).where(
                    StudentClassAssignment.school_year == report_card.school_year,
                    StudentClassAssignment.class_id == assignment.class_id,
                )
            )

    term_dates_en, term_dates_fr = TRIMESTER_DATE_RANGES.get(current_term_num, (None, None))

    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "full_name": f"{student.first_name} {student.last_name}",
            "student_number": student.student_number,
            "educmaster_number": student.educmaster_number,
            "class_name": historical_class_name,
        },
        "term": report_card.term,
        "school_year": report_card.school_year,
        "term_number": current_term_num,
        "is_final_trimester": current_term_num == FINAL_TRIMESTER_NUMBER,
        "term_ordinal_en": TERM_ORDINAL_EN.get(current_term_num),
        "term_ordinal_fr": TERM_ORDINAL_FR.get(current_term_num),
        "term_dates_en": term_dates_en,
        "term_dates_fr": term_dates_fr,
        "school_class": class_block,
        "class_effectif": class_effectif,
        "courses": courses,
        "courses_by_language": courses_by_language,
        "overall_average": report_card.overall_average,
        "gpa": report_card.gpa,
        "scale": report_card.scale,
        "three_averages": three_averages,
        "annual_averages": annual_details,
        "previous_term_averages": previous_term_averages,
        "averages_grid": averages_grid,
        "class_stats": class_stats,
        "conduct_items": conduct_items,
        "work_habit_items": work_habit_items,
        "teacher_comment_fr": report_card.teacher_comment_fr,
        "teacher_comment_en": report_card.teacher_comment_en,
        "principal_comment_fr": report_card.principal_comment_fr,
        "principal_comment_en": report_card.principal_comment_en,
        "grading_key": GRADING_KEY_LEGEND,
        "ai_summary": report_card.ai_summary,
        "status": report_card.status,
        "generated_date": generated_date,
    }
