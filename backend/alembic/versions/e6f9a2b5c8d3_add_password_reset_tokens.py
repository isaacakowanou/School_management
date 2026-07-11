"""add password reset tokens and anonymous audit actors

Revision ID: e6f9a2b5c8d3
Revises: d5e8f1a4b7c2
Create Date: 2026-07-10
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "e6f9a2b5c8d3"
down_revision: Union[str, Sequence[str], None] = "d5e8f1a4b7c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector: sa.Inspector, table: str) -> dict[str, dict]:
    return {column["name"]: column for column in inspector.get_columns(table)}


def _indexes(inspector: sa.Inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table) if index.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "password_reset_tokens" not in tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("token_version", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )

    inspector = sa.inspect(bind)
    if "password_reset_tokens" in inspector.get_table_names():
        indexes = _indexes(inspector, "password_reset_tokens")
        for name, columns, unique in (
            ("ix_password_reset_tokens_user_id", ["user_id"], False),
            ("ix_password_reset_tokens_token_hash", ["token_hash"], True),
            ("ix_password_reset_tokens_expires_at", ["expires_at"], False),
        ):
            if name not in indexes:
                op.create_index(name, "password_reset_tokens", columns, unique=unique)

    inspector = sa.inspect(bind)
    if "audit_logs" in inspector.get_table_names():
        actor_column = _columns(inspector, "audit_logs").get("actor_user_id", {})
        if actor_column.get("nullable") is False:
            with op.batch_alter_table("audit_logs") as batch_op:
                batch_op.alter_column("actor_user_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "audit_logs" in inspector.get_table_names():
        actor_column = _columns(inspector, "audit_logs").get("actor_user_id", {})
        if actor_column.get("nullable") is True:
            op.execute(sa.text("DELETE FROM audit_logs WHERE actor_user_id IS NULL"))
            with op.batch_alter_table("audit_logs") as batch_op:
                batch_op.alter_column("actor_user_id", existing_type=sa.Uuid(), nullable=False)
    inspector = sa.inspect(bind)
    if "password_reset_tokens" in inspector.get_table_names():
        op.drop_table("password_reset_tokens")
