"""Remove grade_level from students and courses

Revision ID: f1a3c8e2b9d7
Revises: d9e3f1a7c2b5
Create Date: 2026-07-03

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a3c8e2b9d7"
down_revision: Union[str, Sequence[str], None] = "d9e3f1a7c2b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table: str) -> list[str]:
    return [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "grade_level" in _columns(inspector, "students"):
        with op.batch_alter_table("students") as batch_op:
            batch_op.drop_column("grade_level")

    if "grade_level" in _columns(inspector, "courses"):
        with op.batch_alter_table("courses") as batch_op:
            batch_op.drop_column("grade_level")


def downgrade() -> None:
    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(sa.Column("grade_level", sa.String(50), nullable=True))

    with op.batch_alter_table("courses") as batch_op:
        batch_op.add_column(sa.Column("grade_level", sa.String(50), nullable=True))
