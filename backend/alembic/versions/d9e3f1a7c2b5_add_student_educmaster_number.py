"""add student educmaster_number

Revision ID: d9e3f1a7c2b5
Revises: c2e5f8a3b1d9
Create Date: 2026-07-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d9e3f1a7c2b5"
down_revision: Union[str, Sequence[str], None] = "c2e5f8a3b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table_name: str) -> list[str]:
    return [col["name"] for col in inspector.get_columns(table_name)]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "educmaster_number" not in _columns(inspector, "students"):
        op.add_column(
            "students",
            sa.Column("educmaster_number", sa.String(50), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("students", "educmaster_number")
