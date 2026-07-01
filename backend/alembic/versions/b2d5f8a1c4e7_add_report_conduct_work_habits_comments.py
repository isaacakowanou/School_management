"""add report conduct/work-habit items and comment columns

Revision ID: b2d5f8a1c4e7
Revises: e1f4a7b2c9d3
Create Date: 2026-07-01 00:00:00.000000

A1.7a — conduct + work-habit assessments and bilingual teacher/principal
comments on report cards. Two child tables (cascade delete with their report)
plus four nullable Text columns on report_cards. All nullable, no backfill;
existing reports keep everything null.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2d5f8a1c4e7"
down_revision: Union[str, Sequence[str], None] = "e1f4a7b2c9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("report_cards", sa.Column("teacher_comment_fr", sa.Text(), nullable=True))
    op.add_column("report_cards", sa.Column("teacher_comment_en", sa.Text(), nullable=True))
    op.add_column("report_cards", sa.Column("principal_comment_fr", sa.Text(), nullable=True))
    op.add_column("report_cards", sa.Column("principal_comment_en", sa.Text(), nullable=True))

    op.create_table(
        "report_conduct_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_card_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(length=50), nullable=False),
        sa.Column("letter_grade", sa.String(length=5), nullable=True),
        sa.ForeignKeyConstraint(["report_card_id"], ["report_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "report_work_habit_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_card_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(length=50), nullable=False),
        sa.Column("letter_grade", sa.String(length=5), nullable=True),
        sa.ForeignKeyConstraint(["report_card_id"], ["report_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("report_work_habit_items")
    op.drop_table("report_conduct_items")
    op.drop_column("report_cards", "principal_comment_en")
    op.drop_column("report_cards", "principal_comment_fr")
    op.drop_column("report_cards", "teacher_comment_en")
    op.drop_column("report_cards", "teacher_comment_fr")
