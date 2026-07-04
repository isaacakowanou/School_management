"""Make User.email nullable for teacher/parent accounts without email

Revision ID: a2b5c8e1f4d7
Revises: f1a3c8e2b9d7
Create Date: 2026-07-03

"""

from typing import Union, Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a2b5c8e1f4d7"
down_revision: Union[str, Sequence[str], None] = "f1a3c8e2b9d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table: str) -> dict:
    return {c["name"]: c for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    col = _columns(inspector, "users").get("email", {})
    if col.get("nullable") is False:
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("email", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(255), nullable=False)
