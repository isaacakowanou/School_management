from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user, require_admin
from audit import create_audit_log
from database import get_db
from models import Parent, ReportCard, ReportCardCourse, StudentParent, User
from schemas import (
    ReportCardCourseResponse,
    ReportCardResponse,
    ReportGenerateRequest,
    ReportReviewUpdate,
    ReportSendResponse,
)
from services.email_service import send_report_notification_to_parents
from services.pdf_generator import _build_pdf_filename, generate_report_card_pdf, render_report_card_pdf_bytes
from services.report_builder import build_report_card_data, build_report_card_data_from_report_card
from utils import get_report_card_or_404


router = APIRouter(tags=["reports"])
PARENT_VISIBLE_STATUSES = {"approved", "sent"}


def to_report_card_response(report_card: ReportCard) -> ReportCardResponse:
    return ReportCardResponse(
        id=report_card.id,
        student_id=report_card.student_id,
        term=report_card.term,
        school_year=report_card.school_year,
        overall_average=report_card.overall_average,
        gpa=report_card.gpa,
        status=report_card.status,
        ai_summary=report_card.ai_summary,
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
    )


def parent_can_access_student(db: Session, current_user: User, student_id: UUID) -> bool:
    parent = db.scalar(select(Parent).where(Parent.user_id == current_user.id))
    if parent is None:
        return False

    student_link = db.scalar(
        select(StudentParent).where(
            StudentParent.parent_id == parent.id,
            StudentParent.student_id == student_id,
        )
    )
    return student_link is not None


def parent_can_access_report(db: Session, current_user: User, report_card: ReportCard) -> bool:
    return (
        report_card.status in PARENT_VISIBLE_STATUSES
        and parent_can_access_student(db, current_user, report_card.student_id)
    )


def ensure_can_view_report(db: Session, current_user: User, report_card: ReportCard) -> None:
    if current_user.role == "admin":
        return
    if current_user.role == "parent" and parent_can_access_report(db, current_user, report_card):
        return

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def ensure_report_is_draft(report_card: ReportCard) -> None:
    if report_card.status != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft reports can be reviewed")


def ensure_report_is_approved(report_card: ReportCard) -> None:
    if report_card.status != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved reports can be sent")


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


@router.post("/generate/{student_id}", response_model=ReportCardResponse, status_code=status.HTTP_201_CREATED)
def generate_report_card(
    student_id: UUID,
    payload: ReportGenerateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> ReportCardResponse:
    try:
        report_data = build_report_card_data(db, student_id, payload.term, payload.school_year)
    except ValueError as exc:
        detail = str(exc)
        if detail == "Student not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    report_data["status"] = "draft"
    report_data["generated_date"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report_data["ai_summary"] = None

    try:
        pdf_path = generate_report_card_pdf(report_data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PDF generation failed") from exc

    report_card = ReportCard(
        student_id=student_id,
        term=payload.term,
        school_year=payload.school_year,
        overall_average=report_data["overall_average"],
        gpa=report_data["gpa"],
        status="draft",
        ai_summary=None,
        pdf_url=pdf_path,
    )
    db.add(report_card)
    db.flush()

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


@router.get("", response_model=list[ReportCardResponse])
def list_reports(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ReportCardResponse]:
    report_cards = db.scalars(select(ReportCard).order_by(ReportCard.created_at.desc())).all()
    return [to_report_card_response(report_card) for report_card in report_cards]


@router.get("/student/{student_id}", response_model=list[ReportCardResponse])
def list_student_reports(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReportCardResponse]:
    if current_user.role == "admin":
        report_cards = db.scalars(
            select(ReportCard)
            .where(ReportCard.student_id == student_id)
            .order_by(ReportCard.created_at.desc())
        ).all()
        return [to_report_card_response(report_card) for report_card in report_cards]

    if current_user.role == "parent" and parent_can_access_student(db, current_user, student_id):
        report_cards = db.scalars(
            select(ReportCard)
            .where(
                ReportCard.student_id == student_id,
                ReportCard.status.in_(PARENT_VISIBLE_STATUSES),
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
    ensure_report_is_draft(report_card)
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
    ensure_report_is_approved(report_card)

    try:
        send_results = send_report_notification_to_parents(db, report_card.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    sent_count = sum(1 for result in send_results if result.get("sent"))
    failed_count = len(send_results) - sent_count
    if sent_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "No report notifications were sent", "results": send_results},
        )

    report_card.status = "sent"
    report_card.sent_at = datetime.now(timezone.utc)
    create_audit_log(
        db=db,
        actor_user_id=current_user.id,
        action="report_sent",
        entity_type="report_card",
        entity_id=report_card.id,
        old_value={"status": "approved"},
        new_value={"status": "sent", "sent_count": sent_count, "failed_count": failed_count},
    )
    db.commit()

    return ReportSendResponse(
        report_card_id=report_card.id,
        status=report_card.status,
        sent_count=sent_count,
        failed_count=failed_count,
        results=send_results,
    )


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
