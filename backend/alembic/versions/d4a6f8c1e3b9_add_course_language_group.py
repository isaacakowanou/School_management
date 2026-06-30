"""add course language_group

Revision ID: d4a6f8c1e3b9
Revises: e7f2d9c1b8a3
Create Date: 2026-06-30 00:00:00.000000

A1.5 prep for A1.6 (three averages: moyenne francaise, moyenne anglaise,
moyenne bilingue). BISC offers every subject in both French and English as
separate Course rows; language_group tags which track a course belongs to.

Nullable, no server default. Existing courses stay null until an admin tags
them manually from the UI — no bulk backfill in this migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4a6f8c1e3b9"
down_revision: Union[str, Sequence[str], None] = "e7f2d9c1b8a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "courses",
        sa.Column("language_group", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("courses", "language_group")
