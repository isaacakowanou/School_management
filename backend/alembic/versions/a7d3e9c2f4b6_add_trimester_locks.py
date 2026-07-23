"""add school-wide trimester locks

Revision ID: a7d3e9c2f4b6
Revises: f2c8d4a7b1e9
Create Date: 2026-07-23
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7d3e9c2f4b6"
down_revision: Union[str, Sequence[str], None] = "f2c8d4a7b1e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trimester_locks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_year", sa.String(length=20), nullable=False),
        sa.Column("term", sa.String(length=50), nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by_admin_id"],
            ["users.id"],
            name="fk_trimester_locks_updated_by_admin_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trimester_locks"),
        sa.UniqueConstraint("school_year", "term", name="uq_trimester_lock_school_year_term"),
    )


def downgrade() -> None:
    op.drop_table("trimester_locks")
