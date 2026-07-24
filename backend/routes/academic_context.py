"""Expose the shared academic year/trimester defaults for frontend filters."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from constants import TRIMESTER_TERMS
from database import get_db
from schemas import AcademicContextResponse
from services.academic_context import available_school_years, current_school_year, current_term_for_year


router = APIRouter(tags=["academic-context"])


@router.get("/academic-context", response_model=AcademicContextResponse)
def get_academic_context(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> AcademicContextResponse:
    school_year = current_school_year(db)
    return AcademicContextResponse(
        current_school_year=school_year,
        current_term=current_term_for_year(db, school_year) if school_year is not None else TRIMESTER_TERMS[0],
        available_school_years=available_school_years(db),
        terms=TRIMESTER_TERMS,
    )
