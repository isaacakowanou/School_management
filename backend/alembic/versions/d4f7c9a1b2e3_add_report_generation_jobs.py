"""add report generation jobs

Revision ID: d4f7c9a1b2e3
Revises: b8e1c4d6a9f2
Create Date: 2026-07-24
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4f7c9a1b2e3"
down_revision: Union[str, Sequence[str], None] = "b8e1c4d6a9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("school_year", sa.String(length=20), nullable=False),
        sa.Column("term", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_generation_jobs_year_term_status",
        "report_generation_jobs",
        ["school_year", "term", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_generation_jobs_year_term_status", table_name="report_generation_jobs")
    op.drop_table("report_generation_jobs")
