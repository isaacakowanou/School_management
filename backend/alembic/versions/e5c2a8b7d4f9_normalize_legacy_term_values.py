"""normalize legacy term values to canonical trimesters

Revision ID: e5c2a8b7d4f9
Revises: d7a4c9e2f6b1
Create Date: 2026-07-02 12:00:00.000000

A1.7c — data-only migration. Term used to be free text, which fragmented data
("Fall" vs "Trimester 1" vs "1er Trimestre") and broke the report builder's
exact-match course lookup plus the bulletin's averages grid. This rewrites
every recognized legacy variant onto its canonical trimester across ALL four
term-bearing tables (courses, grade_items, course_results, report_cards —
staleness matching compares across them, so partial normalization would break
it). Unrecognized values are deliberately left untouched and reported in the
migration output; extend constants._TERM_VARIANTS and re-run if prod surfaces
more variants.

course_results is unique on (student_id, course_id, term), and real data holds
duplicate results for the same student+course under two legacy spellings of
the same trimester ("Fall" and "Trimester 1"). Rows whose canonical twin
already exists are skipped and reported instead of violating the constraint —
deciding which duplicate wins is manual cleanup, not migration guesswork.

Downgrade is a no-op: the original free-text spellings are not recoverable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from constants import normalize_term

# revision identifiers, used by Alembic.
revision: str = "e5c2a8b7d4f9"
down_revision: Union[str, Sequence[str], None] = "d7a4c9e2f6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TERM_TABLES = ("courses", "grade_items", "course_results", "report_cards")


# Collision-safe UPDATE for course_results: only rows whose canonical twin
# does not already exist for the same student+course are rewritten.
_COURSE_RESULTS_UPDATE = """
    UPDATE course_results SET term = :canonical
     WHERE term = :term
       AND NOT EXISTS (
           SELECT 1 FROM course_results twin
            WHERE twin.student_id = course_results.student_id
              AND twin.course_id = course_results.course_id
              AND twin.term = :canonical
       )
"""


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    for table in _TERM_TABLES:
        terms = connection.execute(sa.text(f"SELECT DISTINCT term FROM {table}")).scalars().all()
        for term in terms:
            if term is None:
                continue
            canonical = normalize_term(term)
            if canonical is None:
                print(f"[term-normalization] {table}: unrecognized term left as-is: {term!r}")
                continue
            if canonical == term:
                continue
            if table == "course_results":
                result = connection.execute(
                    sa.text(_COURSE_RESULTS_UPDATE), {"canonical": canonical, "term": term}
                )
                leftovers = connection.execute(
                    sa.text("SELECT COUNT(*) FROM course_results WHERE term = :term"),
                    {"term": term},
                ).scalar()
                note = ""
                if leftovers:
                    note = (
                        f"; {leftovers} row(s) skipped — a {canonical!r} result already exists"
                        " for the same student+course, resolve the duplicate manually"
                    )
                print(f"[term-normalization] {table}: {term!r} -> {canonical!r} ({result.rowcount} rows{note})")
            else:
                result = connection.execute(
                    sa.text(f"UPDATE {table} SET term = :canonical WHERE term = :term"),  # noqa: S608 — table names from a fixed tuple
                    {"canonical": canonical, "term": term},
                )
                print(f"[term-normalization] {table}: {term!r} -> {canonical!r} ({result.rowcount} rows)")


def downgrade() -> None:
    """Downgrade schema — intentionally a no-op (original spellings unrecoverable)."""
