"""add must_change_password to users

Revision ID: c2e5f8a3b1d9
Revises: a13c1b2d3e4f
Create Date: 2026-07-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c2e5f8a3b1d9"
down_revision: Union[str, Sequence[str], None] = "a13c1b2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "must_change_password" not in _columns(inspector, "users"):
        op.add_column(
            "users",
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "must_change_password" in _columns(inspector, "users"):
        op.drop_column("users", "must_change_password")
