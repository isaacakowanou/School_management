"""convert existing /100 grade items and grades to /20

Revision ID: e7f2d9c1b8a3
Revises: c8f5b2a9d6e1
Create Date: 2026-06-29 00:00:00.000000

A1.2.1: Migrate all grade items and their associated grades from the legacy /100
scale to /20.

The A1.2 calculator (Option B) normalises scores at query time via
score / max_score, so any max_score is handled correctly. However, leaving old
grade items at max_score=100 while new ones default to max_score=20 creates a
UX trap: teachers see mixed "FINAL / 100" and "FINAL / 20" fields, and entering
"18" into a /100 field silently produces 18 / 100 = F instead of 18 / 20 = B.

Fix: convert every GradeItem row where max_score == 100 to max_score = 20, and
scale its associated Grade.score values by × 0.2 to preserve the underlying
ratio — averages, letter grades, GPA, and existing report snapshots are
unchanged.

Ordering: Grade rows are updated BEFORE GradeItem rows so the subquery filter
(grade_items WHERE max_score = 100) still selects the correct rows at the time
the grade update runs.

Idempotency: the WHERE max_score = 100 filter makes a second run a no-op.
CourseResult.average and ReportCard snapshot values are NOT touched — those are
point-in-time records that must not be altered retroactively.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e7f2d9c1b8a3"
down_revision: Union[str, Sequence[str], None] = "c8f5b2a9d6e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert /100 grade items and associated scores to /20.

    Step 1 — grades.score: multiply by 0.2 for every grade whose parent
    GradeItem had max_score = 100.  Runs BEFORE step 2 so the subquery still
    matches the pre-migration rows.

    Step 2 — grade_items.max_score: set to 20 where max_score = 100.

    Only rows with max_score exactly equal to 100 are touched. Items with other
    max_scores (e.g. 50, 25, 10) pass through unchanged — the Option B
    calculator handles arbitrary max_scores correctly via score / max_score.
    """
    # Step 1: scale Grade.score down by × 0.2 for all /100 grade items.
    # CAST to NUMERIC before ROUND for PostgreSQL compatibility (ROUND on
    # double precision requires a numeric type in PG; SQLite accepts NUMERIC
    # affinity transparently).
    # score IS NOT NULL guard: the model declares score NOT NULL, but a raw
    # INSERT could bypass the constraint and leave a null; guard against that.
    op.execute(
        sa.text(
            """
            UPDATE grades
               SET score = ROUND(CAST(score * 0.2 AS NUMERIC), 2)
             WHERE score IS NOT NULL
               AND grade_item_id IN (
                       SELECT id FROM grade_items WHERE max_score = 100
                   )
            """
        )
    )

    # Step 2: convert GradeItem.max_score from 100 to 20.
    op.execute(
        sa.text("UPDATE grade_items SET max_score = 20 WHERE max_score = 100")
    )


def downgrade() -> None:
    """Reverse the /100 → /20 conversion.

    LIMITATION: this downgrade cannot distinguish between grade items that were
    originally /100 (migrated by upgrade) and grade items created after A1.2
    with the new default of max_score = 20.  Both sets will have max_score
    restored to 100 and their scores multiplied by 5.  Downgrade is a
    safety-net operation, not a routine one — this approximation is acceptable.
    """
    # Step 1: scale Grade.score back up × 5 for all current /20 grade items.
    op.execute(
        sa.text(
            """
            UPDATE grades
               SET score = ROUND(CAST(score * 5 AS NUMERIC), 2)
             WHERE score IS NOT NULL
               AND grade_item_id IN (
                       SELECT id FROM grade_items WHERE max_score = 20
                   )
            """
        )
    )

    # Step 2: restore GradeItem.max_score from 20 to 100.
    op.execute(
        sa.text("UPDATE grade_items SET max_score = 100 WHERE max_score = 20")
    )
