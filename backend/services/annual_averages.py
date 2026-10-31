"""Read annual language-track averages for bulletin display and passage triage.

Use the latest non-deleted approved/sent snapshot for each canonical trimester,
ignoring null track values and reporting which terms are missing.
Stored draft and needs_review statuses are excluded, but this service does not
recompute derived staleness for approved/sent rows.
It never changes grades, reports, or passage decisions.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from constants import FINAL_TRIMESTER_NUMBER, TRIMESTER_TERMS, term_number
from models import ReportCard


# Filter by stored publication status; derived staleness is not evaluated here.
# A persisted needs_review state withdraws the report and excludes it from this
# annual calculation, while approved/sent snapshots remain eligible.
ANNUAL_REPORT_STATUSES = {"approved", "sent"}


@dataclass(frozen=True)
class AnnualAverages:
    french: float | None
    english: float | None
    bilingual: float | None
    complete_terms: list[str]
    missing_terms: list[str]

    @property
    def incomplete(self) -> bool:
        """Return True if any canonical term is missing or every track has no value."""
        return bool(self.missing_terms) or (self.french is None and self.english is None and self.bilingual is None)


def _mean(values: list[float | None]) -> float | None:
    real_values = [float(value) for value in values if value is not None]
    if not real_values:
        return None
    return round(sum(real_values) / len(real_values), 2)


def compute_student_annual_averages(db: Session, student_id: UUID, school_year: str) -> AnnualAverages:
    """Return annual track means and term-completeness information for a student/year.

    Use the newest non-deleted approved/sent report for each canonical trimester,
    ignoring null track values when averaging. Stored draft/needs_review states
    are excluded; derived staleness is not checked here. This performs reads only.
    """
    reports = db.scalars(
        select(ReportCard).where(
            ReportCard.student_id == student_id,
            ReportCard.school_year == school_year,
            ReportCard.status.in_(ANNUAL_REPORT_STATUSES),
            ReportCard.deleted_at.is_(None),
        )
    ).all()

    by_term_number: dict[int, ReportCard] = {}
    for report in reports:
        number = term_number(report.term)
        if number is None:
            continue
        current = by_term_number.get(number)
        if current is None or report.created_at > current.created_at:
            by_term_number[number] = report

    expected_terms = list(range(1, FINAL_TRIMESTER_NUMBER + 1))
    complete_terms = [TRIMESTER_TERMS[number - 1] for number in expected_terms if number in by_term_number]
    missing_terms = [TRIMESTER_TERMS[number - 1] for number in expected_terms if number not in by_term_number]

    return AnnualAverages(
        french=_mean([by_term_number[number].french_average for number in expected_terms if number in by_term_number]),
        english=_mean([by_term_number[number].english_average for number in expected_terms if number in by_term_number]),
        bilingual=_mean([by_term_number[number].bilingual_average for number in expected_terms if number in by_term_number]),
        complete_terms=complete_terms,
        missing_terms=missing_terms,
    )
