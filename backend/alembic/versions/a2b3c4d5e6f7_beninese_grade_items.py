"""Beninese grading: course.coefficient, grade_items.item_type, nullable weight/category

Revision ID: a2b3c4d5e6f7
Revises: b3c9d4e5f6a2
Create Date: 2026-07-08

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "b3c9d4e5f6a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table: str) -> list[str]:
    return [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    course_cols = _columns(inspector, "courses")
    grade_item_cols = _columns(inspector, "grade_items")

    if "coefficient" not in course_cols:
        with op.batch_alter_table("courses") as batch_op:
            batch_op.add_column(
                sa.Column("coefficient", sa.Integer(), nullable=False, server_default="1")
            )

    if "item_type" not in grade_item_cols:
        with op.batch_alter_table("grade_items") as batch_op:
            batch_op.add_column(
                sa.Column("item_type", sa.String(20), nullable=True)
            )

    # Make weight nullable (Beninese items have no weight).
    # SQLite requires batch_alter for column alterations.
    with op.batch_alter_table("grade_items") as batch_op:
        batch_op.alter_column("weight", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("category", existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("grade_items") as batch_op:
        batch_op.alter_column("category", existing_type=sa.String(100), nullable=False)
        batch_op.alter_column("weight", existing_type=sa.Float(), nullable=False)

    with op.batch_alter_table("grade_items") as batch_op:
        batch_op.drop_column("item_type")

    with op.batch_alter_table("courses") as batch_op:
        batch_op.drop_column("coefficient")
