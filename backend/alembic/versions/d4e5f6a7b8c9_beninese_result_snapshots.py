"""Beninese grading: intermediates on course_results and report_card_courses

Revision ID: d4e5f6a7b8c9
Revises: a2b3c4d5e6f7
Create Date: 2026-07-08

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table: str) -> list[str]:
    return [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cr_cols = _columns(inspector, "course_results")
    rcc_cols = _columns(inspector, "report_card_courses")

    with op.batch_alter_table("course_results") as batch_op:
        if "moy_int" not in cr_cols:
            batch_op.add_column(sa.Column("moy_int", sa.Float(), nullable=True))
        if "mcc" not in cr_cols:
            batch_op.add_column(sa.Column("mcc", sa.Float(), nullable=True))
        if "devoir_score" not in cr_cols:
            batch_op.add_column(sa.Column("devoir_score", sa.Float(), nullable=True))
        if "composition_score" not in cr_cols:
            batch_op.add_column(sa.Column("composition_score", sa.Float(), nullable=True))

    with op.batch_alter_table("report_card_courses") as batch_op:
        if "coefficient" not in rcc_cols:
            batch_op.add_column(
                sa.Column("coefficient", sa.Integer(), nullable=False, server_default="1")
            )
        if "moy_int" not in rcc_cols:
            batch_op.add_column(sa.Column("moy_int", sa.Float(), nullable=True))
        if "mcc" not in rcc_cols:
            batch_op.add_column(sa.Column("mcc", sa.Float(), nullable=True))
        if "devoir_score" not in rcc_cols:
            batch_op.add_column(sa.Column("devoir_score", sa.Float(), nullable=True))
        if "composition_score" not in rcc_cols:
            batch_op.add_column(sa.Column("composition_score", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("report_card_courses") as batch_op:
        batch_op.drop_column("composition_score")
        batch_op.drop_column("devoir_score")
        batch_op.drop_column("mcc")
        batch_op.drop_column("moy_int")
        batch_op.drop_column("coefficient")

    with op.batch_alter_table("course_results") as batch_op:
        batch_op.drop_column("composition_score")
        batch_op.drop_column("devoir_score")
        batch_op.drop_column("mcc")
        batch_op.drop_column("moy_int")
