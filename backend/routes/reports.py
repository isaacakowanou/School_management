"""Official bulletin lifecycle, class-level processing, and publication routes.

Bulletins are immutable academic snapshots with a controlled state machine:
``draft -> approved -> sent`` plus ``needs_review``. Editing conduct, work
habits, or comments after approval persists ``needs_review`` because the stored
document must never silently diverge from what staff approved or parents
received. Newer course results derive the same review state for list views.
Recovery is regeneration back to a draft, followed by approval and sending;
human-entered details survive regeneration while computed course rows do not.

Parents can read only approved/sent snapshots, so moving a sent bulletin to
``needs_review`` intentionally withdraws it. Staleness guards block approving
or sending obsolete snapshots unless an admin explicitly acknowledges the
override. Class batch actions and asynchronous merged PDFs support the Conseil
de classe workflow, where the school processes a whole class each trimester.
APPROVE publishes the reviewed snapshot to the parent portal; ENVOYER only
delivers a notification that the already-published snapshot is available.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from auth import get_current_user, require_admin
from audit import create_audit_log
from constants import CONDUCT_ITEMS, CONDUCT_ITEM_KEYS, WORK_HABIT_ITEMS, WORK_HABIT_ITEM_KEYS
from database import SessionLocal, get_db
from models import (
    Class,
    Course,
    CourseResult,
    Enrollment,
    GradeItem,
    Parent,
    PdfJob,
    ReportCard,
    ReportCardCourse,
    ReportConductItem,
    ReportGenerationJob,
    ReportWorkHabitItem,
    Student,
    StudentClassAssignment,
    StudentParent,
    StudentPassageDecision,
    User,
)
from schemas import (
    AdminReportListItem,
    AdminReportCardResponse,
    ClassPdfJobResponse,
    ClassReportBatchApproveResponse,
    ClassReportBatchGenerateResponse,
    ClassReportBatchRequest,
    ClassReportBatchSendResponse,
    ClassReportStatusResponse,
    ClassReportStatusRow,
    PartialReportStudent,
    ReportBulkGenerateRequest,
    ReportApproveRequest,
    ReportCardCourseResponse,
    ReportCardResponse,
    ReportCardStalenessResponse,
    ReportDetailsUpdate,
    ReportGenerateRequest,
    ReportItemResponse,
    ReportGenerationJobResponse,
    ReportReviewUpdate,
    ReportSendRequest,
    ReportSendResponse,
    StaleReportStudent,
)
from services.email_service import send_report_notification_to_parents
from services.pdf_renderer import (
    _build_pdf_filename,
    _safe_filename_part,
    render_class_bulletins_pdf_bytes,
    render_report_card_pdf_bytes,
)
from services.report_builder import (
    build_report_card_data,
    build_report_card_data_from_report_card,
    get_report_card_staleness,
)
from utils import get_class_or_404, get_report_card_or_404, historical_class_name_for_student_year


router = APIRouter(tags=["reports"])
# This is the publication boundary for averages and rankings. Parents may see
# individual grade-item scores mid-trimester, but only approved/sent snapshots
# expose calculated averages; draft/needs-review reports remain staff-only.
PARENT_VISIBLE_STATUSES = {"approved", "sent"}
REVIEW_REQUIRED_STATUS = "needs_review"

_REPORT_COMMENT_FIELDS = (
    "teacher_comment_fr",
    "teacher_comment_en",
    "principal_comment_fr",
    "principal_comment_en",
)


def _build_report_items(stored_items, item_definitions) -> list[ReportItemResponse]:
    """Merge stored (assessed) rows onto the full canonical item list so the
    response always carries every row in order, with letter_grade null for
    items that haven't been assessed."""
    grade_by_key = {item.item_key: item.letter_grade for item in stored_items}
    return [
        ReportItemResponse(
            item_key=key,
            label_en=label_en,
            label_fr=label_fr,
            letter_grade=grade_by_key.get(key),
        )
        for key, label_en, label_fr in item_definitions
    ]


def _report_details_snapshot(report_card: ReportCard) -> dict:
    """Audit-log snapshot of the A1.7a fields (comments + assessed items)."""
    snapshot = {field: getattr(report_card, field) for field in _REPORT_COMMENT_FIELDS}
    snapshot["conduct_items"] = {item.item_key: item.letter_grade for item in report_card.conduct_items}
    snapshot["work_habit_items"] = {item.item_key: item.letter_grade for item in report_card.work_habit_items}
    return snapshot


def _changed_report_detail_categories(old_value: dict, new_value: dict) -> list[str]:
    categories = []
    if old_value.get("conduct_items") != new_value.get("conduct_items"):
        categories.append("conduct")
    if old_value.get("work_habit_items") != new_value.get("work_habit_items"):
        categories.append("work_habits")
    if any(old_value.get(field) != new_value.get(field) for field in _REPORT_COMMENT_FIELDS):
        categories.append("comments")
    return categories


def _validated_report_item_rows(items, allowed_keys, model_cls):
    """Validate item_keys against the canonical set and build ORM rows for the
    assessed (non-null) items only. A blank letter_grade means 'not assessed'
    and is represented by the row's absence."""
    rows = []
    seen: set[str] = set()
    for item in items:
        if item.item_key not in allowed_keys:
            raise HTTPException(status_code=422, detail=f"Unknown item_key: {item.item_key}")
        if item.item_key in seen:
            raise HTTPException(status_code=422, detail=f"Duplicate item_key: {item.item_key}")
        seen.add(item.item_key)
        if item.letter_grade is not None:
            rows.append(model_cls(item_key=item.item_key, letter_grade=item.letter_grade.value))
    return rows


def _historical_class_for_report_card(db: Session | None, report_card: ReportCard) -> tuple[UUID | None, str | None]:
    for snapshot_course in report_card.courses:
        if snapshot_course.course is not None and snapshot_course.course.school_class is not None:
            return snapshot_course.course.school_class.id, snapshot_course.course.school_class.name_fr
    if db is not None:
        course_class = db.execute(
            select(Class.id, Class.name_fr)
            .join(Course, Course.class_id == Class.id)
            .join(ReportCardCourse, ReportCardCourse.course_id == Course.id)
            .where(
                ReportCardCourse.report_card_id == report_card.id,
                ReportCardCourse.deleted_at.is_(None),
                Course.school_year == report_card.school_year,
                Course.deleted_at.is_(None),
                Class.deleted_at.is_(None),
            )
            .order_by(Class.sort_order, Class.name_fr)
            .limit(1)
        ).first()
        if course_class is not None:
            return course_class[0], course_class[1]

        decision = db.execute(
            select(StudentPassageDecision.from_class_id, StudentPassageDecision.from_class_name)
            .where(
                StudentPassageDecision.student_id == report_card.student_id,
                StudentPassageDecision.school_year == report_card.school_year,
            )
            .order_by(StudentPassageDecision.decided_at.desc())
            .limit(1)
        ).first()
        if decision is not None and decision[1]:
            return decision[0], decision[1]

        return None, historical_class_name_for_student_year(db, report_card.student_id, report_card.school_year)
    return None, None


def _historical_class_name_for_report_card(db: Session | None, report_card: ReportCard) -> str | None:
    return _historical_class_for_report_card(db, report_card)[1]


def to_report_card_response(report_card: ReportCard, db: Session | None = None) -> ReportCardResponse:
    student = report_card.student
    return ReportCardResponse(
        id=report_card.id,
        student_id=report_card.student_id,
        student_name=f"{student.first_name} {student.last_name}" if student else None,
        student_number=student.student_number if student else None,
        academic_status=student.academic_status if student else None,
        student_class_name=_historical_class_name_for_report_card(db, report_card),
        term=report_card.term,
        school_year=report_card.school_year,
        overall_average=report_card.overall_average,
        french_average=report_card.french_average,
        english_average=report_card.english_average,
        bilingual_average=report_card.bilingual_average,
        gpa=report_card.gpa,
        scale=report_card.scale,
        status=report_card.status,
        created_at=report_card.created_at,
        ai_summary=report_card.ai_summary,
        teacher_comment_fr=report_card.teacher_comment_fr,
        teacher_comment_en=report_card.teacher_comment_en,
        principal_comment_fr=report_card.principal_comment_fr,
        principal_comment_en=report_card.principal_comment_en,
        pdf_url=report_card.pdf_url,
        courses=[
            ReportCardCourseResponse(
                id=course.id,
                course_id=course.course_id,
                course_name=course.course_name,
                average=course.average,
                letter_grade=course.letter_grade,
                coefficient=course.coefficient,
                moy_int=course.moy_int,
                mcc=course.mcc,
                devoir_score=course.devoir_score,
                composition_score=course.composition_score,
            )
            for course in report_card.courses
        ],
        conduct_items=_build_report_items(report_card.conduct_items, CONDUCT_ITEMS),
        work_habit_items=_build_report_items(report_card.work_habit_items, WORK_HABIT_ITEMS),
    )


def to_admin_report_card_response(report_card: ReportCard, db: Session | None = None) -> AdminReportCardResponse:
    student = report_card.student
    base = to_report_card_response(report_card, db).model_dump()
    base.pop("student_name", None)
    base.pop("student_number", None)
    return AdminReportCardResponse(
        **base,
        student_name=f"{student.first_name} {student.last_name}",
        student_number=student.student_number,
    )


def _datetime_for_compare(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _course_result_key(student_id: UUID, term: str, school_year: str) -> tuple[UUID, str, str]:
    return (student_id, term, school_year)


def _report_needs_review(report_card: ReportCard, latest_calculated_at: datetime | None) -> bool:
    """Unify persisted content edits and derived grade staleness for admin UI.

    Keep this as the single list/class-view interpretation; otherwise the same
    bulletin could receive different badges or filters depending on whether a
    human field or a course result caused re-review.
    """
    if report_card.status == REVIEW_REQUIRED_STATUS:
        return True
    if report_card.status not in PARENT_VISIBLE_STATUSES:
        return False
    if report_card.approved_at is None or latest_calculated_at is None:
        return False

    latest = _datetime_for_compare(latest_calculated_at)
    approved_at = _datetime_for_compare(report_card.approved_at)
    return latest is not None and approved_at is not None and latest > approved_at


def _latest_course_result_times_by_report_key(db: Session) -> dict[tuple[UUID, str, str], datetime]:
    rows = db.execute(
        select(
            CourseResult.student_id,
            CourseResult.term,
            Course.school_year,
            func.max(CourseResult.calculated_at).label("latest_calculated_at"),
        )
        .join(Course, CourseResult.course_id == Course.id)
        .where(CourseResult.deleted_at.is_(None), Course.deleted_at.is_(None))
        .group_by(CourseResult.student_id, CourseResult.term, Course.school_year)
    ).all()
    return {
        _course_result_key(student_id, term, school_year): latest_calculated_at
        for student_id, term, school_year, latest_calculated_at in rows
    }


def to_admin_report_list_item(
    report_card: ReportCard,
    *,
    needs_review: bool,
    db: Session | None = None,
) -> AdminReportListItem:
    student = report_card.student
    class_id, class_name = _historical_class_for_report_card(db, report_card)
    return AdminReportListItem(
        id=report_card.id,
        student_id=report_card.student_id,
        student_name=f"{student.first_name} {student.last_name}",
        student_number=student.student_number,
        student_class_id=class_id,
        student_class_name=class_name,
        term=report_card.term,
        school_year=report_card.school_year,
        status=report_card.status,
        overall_average=report_card.overall_average,
        bilingual_average=report_card.bilingual_average,
        gpa=report_card.gpa,
        scale=report_card.scale,
        created_at=report_card.created_at,
        needs_review=needs_review,
    )


def parent_can_access_student(db: Session, current_user: User, student_id: UUID) -> bool:
    parent = db.scalar(select(Parent).where(Parent.user_id == current_user.id))
    if parent is None or parent.deleted_at is not None:
        return False

    student_link = db.scalar(
        select(StudentParent)
        .join(Student, StudentParent.student_id == Student.id)
        .where(
            StudentParent.parent_id == parent.id,
            StudentParent.student_id == student_id,
            StudentParent.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
    )
    return student_link is not None


def parent_can_access_report(db: Session, current_user: User, report_card: ReportCard) -> bool:
    return (
        report_card.status in PARENT_VISIBLE_STATUSES
        and report_card.deleted_at is None
        and report_card.student.deleted_at is None
        and parent_can_access_student(db, current_user, report_card.student_id)
    )


def ensure_can_view_report(db: Session, current_user: User, report_card: ReportCard) -> None:
    if current_user.role == "admin":
        if report_card.deleted_at is not None or report_card.student.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")
        return
    if current_user.role == "parent" and parent_can_access_report(db, current_user, report_card):
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def ensure_report_student_active(report_card: ReportCard) -> None:
    if report_card.deleted_at is not None or report_card.student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")


def ensure_report_is_draft(report_card: ReportCard) -> None:
    # needs_review cannot be re-approved in place. Regeneration must first
    # create a fresh computed snapshot and deliberately return it to draft.
    if report_card.status != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft reports can be reviewed")


def ensure_report_can_be_sent(report_card: ReportCard) -> None:
    if report_card.status not in {"approved", "sent"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved or sent reports can be sent")


def update_report_summary(report_card: ReportCard, payload: ReportReviewUpdate) -> tuple[str | None, str | None]:
    # ai_summary is screen-only assistance and is not rendered on the official
    # PDF. Its edits intentionally do not invalidate approval or sending.
    old_summary = report_card.ai_summary
    if "ai_summary" in payload.model_fields_set:
        report_card.ai_summary = payload.ai_summary
    return old_summary, report_card.ai_summary


def log_summary_edit_if_needed(
    db: Session,
    actor_user_id: UUID,
    report_card: ReportCard,
    payload: ReportReviewUpdate,
    old_summary: str | None,
    new_summary: str | None,
) -> None:
    if "ai_summary" not in payload.model_fields_set:
        return

    create_audit_log(
        db=db,
        actor_user_id=actor_user_id,
        action="summary_edited",
        entity_type="report_card",
        entity_id=report_card.id,
        old_value={"ai_summary": old_summary},
        new_value={"ai_summary": new_summary},
    )


def _email_result_provider(send_results: list[dict]) -> str | None:
    providers = sorted({result.get("provider") for result in send_results if result.get("provider")})
    if not providers:
        return None
    if len(providers) == 1:
        return providers[0]
    return "mixed"


def _email_message_ids(send_results: list[dict]) -> list[str]:
    return [
        str(result["provider_message_id"])
        for result in send_results
        if result.get("provider_message_id")
    ]


def _email_error_summary(send_results: list[dict]) -> list[str]:
    errors = []
    for result in send_results:
        error = result.get("error")
        if error and error not in errors:
            errors.append(error)
    return errors[:3]


def _create_report_card(db: Session, student_id: UUID, term: str, school_year: str) -> ReportCard:
    """Build and stage a draft report card + course snapshot rows.

    Shared by the single and batch generate routes. Raises ValueError (from
    build_report_card_data) for missing students or missing course results;
    flushes but does NOT commit — the caller owns the transaction.
    """
    # Snapshot now rather than recomputing on read: an approved official
    # document must retain exactly the figures that were reviewed.
    report_data = build_report_card_data(db, student_id, term, school_year)

    report_card = ReportCard(
        student_id=student_id,
        term=term,
        school_year=school_year,
        overall_average=report_data["overall_average"],
        french_average=report_data["french_average"],
        english_average=report_data["english_average"],
        bilingual_average=report_data["bilingual_average"],
        gpa=report_data["gpa"],
        scale="20",
        status="draft",
        ai_summary=None,
    )
    db.add(report_card)
    db.flush()
    # No file storage (A1.7b): the PDF is rendered on demand, so pdf_url simply
    # points at the download endpoint.
    report_card.pdf_url = f"/api/v1/reports/{report_card.id}/pdf"

    for course in report_data["courses"]:
        db.add(
            ReportCardCourse(
                report_card_id=report_card.id,
                course_id=course["course_id"],
                course_name=course["course_name"],
                average=course["average"],
                letter_grade=course["letter_grade"],
                coefficient=course["coefficient"],
                moy_int=course["moy_int"],
                mcc=course["mcc"],
                devoir_score=course["devoir_score"],
                composition_score=course["composition_score"],
            )
        )
    return report_card


def _expected_result_courses(db: Session, student_id: UUID, term: str, school_year: str) -> list[Course]:
    """Active enrolled courses that are actually gradeable for this term.

    A course with zero active grade items is setup-only and does not block
    bulletin generation.
    """
    return list(
        db.scalars(
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .join(Course.grade_items)
            .where(
                Enrollment.student_id == student_id,
                Enrollment.deleted_at.is_(None),
                Course.term == term,
                Course.school_year == school_year,
                Course.deleted_at.is_(None),
                GradeItem.term == term,
                GradeItem.deleted_at.is_(None),
            )
            .distinct()
            .order_by(Course.name, Course.code)
        ).all()
    )


def _result_course_ids(db: Session, student_id: UUID, term: str, school_year: str) -> set[UUID]:
    return set(
        db.scalars(
            select(CourseResult.course_id)
            .join(Course, CourseResult.course_id == Course.id)
            .where(
                CourseResult.student_id == student_id,
                CourseResult.term == term,
                Course.school_year == school_year,
                CourseResult.deleted_at.is_(None),
                Course.deleted_at.is_(None),
            )
        ).all()
    )


def _partial_report_student(db: Session, student: Student, term: str, school_year: str) -> PartialReportStudent:
    expected_courses = _expected_result_courses(db, student.id, term, school_year)
    result_course_ids = _result_course_ids(db, student.id, term, school_year)
    missing_courses = [course for course in expected_courses if course.id not in result_course_ids]
    return PartialReportStudent(
        student_id=student.id,
        student_name=f"{student.last_name}, {student.first_name}",
        student_number=student.student_number,
        expected_results_count=len(expected_courses),
        results_count=len([course for course in expected_courses if course.id in result_course_ids]),
        missing_course_names=[course.name for course in missing_courses],
    )


def _ensure_complete_or_allowed(db: Session, student: Student, term: str, school_year: str, generate_partial: bool) -> None:
    partial = _partial_report_student(db, student, term, school_year)
    if partial.missing_course_names and not generate_partial:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Report results are incomplete",
                "code": "partial_results",
                "student_id": str(partial.student_id),
                "student_name": partial.student_name,
                "expected_results_count": partial.expected_results_count,
                "results_count": partial.results_count,
                "missing_course_names": partial.missing_course_names,
            },
        )


def _staleness_guard_code(staleness) -> str:
    if staleness.current_overall_average is None:
        return "incomplete_report_results"
    return "stale_report_snapshot"


def _stale_report_student(report_card: ReportCard, staleness) -> StaleReportStudent:
    student = report_card.student
    return StaleReportStudent(
        student_id=student.id,
        student_name=f"{student.last_name}, {student.first_name}",
        student_number=student.student_number,
        report_id=report_card.id,
        code=_staleness_guard_code(staleness),
        reason=staleness.reason,
    )


def _ensure_report_snapshot_fresh_or_allowed(db: Session, report_card: ReportCard, allow_stale: bool) -> None:
    """Require current snapshot data or an explicit admin override.

    A 409 lets the UI show the old/new context before retrying with the override;
    silently recomputing here would change the official document being approved
    or sent without returning it through draft review.
    """
    staleness = get_report_card_staleness(db, report_card)
    if not staleness.is_stale or allow_stale:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "Report snapshot is stale",
            "code": _staleness_guard_code(staleness),
            "report_id": str(report_card.id),
            "reason": staleness.reason,
            "snapshot_overall_average": staleness.snapshot_overall_average,
            "current_overall_average": staleness.current_overall_average,
            "snapshot_gpa": staleness.snapshot_gpa,
            "current_gpa": staleness.current_gpa,
        },
    )


@router.post("/generate/{student_id}", response_model=ReportCardResponse, status_code=status.HTTP_201_CREATED)
def generate_report_card(
    student_id: UUID,
    payload: ReportGenerateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReportCardResponse:
    student = db.get(Student, student_id)
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    _ensure_complete_or_allowed(db, student, payload.term.value, payload.school_year, payload.generate_partial)
    try:
        report_card = _create_report_card(db, student_id, payload.term.value, payload.school_year)
    except ValueError as exc:
        detail = str(exc)
        if detail == "Student not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    db.commit()
    db.refresh(report_card)
    return to_report_card_response(report_card, db)


# --- Conseil de classe: class-scoped status + batch actions -----------------
# GGFK closes each of three trimesters as a class-level ceremony. These routes
# intentionally mirror the single-student guards while removing repetitive
# per-student clicks; batch convenience must never weaken snapshot integrity.
# NOTE: these are static paths and must stay declared before the /{report_id}
# routes further down, or FastAPI tries to parse them as report UUIDs.


def _class_students(db: Session, class_id: UUID, school_year: str | None = None) -> list[Student]:
    assignment_query = (
        select(Student)
        .join(StudentClassAssignment, StudentClassAssignment.student_id == Student.id)
        .where(
            StudentClassAssignment.class_id == class_id,
            Student.deleted_at.is_(None),
            Student.academic_status == "active",
        )
    )
    if school_year is not None:
        assignment_query = assignment_query.where(StudentClassAssignment.school_year == school_year)
    students = list(
        db.scalars(assignment_query.order_by(Student.last_name, Student.first_name)).all()
    )
    by_id = {student.id: student for student in students}
    if school_year is not None:
        historical_students = db.scalars(
            select(Student)
            .join(StudentPassageDecision, StudentPassageDecision.student_id == Student.id)
            .where(
                StudentPassageDecision.from_class_id == class_id,
                StudentPassageDecision.school_year == school_year,
                Student.deleted_at.is_(None),
            )
            .order_by(Student.last_name, Student.first_name)
        ).all()
        for student in historical_students:
            by_id.setdefault(student.id, student)
    return sorted(by_id.values(), key=lambda student: (student.last_name, student.first_name))


def _reports_by_student(
    db: Session, student_ids: list[UUID], term: str, school_year: str
) -> dict[UUID, ReportCard]:
    """Latest non-deleted report card per student for (term, school_year)."""
    if not student_ids:
        return {}
    report_cards = db.scalars(
        select(ReportCard)
        .where(
            ReportCard.student_id.in_(student_ids),
            ReportCard.term == term,
            ReportCard.school_year == school_year,
            ReportCard.deleted_at.is_(None),
        )
        .order_by(ReportCard.created_at)
    ).all()
    by_student: dict[UUID, ReportCard] = {}
    for report_card in report_cards:
        by_student[report_card.student_id] = report_card
    return by_student


@router.get("/class-status", response_model=ClassReportStatusResponse)
def class_report_status(
    class_id: UUID,
    school_year: str,
    term: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ClassReportStatusResponse:
    school_class = get_class_or_404(db, class_id)
    students = _class_students(db, class_id, school_year)
    student_ids = [student.id for student in students]

    results_by_student: dict[UUID, int] = {}
    if student_ids:
        results_by_student = dict(
            db.execute(
                select(CourseResult.student_id, func.count(CourseResult.id))
                .join(Course, CourseResult.course_id == Course.id)
                .where(
                    CourseResult.student_id.in_(student_ids),
                    CourseResult.term == term,
                    Course.school_year == school_year,
                    CourseResult.deleted_at.is_(None),
                    Course.deleted_at.is_(None),
                )
                .group_by(CourseResult.student_id)
            ).all()
        )

    reports_by_student = _reports_by_student(db, student_ids, term, school_year)
    latest_by_key = _latest_course_result_times_by_report_key(db)

    rows = []
    without_report = 0
    status_counts = {"draft": 0, "approved": 0, "sent": 0}
    needs_review_count = 0
    for student in students:
        report_card = reports_by_student.get(student.id)
        partial = _partial_report_student(db, student, term, school_year)
        needs_review = False
        if report_card is None:
            without_report += 1
        else:
            status_counts[report_card.status] = status_counts.get(report_card.status, 0) + 1
            needs_review = _report_needs_review(
                report_card,
                latest_by_key.get(_course_result_key(student.id, term, school_year)),
            )
            if needs_review:
                needs_review_count += 1
        rows.append(
            ClassReportStatusRow(
                student_id=student.id,
                student_name=f"{student.last_name}, {student.first_name}",
                student_number=student.student_number,
                results_count=results_by_student.get(student.id, 0),
                expected_results_count=partial.expected_results_count,
                missing_results_count=len(partial.missing_course_names),
                missing_course_names=partial.missing_course_names,
                report_id=report_card.id if report_card else None,
                report_status=report_card.status if report_card else None,
                overall_average=report_card.overall_average if report_card else None,
                french_average=report_card.french_average if report_card else None,
                english_average=report_card.english_average if report_card else None,
                bilingual_average=report_card.bilingual_average if report_card else None,
                needs_review=needs_review,
            )
        )

    return ClassReportStatusResponse(
        class_id=class_id,
        class_name=school_class.name_fr,
        school_year=school_year,
        term=term,
        students=rows,
        total_students=len(students),
        without_report_count=without_report,
        draft_count=status_counts["draft"],
        approved_count=status_counts["approved"],
        sent_count=status_counts["sent"],
        needs_review_count=needs_review_count,
    )


def _generate_reports_for_class(
    db: Session,
    *,
    school_class: Class,
    term: str,
    school_year: str,
    generate_partial: bool,
    current_user: User,
) -> dict:
    """Generate missing draft bulletins for one class without touching
    existing approved/sent snapshots."""
    students = _class_students(db, school_class.id, school_year)
    student_ids = [student.id for student in students]
    existing = _reports_by_student(db, student_ids, term, school_year)
    results_by_student: dict[UUID, int] = {}
    if student_ids:
        results_by_student = dict(
            db.execute(
                select(CourseResult.student_id, func.count(CourseResult.id))
                .join(Course, CourseResult.course_id == Course.id)
                .where(
                    CourseResult.student_id.in_(student_ids),
                    CourseResult.term == term,
                    Course.school_year == school_year,
                    CourseResult.deleted_at.is_(None),
                    Course.deleted_at.is_(None),
                )
                .group_by(CourseResult.student_id)
            ).all()
        )

    generated_ids: list[UUID] = []
    skipped_existing = 0
    skipped_no_results = 0
    partial_students: list[PartialReportStudent] = []
    for student in students:
        if student.id in existing:
            skipped_existing += 1
            continue
        partial = _partial_report_student(db, student, term, school_year)
        if partial.missing_course_names and not generate_partial:
            partial_students.append(partial)
            continue
        if results_by_student.get(student.id, 0) == 0:
            skipped_no_results += 1
            continue
        try:
            report_card = _create_report_card(db, student.id, term, school_year)
        except ValueError:
            skipped_no_results += 1
            continue
        generated_ids.append(report_card.id)

    if generated_ids:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="reports_batch_generated",
            entity_type="report_batch",
            entity_id=school_class.id,
            old_value=None,
            new_value={
                "class_id": str(school_class.id),
                "school_year": school_year,
                "term": term,
                "generated_count": len(generated_ids),
                "skipped_existing_count": skipped_existing,
                "skipped_no_results_count": skipped_no_results,
                "skipped_partial_count": len(partial_students),
            },
        )

    return {
        "class_id": str(school_class.id),
        "class_name": school_class.name_fr,
        "generated_count": len(generated_ids),
        "skipped_existing_count": skipped_existing,
        "skipped_no_results_count": skipped_no_results,
        "skipped_partial_count": len(partial_students),
        "partial_students": partial_students,
        "failed": False,
        "error": None,
        "report_ids": [str(report_id) for report_id in generated_ids],
    }


def _job_result_totals(class_rows: list[dict]) -> dict:
    return {
        "generated_count": sum(row.get("generated_count", 0) for row in class_rows),
        "skipped_existing_count": sum(row.get("skipped_existing_count", 0) for row in class_rows),
        "skipped_no_results_count": sum(row.get("skipped_no_results_count", 0) for row in class_rows),
        "skipped_partial_count": sum(row.get("skipped_partial_count", 0) for row in class_rows),
        "failed_count": sum(1 for row in class_rows if row.get("failed")),
    }


def _unassigned_student_count(db: Session, school_year: str) -> int:
    return db.scalar(
        select(func.count(Student.id))
        .outerjoin(
            StudentClassAssignment,
            (StudentClassAssignment.student_id == Student.id)
            & (StudentClassAssignment.school_year == school_year),
        )
        .where(
            StudentClassAssignment.id.is_(None),
            Student.academic_status == "active",
            Student.deleted_at.is_(None),
        )
    ) or 0


@router.post("/batch-generate", response_model=ClassReportBatchGenerateResponse)
def batch_generate_reports(
    payload: ClassReportBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassReportBatchGenerateResponse:
    """Generate draft report cards for every student of the class who has
    course results for the term and no report card yet. One transaction —
    a class generates atomically or not at all because Conseil de classe should
    not leave an ambiguous half-generated class after a database failure."""
    school_class = get_class_or_404(db, payload.class_id)
    term = payload.term.value
    result = _generate_reports_for_class(
        db,
        school_class=school_class,
        term=term,
        school_year=payload.school_year,
        generate_partial=payload.generate_partial,
        current_user=current_user,
    )
    db.commit()

    return ClassReportBatchGenerateResponse(
        status="ok",
        generated_count=result["generated_count"],
        skipped_existing_count=result["skipped_existing_count"],
        skipped_no_results_count=result["skipped_no_results_count"],
        skipped_partial_count=result["skipped_partial_count"],
        partial_students=result["partial_students"],
        report_ids=result["report_ids"],
    )


def _to_report_generation_job_response(job: ReportGenerationJob) -> ReportGenerationJobResponse:
    return ReportGenerationJobResponse(
        job_id=job.id,
        school_year=job.school_year,
        term=job.term,
        status=job.status,
        result=job.result_json if job.status != "pending" else None,
        error=job.error,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


def _run_report_generation_job(job_id: UUID, db: Session) -> None:
    """Background task for all-class bulletin generation."""
    job = db.get(ReportGenerationJob, job_id)
    if job is None:
        return
    class_rows: list[dict] = []
    try:
        admin = db.get(User, job.created_by_admin_id) if job.created_by_admin_id else None
        if admin is None:
            raise ValueError("Job admin user not found")
        generate_partial = bool((job.result_json or {}).get("generate_partial", False))
        classes = db.scalars(
            select(Class)
            .where(Class.school_year == job.school_year, Class.deleted_at.is_(None))
            .order_by(Class.sort_order, Class.name_fr)
        ).all()
        for school_class in classes:
            try:
                row = _generate_reports_for_class(
                    db,
                    school_class=school_class,
                    term=job.term,
                    school_year=job.school_year,
                    generate_partial=generate_partial,
                    current_user=admin,
                )
                db.commit()
            except Exception as exc:
                db.rollback()
                row = {
                    "class_id": str(school_class.id),
                    "class_name": school_class.name_fr,
                    "generated_count": 0,
                    "skipped_existing_count": 0,
                    "skipped_no_results_count": 0,
                    "skipped_partial_count": 0,
                    "failed": True,
                    "error": str(exc)[:500] or exc.__class__.__name__,
                    "report_ids": [],
                }
            class_rows.append(row)

        job = db.get(ReportGenerationJob, job_id)
        if job is None:
            return
        job.result_json = {
            "classes": class_rows,
            "totals": _job_result_totals(class_rows),
            "unassigned_student_count": _unassigned_student_count(db, job.school_year),
        }
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(ReportGenerationJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)[:500] or exc.__class__.__name__
            job.result_json = {
                "classes": class_rows,
                "totals": _job_result_totals(class_rows),
                "unassigned_student_count": _unassigned_student_count(db, job.school_year),
            }
            job.completed_at = datetime.now(timezone.utc)
            db.commit()


@router.post("/bulk-generate", response_model=ReportGenerationJobResponse)
def create_report_generation_job(
    payload: ReportBulkGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportGenerationJobResponse:
    term = payload.term.value
    existing_job = db.scalar(
        select(ReportGenerationJob)
        .where(
            ReportGenerationJob.school_year == payload.school_year,
            ReportGenerationJob.term == term,
            ReportGenerationJob.status == "pending",
        )
        .order_by(ReportGenerationJob.created_at.desc())
    )
    if existing_job is not None:
        return _to_report_generation_job_response(existing_job)

    job = ReportGenerationJob(
        school_year=payload.school_year,
        term=term,
        status="pending",
        result_json={"generate_partial": payload.generate_partial},
        created_by_admin_id=current_user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_report_generation_job, job.id, db)
    return _to_report_generation_job_response(job)


@router.get("/bulk-generate/{job_id}", response_model=ReportGenerationJobResponse)
def get_report_generation_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReportGenerationJobResponse:
    job = db.get(ReportGenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report generation job not found")
    return _to_report_generation_job_response(job)


@router.post("/batch-approve", response_model=ClassReportBatchApproveResponse)
def batch_approve_reports(
    payload: ClassReportBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassReportBatchApproveResponse:
    """Approve every DRAFT report card of the class for the term.

    Deliberately drafts-only: an approved/sent report flagged needs-review is
    stale and must be regenerated (which resets it to draft) — batch approval
    never silently re-blesses stale numbers."""
    get_class_or_404(db, payload.class_id)
    term = payload.term.value
    students = _class_students(db, payload.class_id, payload.school_year)
    reports = _reports_by_student(db, [s.id for s in students], term, payload.school_year)

    approved_at = datetime.now(timezone.utc)
    approved_ids = []
    stale_reports: list[StaleReportStudent] = []
    for report_card in reports.values():
        if report_card.status != "draft":
            continue
        staleness = get_report_card_staleness(db, report_card)
        if staleness.is_stale and not payload.approve_stale:
            stale_reports.append(_stale_report_student(report_card, staleness))
            continue
        report_card.status = "approved"
        report_card.approved_by_admin_id = current_user.id
        report_card.approved_at = approved_at
        approved_ids.append(report_card.id)

    if approved_ids:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="reports_batch_approved",
            entity_type="report_batch",
            entity_id=payload.class_id,
            old_value=None,
            new_value={
                "class_id": payload.class_id,
                "school_year": payload.school_year,
                "term": term,
                "approved_count": len(approved_ids),
                "skipped_stale_count": len(stale_reports),
                "approved_at": approved_at,
            },
        )
    db.commit()

    return ClassReportBatchApproveResponse(
        status="ok",
        approved_count=len(approved_ids),
        skipped_count=len(reports) - len(approved_ids),
        skipped_stale_count=len(stale_reports),
        stale_reports=stale_reports,
    )


@router.post("/batch-send", response_model=ClassReportBatchSendResponse)
def batch_send_reports(
    payload: ClassReportBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ClassReportBatchSendResponse:
    """Send every approved/sent report of the class for the term.

    Same policy as the single send: a report is only marked sent when at
    least one notification actually went out. Per-report failures never
    abort the batch — they are counted and reported."""
    get_class_or_404(db, payload.class_id)
    term = payload.term.value
    students = _class_students(db, payload.class_id, payload.school_year)
    reports = _reports_by_student(db, [s.id for s in students], term, payload.school_year)

    sent_count = 0
    failed_count = 0
    no_recipient_count = 0
    stale_reports: list[StaleReportStudent] = []
    outcomes = {}
    sent_at = datetime.now(timezone.utc)
    for report_card in reports.values():
        if report_card.status not in {"approved", "sent"}:
            continue
        staleness = get_report_card_staleness(db, report_card)
        if staleness.is_stale and not payload.send_stale:
            stale_reports.append(_stale_report_student(report_card, staleness))
            outcomes[str(report_card.id)] = "stale"
            continue
        try:
            send_results = send_report_notification_to_parents(db, report_card.id)
        except ValueError:
            # Email/SMS configuration missing — nothing could be attempted.
            failed_count += 1
            outcomes[str(report_card.id)] = "failed"
            continue
        if not send_results:
            no_recipient_count += 1
            outcomes[str(report_card.id)] = "no_recipient"
            continue
        if any(result.get("sent") for result in send_results):
            report_card.status = "sent"
            report_card.sent_at = sent_at
            sent_count += 1
            outcomes[str(report_card.id)] = "sent"
        else:
            failed_count += 1
            outcomes[str(report_card.id)] = "failed"

    if outcomes:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="reports_batch_sent",
            entity_type="report_batch",
            entity_id=payload.class_id,
            old_value=None,
            new_value={
                "class_id": payload.class_id,
                "school_year": payload.school_year,
                "term": term,
                "sent_count": sent_count,
                "failed_count": failed_count,
                "no_recipient_count": no_recipient_count,
                "skipped_stale_count": len(stale_reports),
                "outcomes": outcomes,
            },
        )
    db.commit()

    return ClassReportBatchSendResponse(
        status="ok",
        sent_count=sent_count,
        failed_count=failed_count,
        no_recipient_count=no_recipient_count,
        skipped_stale_count=len(stale_reports),
        stale_reports=stale_reports,
    )


def _class_pdf_reports(db: Session, class_id: UUID, term: str, school_year: str) -> list[ReportCard]:
    """Approved/sent reports for the class print run, ordered like the paper
    class list (student last name, first name)."""
    student_ids = [student.id for student in _class_students(db, class_id, school_year)]
    if not student_ids:
        return []
    return list(
        db.scalars(
            select(ReportCard)
            .join(Student, ReportCard.student_id == Student.id)
            .where(
                ReportCard.student_id.in_(student_ids),
                Student.deleted_at.is_(None),
                ReportCard.term == term,
                ReportCard.school_year == school_year,
                ReportCard.status.in_(sorted(PARENT_VISIBLE_STATUSES)),
                ReportCard.deleted_at.is_(None),
            )
            .order_by(Student.last_name, Student.first_name)
        ).all()
    )


def _run_class_pdf_job(job_id: UUID) -> None:
    """Background task: render + merge every bulletin of the class.

    Runs after the response is sent because WeasyPrint time scales with class
    size and can outlive an HTTP request. It opens its own session because the
    request-scoped one is already closed. Each page is rebuilt from the stored
    approved/sent snapshot, never from current live grades.
    """
    db = SessionLocal()
    try:
        job = db.get(PdfJob, job_id)
        if job is None:
            return
        try:
            report_cards = _class_pdf_reports(db, job.class_id, job.term, job.school_year)
            report_data_list = [
                build_report_card_data_from_report_card(db, report_card) for report_card in report_cards
            ]
            job.pdf_bytes = render_class_bulletins_pdf_bytes(report_data_list)
            job.report_count = len(report_data_list)
            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:500] or exc.__class__.__name__
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


@router.post("/class-pdf", response_model=ClassPdfJobResponse)
def create_class_pdf_job(
    payload: ClassReportBatchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ClassPdfJobResponse:
    """Enqueue a merged-PDF render of every approved/sent bulletin in the
    class. Returns a job id to poll — rendering 40 bulletins outlives the
    request timeout on the free tier, so it runs as a background task."""
    get_class_or_404(db, payload.class_id)
    term = payload.term.value
    if not _class_pdf_reports(db, payload.class_id, term, payload.school_year):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No approved or sent reports for this class and term",
        )

    # Opportunistic cleanup: finished/stale jobs older than an hour are dead
    # weight (their blobs were either downloaded or abandoned).
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    for old_job in db.scalars(select(PdfJob).where(PdfJob.created_at < cutoff)).all():
        db.delete(old_job)

    job = PdfJob(class_id=payload.class_id, school_year=payload.school_year, term=term, status="pending")
    db.add(job)
    db.commit()

    background_tasks.add_task(_run_class_pdf_job, job.id)
    return ClassPdfJobResponse(job_id=job.id, status="pending")


@router.get("/class-pdf/{job_id}")
def get_class_pdf_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    """Poll a class-PDF job. JSON while pending/failed; the PDF once done."""
    job = db.get(PdfJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF job not found")

    if job.status != "done":
        return Response(
            content=ClassPdfJobResponse(
                job_id=job.id, status=job.status, error=job.error, report_count=job.report_count
            ).model_dump_json(),
            media_type="application/json",
        )

    school_class = db.get(Class, job.class_id)
    class_part = _safe_filename_part(school_class.name_fr if school_class else "classe")
    filename = f"{class_part}_{_safe_filename_part(job.term)}_{_safe_filename_part(job.school_year)}_bulletins.pdf"
    return Response(
        content=job.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=list[AdminReportListItem])
def list_reports(
    school_year: str | None = None,
    term: str | None = None,
    class_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AdminReportListItem]:
    report_cards = db.scalars(
        select(ReportCard)
        .join(ReportCard.student)
        .options(
            joinedload(ReportCard.student),
            selectinload(ReportCard.courses).joinedload(ReportCardCourse.course).joinedload(Course.school_class),
        )
        .where(ReportCard.deleted_at.is_(None), Student.deleted_at.is_(None))
    ).all()
    latest_by_key = _latest_course_result_times_by_report_key(db)
    needs_review_by_report_id = {
        report_card.id: _report_needs_review(
            report_card,
            latest_by_key.get(
                _course_result_key(
                    report_card.student_id,
                    report_card.term,
                    report_card.school_year,
                )
            ),
        )
        for report_card in report_cards
    }
    visible_report_cards: list[ReportCard] = []
    for report_card in report_cards:
        needs_review = needs_review_by_report_id[report_card.id]
        report_class_id, _ = _historical_class_for_report_card(db, report_card)
        if class_id is not None and report_class_id != class_id:
            continue
        if needs_review:
            visible_report_cards.append(report_card)
            continue
        if school_year is not None and report_card.school_year != school_year:
            continue
        if term is not None and report_card.term != term:
            continue
        visible_report_cards.append(report_card)
    report_cards = visible_report_cards
    report_cards.sort(
        key=lambda report_card: (
            needs_review_by_report_id[report_card.id],
            _datetime_for_compare(report_card.created_at) or datetime.min,
        ),
        reverse=True,
    )
    return [
        to_admin_report_list_item(
            report_card,
            needs_review=needs_review_by_report_id[report_card.id],
            db=db,
        )
        for report_card in report_cards
    ]


@router.get("/admin/{report_id}", response_model=AdminReportCardResponse)
def get_admin_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AdminReportCardResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    return to_admin_report_card_response(report_card, db)


@router.get("/student/{student_id}", response_model=list[ReportCardResponse])
def list_student_reports(
    student_id: UUID,
    school_year: str | None = None,
    term: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportCardResponse]:
    if current_user.role == "admin":
        query = (
            select(ReportCard)
            .join(ReportCard.student)
            .options(selectinload(ReportCard.courses))
            .where(
                ReportCard.student_id == student_id,
                ReportCard.deleted_at.is_(None),
                Student.deleted_at.is_(None),
            )
            .order_by(ReportCard.created_at.desc())
        )
        if school_year is not None:
            query = query.where(ReportCard.school_year == school_year)
        if term is not None:
            query = query.where(ReportCard.term == term)
        report_cards = db.scalars(query).all()
        return [to_report_card_response(report_card, db) for report_card in report_cards]

    if current_user.role == "parent" and parent_can_access_student(db, current_user, student_id):
        query = (
            select(ReportCard)
            .join(ReportCard.student)
            .options(selectinload(ReportCard.courses))
            .where(
                ReportCard.student_id == student_id,
                ReportCard.status.in_(PARENT_VISIBLE_STATUSES),
                ReportCard.deleted_at.is_(None),
                Student.deleted_at.is_(None),
            )
            .order_by(ReportCard.created_at.desc())
        )
        if school_year is not None:
            query = query.where(ReportCard.school_year == school_year)
        if term is not None:
            query = query.where(ReportCard.term == term)
        report_cards = db.scalars(query).all()
        return [to_report_card_response(report_card, db) for report_card in report_cards]

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.put("/{report_id}/review", response_model=ReportCardResponse)
def review_report_card(
    report_id: UUID,
    payload: ReportReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportCardResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    ensure_report_is_draft(report_card)
    old_summary, new_summary = update_report_summary(report_card, payload)
    log_summary_edit_if_needed(db, current_user.id, report_card, payload, old_summary, new_summary)

    db.commit()
    db.refresh(report_card)
    return to_report_card_response(report_card, db)


@router.put("/{report_id}/summary", response_model=ReportCardResponse)
def update_report_summary_route(
    report_id: UUID,
    payload: ReportReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportCardResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    old_summary, new_summary = update_report_summary(report_card, payload)
    log_summary_edit_if_needed(db, current_user.id, report_card, payload, old_summary, new_summary)

    db.commit()
    db.refresh(report_card)
    return to_report_card_response(report_card, db)


@router.post("/{report_id}/approve", response_model=ReportCardResponse)
def approve_report_card(
    report_id: UUID,
    payload: ReportApproveRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportCardResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    ensure_report_is_draft(report_card)
    _ensure_report_snapshot_fresh_or_allowed(db, report_card, payload.approve_stale if payload else False)

    approved_at = datetime.now(timezone.utc)
    report_card.status = "approved"
    report_card.approved_by_admin_id = current_user.id
    report_card.approved_at = approved_at
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="report_approved",
        entity_type="report_card",
        entity_id=report_card.id,
        old_value={"status": "draft"},
        new_value={
            "status": "approved",
            "approved_by_admin_id": current_user.id,
            "approved_at": approved_at,
        },
    )

    db.commit()
    db.refresh(report_card)
    return to_report_card_response(report_card, db)


@router.post("/{report_id}/send", response_model=ReportSendResponse)
def send_report_card(
    report_id: UUID,
    payload: ReportSendRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportSendResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    ensure_report_can_be_sent(report_card)
    _ensure_report_snapshot_fresh_or_allowed(db, report_card, payload.send_stale if payload else False)
    was_already_sent = report_card.status == "sent"
    old_status = report_card.status
    old_sent_at = report_card.sent_at

    try:
        send_results = send_report_notification_to_parents(db, report_card.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    sent_count = sum(1 for result in send_results if result.get("sent"))
    failed_count = len(send_results) - sent_count
    provider = _email_result_provider(send_results)
    if sent_count == 0:
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="report_email_failed",
            entity_type="report_card",
            entity_id=report_card.id,
            old_value={"status": old_status, "sent_at": old_sent_at},
            new_value={
                "recipient_count": len(send_results),
                "failed_count": failed_count,
                "provider": provider,
                "errors": _email_error_summary(send_results),
                "was_already_sent": was_already_sent,
            },
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "No report notifications were sent", "results": send_results},
        )

    report_card.status = "sent"
    sent_at = datetime.now(timezone.utc)
    report_card.sent_at = sent_at
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="report_resent" if was_already_sent else "report_sent",
        entity_type="report_card",
        entity_id=report_card.id,
        old_value={"status": old_status, "sent_at": old_sent_at},
        new_value={
            "status": "sent",
            "sent_at": sent_at,
            "recipient_count": len(send_results),
            "success_count": sent_count,
            "failed_count": failed_count,
            "provider": provider,
            "provider_message_ids": _email_message_ids(send_results),
            "was_already_sent": was_already_sent,
        },
    )
    db.commit()

    return ReportSendResponse(
        report_card_id=report_card.id,
        status=report_card.status,
        sent_count=sent_count,
        failed_count=failed_count,
        results=send_results,
    )


@router.get("/{report_id}/staleness", response_model=ReportCardStalenessResponse)
def get_report_staleness(
    report_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReportCardStalenessResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    staleness = get_report_card_staleness(db, report_card)
    return ReportCardStalenessResponse(
        is_stale=staleness.is_stale,
        reason=staleness.reason,
        snapshot_overall_average=staleness.snapshot_overall_average,
        current_overall_average=staleness.current_overall_average,
        snapshot_gpa=staleness.snapshot_gpa,
        current_gpa=staleness.current_gpa,
    )


@router.post("/{report_id}/regenerate", response_model=ReportCardResponse)
def regenerate_report_card(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportCardResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    try:
        report_data = build_report_card_data(
            db,
            report_card.student_id,
            report_card.term,
            report_card.school_year,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "Student not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    old_value = {
        "status": report_card.status,
        "overall_average": report_card.overall_average,
        "french_average": report_card.french_average,
        "english_average": report_card.english_average,
        "bilingual_average": report_card.bilingual_average,
        "gpa": report_card.gpa,
        "scale": report_card.scale,
        "approved_by_admin_id": report_card.approved_by_admin_id,
        "approved_at": report_card.approved_at,
        "sent_at": report_card.sent_at,
        "courses": [
            {
                "course_id": course.course_id,
                "course_name": course.course_name,
                "average": course.average,
                "letter_grade": course.letter_grade,
            }
            for course in report_card.courses
        ],
    }

    # Replace only computed course snapshot data. Conduct, work habits, all four
    # comments, and ai_summary are human input and deliberately survive the
    # needs_review -> regenerate -> draft recovery path.
    for course in db.scalars(
        select(ReportCardCourse).where(ReportCardCourse.report_card_id == report_card.id)
    ).all():
        db.delete(course)
    db.flush()

    report_card.overall_average = report_data["overall_average"]
    report_card.french_average = report_data["french_average"]
    report_card.english_average = report_data["english_average"]
    report_card.bilingual_average = report_data["bilingual_average"]
    report_card.gpa = report_data["gpa"]
    # Regenerated snapshots are always on the /20 scale, even when the previous
    # snapshot was a historical /100 report.
    report_card.scale = "20"
    report_card.status = "draft"
    report_card.approved_by_admin_id = None
    report_card.approved_at = None
    report_card.sent_at = None

    for course in report_data["courses"]:
        db.add(
            ReportCardCourse(
                report_card_id=report_card.id,
                course_id=course["course_id"],
                course_name=course["course_name"],
                average=course["average"],
                letter_grade=course["letter_grade"],
                coefficient=course["coefficient"],
                moy_int=course["moy_int"],
                mcc=course["mcc"],
                devoir_score=course["devoir_score"],
                composition_score=course["composition_score"],
            )
        )

    new_value = {
        "status": report_card.status,
        "overall_average": report_card.overall_average,
        "french_average": report_card.french_average,
        "english_average": report_card.english_average,
        "bilingual_average": report_card.bilingual_average,
        "gpa": report_card.gpa,
        "scale": report_card.scale,
        "approved_by_admin_id": None,
        "approved_at": None,
        "sent_at": None,
        "courses": [
            {
                "course_id": course["course_id"],
                "course_name": course["course_name"],
                "average": course["average"],
                "letter_grade": course["letter_grade"],
            }
            for course in report_data["courses"]
        ],
    }
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="report_regenerated",
        entity_type="report_card",
        entity_id=report_card.id,
        old_value=old_value,
        new_value=new_value,
    )

    db.commit()
    db.refresh(report_card)
    db.expire(report_card, ["courses"])
    return to_report_card_response(report_card, db)


@router.patch("/{report_id}", response_model=ReportCardResponse)
def update_report_details(
    report_id: UUID,
    payload: ReportDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportCardResponse:
    """Admin-only edit of A1.7a conduct / work-habit items and comments.

    Does not touch grades, averages, or the course snapshot. Editable on any
    status; approved/sent reports move to needs_review when content changes.
    """
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    old_status = report_card.status
    old_value = _report_details_snapshot(report_card)

    # Comments: nullable Text. An explicit value (including null) sets or clears;
    # an omitted key leaves the field unchanged (A1.5 model_fields_set pattern).
    for field in _REPORT_COMMENT_FIELDS:
        if field in payload.model_fields_set:
            setattr(report_card, field, getattr(payload, field))

    # Item collections: when provided, replace the report's rows for that
    # category. delete-orphan cascade removes rows that are no longer present.
    if "conduct_items" in payload.model_fields_set:
        report_card.conduct_items = _validated_report_item_rows(
            payload.conduct_items or [], CONDUCT_ITEM_KEYS, ReportConductItem
        )
    if "work_habit_items" in payload.model_fields_set:
        report_card.work_habit_items = _validated_report_item_rows(
            payload.work_habit_items or [], WORK_HABIT_ITEM_KEYS, ReportWorkHabitItem
        )

    new_value = _report_details_snapshot(report_card)
    if new_value != old_value:
        changed_categories = _changed_report_detail_categories(old_value, new_value)
        # Withdrawal is intentional: a sent document edited after delivery is
        # no longer the approved parent-facing artifact. Regenerate/re-approve/
        # re-send is the only route that publishes the revised content again.
        if old_status in PARENT_VISIBLE_STATUSES:
            report_card.status = REVIEW_REQUIRED_STATUS
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="report_details_edited",
            entity_type="report_card",
            entity_id=report_card.id,
            old_value={**old_value, "status": old_status},
            new_value={
                **new_value,
                "status": report_card.status,
                "prior_status": old_status,
                "changed_categories": changed_categories,
            },
        )

    db.commit()
    db.refresh(report_card)
    return to_report_card_response(report_card, db)


@router.get("/{report_id}/pdf")
def download_report_pdf(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report_card = get_report_card_or_404(db, report_id)
    ensure_can_view_report(db, current_user, report_card)

    # Regenerate bytes from the stored snapshot, never live CourseResults: an
    # official PDF must remain reproducible after later grade changes. This also
    # avoids deployment-local file state; pdf_url is left untouched.
    report_data = build_report_card_data_from_report_card(db, report_card)
    pdf_bytes = render_report_card_pdf_bytes(report_data)
    filename = _build_pdf_filename(report_data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report_id}", response_model=ReportCardResponse)
def get_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportCardResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_can_view_report(db, current_user, report_card)
    return to_report_card_response(report_card, db)
