"""Admin archive lists for past academic years and graduated students.

Archives are navigation filters, not read-only copies. Rows link back into the
same detail and lifecycle endpoints so recall/regenerate/reapprove/resend keep
working on historical bulletins.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from auth import require_admin
from database import get_db
from models import Course, ReportCard, ReportCardCourse, Student, User
from schemas import AdminReportListItem, CourseResponse, StudentResponse
from services.academic_context import current_school_year
from routes.courses import course_list_stats
from routes.reports import _course_result_key, _latest_course_result_times_by_report_key, _report_needs_review, to_admin_report_list_item
from utils import to_course_response, to_student_response


router = APIRouter(tags=["archives"])


@router.get("/archives/reports", response_model=list[AdminReportListItem])
def list_archived_reports(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AdminReportListItem]:
    current_year = current_school_year(db)
    if current_year is None:
        return []
    reports = db.scalars(
        select(ReportCard)
        .join(ReportCard.student)
        .options(
            joinedload(ReportCard.student),
            selectinload(ReportCard.courses).joinedload(ReportCardCourse.course).joinedload(Course.school_class),
        )
        .where(
            ReportCard.school_year < current_year,
            ReportCard.deleted_at.is_(None),
            Student.deleted_at.is_(None),
        )
        .order_by(ReportCard.school_year.desc(), ReportCard.created_at.desc())
    ).all()
    latest_by_key = _latest_course_result_times_by_report_key(db)
    return [
        to_admin_report_list_item(
            report,
            needs_review=_report_needs_review(
                report,
                latest_by_key.get(_course_result_key(report.student_id, report.term, report.school_year)),
            ),
            db=db,
        )
        for report in reports
    ]


@router.get("/archives/courses", response_model=list[CourseResponse])
def list_archived_courses(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[CourseResponse]:
    current_year = current_school_year(db)
    if current_year is None:
        return []
    courses = db.scalars(
        select(Course)
        .options(joinedload(Course.school_class))
        .where(Course.school_year < current_year, Course.deleted_at.is_(None))
        .order_by(Course.school_year.desc(), Course.name, Course.code)
    ).all()
    stats = course_list_stats(db, courses)
    return [to_course_response(course, stats.get(course.id)) for course in courses]


@router.get("/archives/students", response_model=list[StudentResponse])
def list_graduated_students_archive(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[StudentResponse]:
    students = db.scalars(
        select(Student)
        .options(joinedload(Student.school_class))
        .where(
            Student.academic_status == "graduated",
            Student.deleted_at.is_(None),
        )
        .order_by(Student.last_name, Student.first_name)
    ).all()
    return [to_student_response(student) for student in students]
