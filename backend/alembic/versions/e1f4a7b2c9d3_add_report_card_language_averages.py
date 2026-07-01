"""add report_card french/english/bilingual averages

Revision ID: e1f4a7b2c9d3
Revises: d4a6f8c1e3b9
Create Date: 2026-06-30 00:00:00.000000

A1.6 three averages (moyenne francaise, moyenne anglaise, moyenne bilingue).
Computed at snapshot time from CourseResults grouped by course.language_group.

All three are nullable, no server default. Existing rows stay null — historical
reports keep their legacy overall_average and render via the frontend fallback.
overall_average is intentionally left intact and still populated on new reports
(the legacy all-courses mean) for backwards compat and the staleness check.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1f4a7b2c9d3"
down_revision: Union[str, Sequence[str], None] = "d4a6f8c1e3b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("report_cards", sa.Column("french_average", sa.Float(), nullable=True))
    op.add_column("report_cards", sa.Column("english_average", sa.Float(), nullable=True))
    op.add_column("report_cards", sa.Column("bilingual_average", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("report_cards", "bilingual_average")
    op.drop_column("report_cards", "english_average")
    op.drop_column("report_cards", "french_average")
