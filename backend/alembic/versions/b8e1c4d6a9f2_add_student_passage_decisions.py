"""add student passage decisions

Revision ID: b8e1c4d6a9f2
Revises: a7d3e9c2f4b6
Create Date: 2026-07-23
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8e1c4d6a9f2"
down_revision: Union[str, Sequence[str], None] = "a7d3e9c2f4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("academic_status", sa.String(length=20), server_default="active", nullable=False),
    )
    op.add_column("students", sa.Column("graduated_at", sa.DateTime(), nullable=True))

    op.create_table(
        "student_passage_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("school_year", sa.String(length=20), nullable=False),
        sa.Column("target_school_year", sa.String(length=20), nullable=False),
        sa.Column("from_class_id", sa.Uuid(), nullable=True),
        sa.Column("from_class_name", sa.String(length=100), nullable=True),
        sa.Column("result_class_id", sa.Uuid(), nullable=True),
        sa.Column("result_class_name", sa.String(length=100), nullable=True),
        sa.Column("suggested_decision", sa.String(length=30), nullable=False),
        sa.Column("final_decision", sa.String(length=30), nullable=False),
        sa.Column("annual_french_average", sa.Float(), nullable=True),
        sa.Column("annual_english_average", sa.Float(), nullable=True),
        sa.Column("annual_bilingual_average", sa.Float(), nullable=True),
        sa.Column("incomplete_data", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["decided_by_admin_id"], ["users.id"], name="fk_passage_decided_by_admin_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["from_class_id"], ["classes.id"], name="fk_passage_from_class_classes", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["result_class_id"], ["classes.id"], name="fk_passage_result_class_classes", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_passage_student_students"),
        sa.PrimaryKeyConstraint("id", name="pk_student_passage_decisions"),
        sa.UniqueConstraint("student_id", "school_year", name="uq_student_passage_decision_year"),
    )
    op.create_index("ix_student_passage_decisions_school_year", "student_passage_decisions", ["school_year"])
    op.create_index("ix_student_passage_decisions_student_id", "student_passage_decisions", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_student_passage_decisions_student_id", table_name="student_passage_decisions")
    op.drop_index("ix_student_passage_decisions_school_year", table_name="student_passage_decisions")
    op.drop_table("student_passage_decisions")
    op.drop_column("students", "graduated_at")
    op.drop_column("students", "academic_status")
