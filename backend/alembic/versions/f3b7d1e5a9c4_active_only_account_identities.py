"""active-only account identities

Revision ID: f3b7d1e5a9c4
Revises: e8a4c7d1f3b6
Create Date: 2026-07-27
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "f3b7d1e5a9c4"
down_revision: Union[str, Sequence[str], None] = "e8a4c7d1f3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def _backfill_deleted_users(bind) -> dict[str, int]:
    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("role", sa.String()),
        sa.column("deleted_at", sa.DateTime()),
    )
    parents = sa.table(
        "parents",
        sa.column("user_id", sa.Uuid()),
        sa.column("deleted_at", sa.DateTime()),
    )
    teachers = sa.table(
        "teachers",
        sa.column("user_id", sa.Uuid()),
        sa.column("deleted_at", sa.DateTime()),
    )

    counts = {"parents": 0, "teachers": 0}
    for role, profiles, key in (
        ("parent", parents, "parents"),
        ("teacher", teachers, "teachers"),
    ):
        rows = bind.execute(
            sa.select(profiles.c.user_id, profiles.c.deleted_at)
            .join(users, users.c.id == profiles.c.user_id)
            .where(
                users.c.role == role,
                users.c.deleted_at.is_(None),
                profiles.c.deleted_at.is_not(None),
            )
        ).all()
        for row in rows:
            result = bind.execute(
                users.update()
                .where(users.c.id == row.user_id, users.c.deleted_at.is_(None))
                .values(deleted_at=row.deleted_at)
            )
            counts[key] += result.rowcount or 0

    print(f"active-only account identity backfill: {counts}")
    return counts


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "deleted_at" not in _column_names(inspector, "users"):
        op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    _backfill_deleted_users(bind)
    inspector = sa.inspect(bind)

    user_indexes = _index_names(inspector, "users")
    if "ix_users_email" in user_indexes:
        op.drop_index("ix_users_email", table_name="users")
    if "uq_active_user_email" not in user_indexes:
        op.create_index(
            "uq_active_user_email",
            "users",
            ["email"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )

    teacher_indexes = _index_names(sa.inspect(bind), "teachers")
    if "ix_teachers_employee_number" in teacher_indexes:
        op.drop_index("ix_teachers_employee_number", table_name="teachers")
    if "uq_active_teacher_employee_number" not in teacher_indexes:
        op.create_index(
            "uq_active_teacher_employee_number",
            "teachers",
            ["employee_number"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )


def _assert_global_identity_downgrade_is_safe(bind) -> None:
    users = sa.table("users", sa.column("email", sa.String()))
    teachers = sa.table("teachers", sa.column("employee_number", sa.String()))
    duplicate_email = bind.execute(
        sa.select(users.c.email)
        .where(users.c.email.is_not(None))
        .group_by(users.c.email)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    duplicate_employee = bind.execute(
        sa.select(teachers.c.employee_number)
        .group_by(teachers.c.employee_number)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate_email or duplicate_employee:
        raise RuntimeError(
            "Cannot restore global identity indexes while deleted rows reuse active identities."
        )


def downgrade() -> None:
    bind = op.get_bind()
    _assert_global_identity_downgrade_is_safe(bind)
    inspector = sa.inspect(bind)

    user_indexes = _index_names(inspector, "users")
    if "uq_active_user_email" in user_indexes:
        op.drop_index("uq_active_user_email", table_name="users")
    if "ix_users_email" not in user_indexes:
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    teacher_indexes = _index_names(sa.inspect(bind), "teachers")
    if "uq_active_teacher_employee_number" in teacher_indexes:
        op.drop_index("uq_active_teacher_employee_number", table_name="teachers")
    if "ix_teachers_employee_number" not in teacher_indexes:
        op.create_index(
            "ix_teachers_employee_number",
            "teachers",
            ["employee_number"],
            unique=True,
        )

    if "deleted_at" in _column_names(sa.inspect(bind), "users"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("deleted_at")
