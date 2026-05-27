from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import ReportCard, ReportCardCourse, User
from schemas import ReportCardCourseResponse, ReportCardResponse, ReportGenerateRequest
from services.pdf_generator import generate_report_card_pdf
from services.report_builder import build_report_card_data


router = APIRouter(tags=["reports"])


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
