"""Expose advisory checks and generated summaries without changing official marks.

Teacher checks are limited to their owned active courses and never replace
stored full-report warnings; admin checks replace the complete warning list.
Student-based summary generation selects the latest draft, while the report-ID
route has no draft-status guard of its own.
Summaries remain screen-only assistance and do not change report status or PDFs.
"""

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
    """Replace all stored warnings for a report, commit, and return warning responses.

    This is the admin full-report storage path; a teacher's scoped check must not
    call it or it would erase warnings about other courses.
    """
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
    """Return a non-deleted student by ID or raise 404."""
    student = db.get(Student, student_id)
    if student is None or student.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def teacher_can_check_student(db: Session, current_user: User, student_id: UUID) -> bool:
    """Return whether this teacher owns an active course with this student's active enrollment."""
    teacher = get_current_teacher(db, current_user)
    if teacher is None:
        return False

    enrollment = db.scalar(
        select(Enrollment)
        .join(Course, Enrollment.course_id == Course.id)
        .join(Student, Enrollment.student_id == Student.id)
        .where(
            Enrollment.student_id == student_id,
            Course.teacher_id == teacher.id,
            Enrollment.deleted_at.is_(None),
            Course.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
    )
    return enrollment is not None


def get_latest_draft_report_card_or_404(db: Session, student_id: UUID) -> ReportCard:
    """Return the student's newest non-deleted draft report or raise 404.

    Selection is by creation time across years and terms, not the global current year.
    """
    report_card = db.scalar(
        select(ReportCard)
        .where(
            ReportCard.student_id == student_id,
            ReportCard.status == "draft",
            ReportCard.deleted_at.is_(None),
        )
        .order_by(ReportCard.created_at.desc())
    )
    if report_card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student has no draft report card")
    return report_card


def build_summary_report_data(report_card: ReportCard) -> dict:
    """Return the student and stored course/average data supplied to the summary service."""
    student = report_card.student
    return {
        "student": {
            "id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "class_name": student.school_class.name_fr if student.school_class else None,
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
        "scale": report_card.scale,
    }


def generate_and_store_report_summary(db: Session, report_card: ReportCard) -> AISummaryResponse:
    """Generate summary text from report data, save it, commit, and return its response.

    Translate service ValueError into 400. Do not modify official marks, status,
    PDFs, or course snapshots; this helper does not itself require draft status.
    """
    report_data = build_summary_report_data(report_card)

    try:
        ai_summary = generate_report_summary(report_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    report_card.ai_summary = ai_summary
    db.commit()
    db.refresh(report_card)

    return AISummaryResponse(report_card_id=report_card.id, ai_summary=report_card.ai_summary)


@router.post("/check-report/{report_card_id}", response_model=list[AIWarningResponse])
def check_report_card(
    report_card_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AIWarningResponse]:
    """Run an admin's full deterministic report check and replace stored warnings.

    Return the warning list, with missing/invalid report data mapped to HTTP errors.
    """
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
    """Check the student's latest draft, restricted to the caller's course scope.

    Admins replace the report's full warning list. Teachers need enrollment in an
    owned course and receive only owned-course warnings without changing stored
    warnings. Parents are denied.
    """
    student = get_student_or_404(db, student_id)

    if current_user.role == "admin":
        pass
    elif current_user.role == "teacher" and teacher_can_check_student(db, current_user, student.id):
        pass
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    report_card = get_latest_draft_report_card_or_404(db, student.id)
    if current_user.role == "teacher":
        teacher = get_current_teacher(db, current_user)
        course_ids = set(db.scalars(
            select(Course.id).where(
                Course.teacher_id == teacher.id,
                Course.deleted_at.is_(None),
            )
        ).all())
        warnings = check_report_card_data(db, report_card.id, course_ids=course_ids)
        return [AIWarningResponse(**warning) for warning in warnings]
    warnings = check_report_card_data(db, report_card.id)
    return store_report_warnings(db, report_card.id, warnings)


@router.post("/generate-summary/{report_card_id}", response_model=AISummaryResponse)
def generate_summary_for_report(
    report_card_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AISummaryResponse:
    """Generate and save an admin-requested summary for the specified existing report.

    This ID-based route does not itself enforce draft status; it leaves report
    status and official results unchanged.
    """
    report_card = get_report_card_or_404(db, report_card_id)
    return generate_and_store_report_summary(db, report_card)


@router.post("/summary/{student_id}", response_model=AISummaryResponse)
def generate_summary_for_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AISummaryResponse:
    """Generate and save a summary for the student's latest draft report, admin-only.

    Missing students or absent drafts return 404; reuse the report-based service.
    """
    student = get_student_or_404(db, student_id)
    report_card = get_latest_draft_report_card_or_404(db, student.id)
    return generate_and_store_report_summary(db, report_card)
