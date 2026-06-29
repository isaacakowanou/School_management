"""add course_result scale column

Revision ID: c8f5b2a9d6e1
Revises: b7e4a1c2d3f4
Create Date: 2026-06-28 00:00:00.000000

A1.2 follow-up: course results carry the scale their average is on, mirroring
ReportCard.scale. Existing rows are historical /100 results, so they are tagged
scale="100"; new results default to scale="20". The report builder reads this
field and normalizes /100 averages to /20 before averaging.

Added nullable-first for SQLite/Postgres safety: the column is added with a
server_default of "20", every pre-existing row is backfilled to "100", and the
ORM supplies "20" on all future inserts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8f5b2a9d6e1"
down_revision: Union[str, Sequence[str], None] = "b7e4a1c2d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "course_results",
        sa.Column("scale", sa.String(length=10), server_default="20", nullable=True),
    )
    # All course results that existed before this migration are on the /100 scale.
    op.execute("UPDATE course_results SET scale = '100'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("course_results", "scale")
