"""add recoverable deletion batches

Revision ID: a13c1b2d3e4f
Revises: f9a1c2d3e4b5
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a13c1b2d3e4f"
down_revision: Union[str, Sequence[str], None] = "f9a1c2d3e4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "classes",
    "students",
    "parents",
    "student_parents",
    "teachers",
    "courses",
    "enrollments",
    "grade_items",
    "grades",
    "course_results",
    "report_cards",
    "report_card_courses",
    "report_conduct_items",
    "report_work_habit_items",
    "ai_warnings",
]


def _tables(inspector: sa.Inspector) -> set[str]:
    return set(inspector.get_table_names())


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _foreign_keys(inspector: sa.Inspector, table: str) -> set[str]:
    return {fk["name"] for fk in inspector.get_foreign_keys(table) if fk.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = _tables(inspector)

    if "deletion_batches" not in existing_tables:
        op.create_table(
            "deletion_batches",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_id", sa.Uuid(), nullable=False),
            sa.Column("target_label", sa.String(length=255), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("deleted_by_user_id", sa.Uuid(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("restored_at", sa.DateTime(), nullable=True),
            sa.Column("restored_by_user_id", sa.Uuid(), nullable=True),
            sa.Column("counts_json", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["deleted_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["restored_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    for table in TABLES:
        existing_columns = _columns(inspector, table)
        if table != "students" and "deleted_at" not in existing_columns:
            op.add_column(table, sa.Column("deleted_at", sa.DateTime(), nullable=True))
        if "deleted_batch_id" not in existing_columns:
            op.add_column(table, sa.Column("deleted_batch_id", sa.Uuid(), nullable=True))

        # SQLite cannot add a foreign key constraint to an existing table with
        # ALTER TABLE. Postgres/Neon can, so create it there when absent.
        fk_name = f"fk_{table}_deleted_batch_id"
        if bind.dialect.name != "sqlite" and fk_name not in _foreign_keys(sa.inspect(bind), table):
            op.create_foreign_key(
                fk_name,
                table,
                "deletion_batches",
                ["deleted_batch_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in reversed(TABLES):
        columns = _columns(inspector, table)
        fk_name = f"fk_{table}_deleted_batch_id"
        if bind.dialect.name != "sqlite" and fk_name in _foreign_keys(inspector, table):
            op.drop_constraint(fk_name, table, type_="foreignkey")
        if "deleted_batch_id" in columns:
            op.drop_column(table, "deleted_batch_id")
        if table != "students" and "deleted_at" in columns:
            op.drop_column(table, "deleted_at")
        inspector = sa.inspect(bind)
    if "deletion_batches" in _tables(inspector):
        op.drop_table("deletion_batches")
