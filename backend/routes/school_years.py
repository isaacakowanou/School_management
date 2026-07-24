"""Admin school-year rollover flow.

This is the single entry point for creating a new academic year: it creates
the canonical GGFK class set and can clone reusable course setup from a prior
year. It does not copy students, enrollments, grades, results, or bulletins.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models import User
from schemas import SchoolYearCreateRequest, SchoolYearCreateResponse
from services.school_year_rollover import (
    audit_rollover,
    clean_school_year,
    clone_course_setup_for_year,
    create_ggfk_classes_for_year,
    latest_course_school_year_before,
)


router = APIRouter(tags=["school-years"])


@router.post("/school-years", response_model=SchoolYearCreateResponse, status_code=201)
def create_school_year(
    payload: SchoolYearCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SchoolYearCreateResponse:
    school_year = clean_school_year(payload.school_year)
    created_classes, skipped_classes = create_ggfk_classes_for_year(db, school_year)

    source_year = clean_school_year(payload.source_school_year, "source_school_year") if payload.source_school_year else None
    cloned_course_count = 0
    unmatched_class_names: list[str] = []
    if payload.clone_courses:
        source_year = source_year or latest_course_school_year_before(db, school_year)
        if source_year is None:
            raise HTTPException(status_code=422, detail="No previous school year with courses was found")
        cloned_course_count, unmatched_class_names = clone_course_setup_for_year(db, source_year, school_year)

    db.flush()
    audit_rollover(
        db,
        current_user=current_user,
        school_year=school_year,
        created_classes=created_classes,
        skipped_classes=skipped_classes,
        source_school_year=source_year,
        cloned_course_count=cloned_course_count,
        unmatched_class_names=unmatched_class_names,
    )
    db.commit()

    return SchoolYearCreateResponse(
        status="ok",
        school_year=school_year,
        created_classes=created_classes,
        skipped_classes=skipped_classes,
        cloned_course_count=cloned_course_count,
        unmatched_class_names=unmatched_class_names,
        source_school_year=source_year,
    )
