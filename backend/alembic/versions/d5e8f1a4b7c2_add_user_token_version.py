"""add user token version

Revision ID: d5e8f1a4b7c2
Revises: c4d7e8f9a1b2
Create Date: 2026-07-10
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "d5e8f1a4b7c2"
down_revision: Union[str, Sequence[str], None] = "c4d7e8f9a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" in inspector.get_table_names() and "token_version" not in _columns(inspector, "users"):
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" in inspector.get_table_names() and "token_version" in _columns(inspector, "users"):
        op.drop_column("users", "token_version")
