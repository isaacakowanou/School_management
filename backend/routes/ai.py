from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import get_current_user, require_admin
from database import get_db
from models import AIWarning, Course, Enrollment, ReportCard, Student, User
from schemas import AISummaryResponse, AIWarningResponse
from services.ai_checker import check_report_card_data
from services.ai_summary import generate_report_summary
from utils import get_current_teacher, get_report_card_or_404


router = APIRouter(tags=["ai"])


def store_report_warnings(db: Session, report_card_id: UUID, warnings: list[dict]) -> list[AIWarningResponse]:
    db.execute(delete(AIWarning).where(AIWarning.report_card_id == report_card_id))
    for warning in warnings:
        db.add(
            AIWarning(
                report_card_id=report_card_id,
                warning_type=warning["warning_type"],
                message=warning["message"],
                severity=warning["severity"],
            )
        )
    db.commit()

    return [AIWarningResponse(**warning) for warning in warnings]


def get_student_or_404(db: Session, student_id: UUID) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def teacher_can_check_student(db: Session, current_user: User, student_id: UUID) -> bool:
    teacher = get_current_teacher(db, current_user)
    if teacher is None:
        return False

    enrollment = db.scalar(
        select(Enrollment)
        .join(Course, Enrollment.course_id == Course.id)
        .where(
            Enrollment.student_id == student_id,
            Course.teacher_id == teacher.id,
        )
    )
    return enrollment is not None


def get_latest_draft_report_card_or_404(db: Session, student_id: UUID) -> ReportCard:
    report_card = db.scalar(
        select(ReportCard)
        .where(
            ReportCard.student_id == student_id,
            ReportCard.status == "draft",
        )
        .order_by(ReportCard.created_at.desc())
    )
    if report_card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student has no draft report card")
    return report_card


def build_summary_report_data(report_card: ReportCard) -> dict:
    student = report_card.student
    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "grade_level": student.grade_level,
        },
        "term": report_card.term,
        "school_year": report_card.school_year,
        "courses": [
            {
                "course_name": course.course_name,
                "average": course.average,
                "letter_grade": course.letter_grade,
            }
            for course in report_card.courses
        ],
        "overall_average": report_card.overall_average,
        "gpa": report_card.gpa,
    }


@router.post("/check-report/{report_card_id}", response_model=list[AIWarningResponse])
def check_report_card(
    report_card_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AIWarningResponse]:
    try:
        warnings = check_report_card_data(db, report_card_id)
    except ValueError as exc:
        if str(exc) == "Report card not found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return store_report_warnings(db, report_card_id, warnings)


@router.post("/check-grades/{student_id}", response_model=list[AIWarningResponse])
def check_student_grades(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AIWarningResponse]:
    student = get_student_or_404(db, student_id)

    if current_user.role == "admin":
        pass
    elif current_user.role == "teacher" and teacher_can_check_student(db, current_user, student.id):
        pass
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    report_card = get_latest_draft_report_card_or_404(db, student.id)
    warnings = check_report_card_data(db, report_card.id)
    return store_report_warnings(db, report_card.id, warnings)


@router.post("/generate-summary/{report_card_id}", response_model=AISummaryResponse)
def generate_summary_for_report(
    report_card_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AISummaryResponse:
    report_card = get_report_card_or_404(db, report_card_id)
    report_data = build_summary_report_data(report_card)

    try:
        ai_summary = generate_report_summary(report_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    report_card.ai_summary = ai_summary
    db.commit()
    db.refresh(report_card)

    return AISummaryResponse(report_card_id=report_card.id, ai_summary=report_card.ai_summary)
