"""add report_card scale column

Revision ID: b7e4a1c2d3f4
Revises: 43b4cc97eee6
Create Date: 2026-06-28 00:00:00.000000

A1.2: course averages and report overall_average switch from /100 to /20.
Existing report snapshots stay as historical /100 records, so they are tagged
scale="100". New reports default to scale="20" (model + server_default).

Added nullable-first for SQLite/Postgres safety: the column is added with a
server_default of "20", every pre-existing row is then backfilled to "100",
and the ORM supplies "20" on all future inserts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7e4a1c2d3f4"
down_revision: Union[str, Sequence[str], None] = "43b4cc97eee6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "report_cards",
        sa.Column("scale", sa.String(length=10), server_default="20", nullable=True),
    )
    # All report snapshots that existed before this migration are on the /100
    # scale. Tag them so they remain truthful historical records.
    op.execute("UPDATE report_cards SET scale = '100'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("report_cards", "scale")
