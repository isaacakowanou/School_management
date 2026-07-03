"""add student deleted_at

Revision ID: f9a1c2d3e4b5
Revises: e5c2a8b7d4f9
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f9a1c2d3e4b5"
down_revision: Union[str, Sequence[str], None] = "e5c2a8b7d4f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("students", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_students_deleted_at", "students", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_students_deleted_at", table_name="students")
    op.drop_column("students", "deleted_at")
