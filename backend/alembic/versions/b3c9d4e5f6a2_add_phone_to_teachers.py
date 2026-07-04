"""Add phone column to teachers table

Revision ID: b3c9d4e5f6a2
Revises: a2b5c8e1f4d7
Create Date: 2026-07-03

"""

from typing import Union, Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b3c9d4e5f6a2"
down_revision: Union[str, Sequence[str], None] = "a2b5c8e1f4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table: str) -> dict:
    return {c["name"]: c for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "phone" not in _columns(inspector, "teachers"):
        with op.batch_alter_table("teachers") as batch_op:
            batch_op.add_column(sa.Column("phone", sa.String(30), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "phone" in _columns(inspector, "teachers"):
        with op.batch_alter_table("teachers") as batch_op:
            batch_op.drop_column("phone")
