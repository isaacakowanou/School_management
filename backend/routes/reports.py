from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from auth import get_current_user, require_admin
from audit import create_audit_log
from constants import CONDUCT_ITEMS, CONDUCT_ITEM_KEYS, WORK_HABIT_ITEMS, WORK_HABIT_ITEM_KEYS
from database import get_db
from models import (
    Course,
    CourseResult,
    Parent,
    ReportCard,
    ReportCardCourse,
    ReportConductItem,
    ReportWorkHabitItem,
    Student,
    StudentParent,
    User,
)
from schemas import (
    AdminReportListItem,
    AdminReportCardResponse,
    ReportCardCourseResponse,
    ReportCardResponse,
    ReportCardStalenessResponse,
    ReportDetailsUpdate,
    ReportGenerateRequest,
    ReportItemResponse,
    ReportReviewUpdate,
    ReportSendResponse,
)
from services.email_service import send_report_notification_to_parents
from services.pdf_renderer import _build_pdf_filename, render_report_card_pdf_bytes
from services.report_builder import (
    build_report_card_data,
    build_report_card_data_from_report_card,
    get_report_card_staleness,
)
from utils import get_report_card_or_404


router = APIRouter(tags=["reports"])
PARENT_VISIBLE_STATUSES = {"approved", "sent"}

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


def to_report_card_response(report_card: ReportCard) -> ReportCardResponse:
    return ReportCardResponse(
        id=report_card.id,
        student_id=report_card.student_id,
        term=report_card.term,
        school_year=report_card.school_year,
        overall_average=report_card.overall_average,
        french_average=report_card.french_average,
        english_average=report_card.english_average,
        bilingual_average=report_card.bilingual_average,
        gpa=report_card.gpa,
        scale=report_card.scale,
        status=report_card.status,
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
            )
            for course in report_card.courses
        ],
        conduct_items=_build_report_items(report_card.conduct_items, CONDUCT_ITEMS),
        work_habit_items=_build_report_items(report_card.work_habit_items, WORK_HABIT_ITEMS),
    )


def to_admin_report_card_response(report_card: ReportCard) -> AdminReportCardResponse:
    student = report_card.student
    return AdminReportCardResponse(
        **to_report_card_response(report_card).model_dump(),
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
        .group_by(CourseResult.student_id, CourseResult.term, Course.school_year)
    ).all()
    return {
        _course_result_key(student_id, term, school_year): latest_calculated_at
        for student_id, term, school_year, latest_calculated_at in rows
    }


def to_admin_report_list_item(report_card: ReportCard, *, needs_review: bool) -> AdminReportListItem:
    student = report_card.student
    return AdminReportListItem(
        id=report_card.id,
        student_id=report_card.student_id,
        student_name=f"{student.first_name} {student.last_name}",
        student_number=student.student_number,
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
    if parent is None:
        return False

    student_link = db.scalar(
        select(StudentParent)
        .join(Student, StudentParent.student_id == Student.id)
        .where(
            StudentParent.parent_id == parent.id,
            StudentParent.student_id == student_id,
            Student.deleted_at.is_(None),
        )
    )
    return student_link is not None


def parent_can_access_report(db: Session, current_user: User, report_card: ReportCard) -> bool:
    return (
        report_card.status in PARENT_VISIBLE_STATUSES
        and report_card.student.deleted_at is None
        and parent_can_access_student(db, current_user, report_card.student_id)
    )


def ensure_can_view_report(db: Session, current_user: User, report_card: ReportCard) -> None:
    if current_user.role == "admin":
        if report_card.student.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")
        return
    if current_user.role == "parent" and parent_can_access_report(db, current_user, report_card):
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def ensure_report_student_active(report_card: ReportCard) -> None:
    if report_card.student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")


def ensure_report_is_draft(report_card: ReportCard) -> None:
    if report_card.status != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft reports can be reviewed")


def ensure_report_can_be_sent(report_card: ReportCard) -> None:
    if report_card.status not in {"approved", "sent"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved or sent reports can be sent")


def update_report_summary(report_card: ReportCard, payload: ReportReviewUpdate) -> tuple[str | None, str | None]:
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


@router.post("/generate/{student_id}", response_model=ReportCardResponse, status_code=status.HTTP_201_CREATED)
def generate_report_card(
    student_id: UUID,
    payload: ReportGenerateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReportCardResponse:
    try:
        report_data = build_report_card_data(db, student_id, payload.term.value, payload.school_year)
    except ValueError as exc:
        detail = str(exc)
        if detail == "Student not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    report_data["status"] = "draft"
    report_data["generated_date"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report_data["ai_summary"] = None

    report_card = ReportCard(
        student_id=student_id,
        term=payload.term.value,
        school_year=payload.school_year,
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
            )
        )

    db.commit()
    db.refresh(report_card)
    return to_report_card_response(report_card)


@router.get("", response_model=list[AdminReportListItem])
def list_reports(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AdminReportListItem]:
    report_cards = db.scalars(
        select(ReportCard)
        .join(ReportCard.student)
        .options(joinedload(ReportCard.student))
        .where(Student.deleted_at.is_(None))
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
    return to_admin_report_card_response(report_card)


@router.get("/student/{student_id}", response_model=list[ReportCardResponse])
def list_student_reports(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportCardResponse]:
    if current_user.role == "admin":
        report_cards = db.scalars(
            select(ReportCard)
            .join(ReportCard.student)
            .options(selectinload(ReportCard.courses))
            .where(
                ReportCard.student_id == student_id,
                Student.deleted_at.is_(None),
            )
            .order_by(ReportCard.created_at.desc())
        ).all()
        return [to_report_card_response(report_card) for report_card in report_cards]

    if current_user.role == "parent" and parent_can_access_student(db, current_user, student_id):
        report_cards = db.scalars(
            select(ReportCard)
            .join(ReportCard.student)
            .options(selectinload(ReportCard.courses))
            .where(
                ReportCard.student_id == student_id,
                ReportCard.status.in_(PARENT_VISIBLE_STATUSES),
                Student.deleted_at.is_(None),
            )
            .order_by(ReportCard.created_at.desc())
        ).all()
        return [to_report_card_response(report_card) for report_card in report_cards]

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
    return to_report_card_response(report_card)


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
    return to_report_card_response(report_card)


@router.post("/{report_id}/approve", response_model=ReportCardResponse)
def approve_report_card(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportCardResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    ensure_report_is_draft(report_card)

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
    return to_report_card_response(report_card)


@router.post("/{report_id}/send", response_model=ReportSendResponse)
def send_report_card(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportSendResponse:
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
    ensure_report_can_be_sent(report_card)
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
    return to_report_card_response(report_card)


@router.patch("/{report_id}", response_model=ReportCardResponse)
def update_report_details(
    report_id: UUID,
    payload: ReportDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReportCardResponse:
    """Admin-only edit of A1.7a conduct / work-habit items and comments.

    Does not touch grades, averages, status, or the course snapshot. Editable
    on any status (draft/approved/sent).
    """
    report_card = get_report_card_or_404(db, report_id)
    ensure_report_student_active(report_card)
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
        create_audit_log(
            db=db,
            actor_user_id=current_user.id,
            action="report_details_edited",
            entity_type="report_card",
            entity_id=report_card.id,
            old_value=old_value,
            new_value=new_value,
        )

    db.commit()
    db.refresh(report_card)
    return to_report_card_response(report_card)


@router.get("/{report_id}/pdf")
def download_report_pdf(
    report_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    report_card = get_report_card_or_404(db, report_id)
    ensure_can_view_report(db, current_user, report_card)

    # Regenerate the PDF in memory from the stored snapshot so download does not
    # depend on a local file existing (deployment-safe). pdf_url is left untouched.
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
    return to_report_card_response(report_card)
