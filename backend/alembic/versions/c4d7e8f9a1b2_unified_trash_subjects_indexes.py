"""Add unified trash subject columns and deleted_at indexes

Revision ID: c4d7e8f9a1b2
Revises: b7c8d9e0f1a2
Create Date: 2026-07-10
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4d7e8f9a1b2"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRASH_TABLES = [
    "classes",
    "students",
    "parents",
    "student_parents",
    "teachers",
    "subjects",
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

PREEXISTING_INDEXES = {"ix_students_deleted_at"}


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(inspector: sa.Inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table) if index.get("name")}


def _foreign_keys(inspector: sa.Inspector, table: str) -> set[str]:
    return {fk["name"] for fk in inspector.get_foreign_keys(table) if fk.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "subjects" in tables:
        columns = _columns(inspector, "subjects")
        if "deleted_at" not in columns:
            op.add_column("subjects", sa.Column("deleted_at", sa.DateTime(), nullable=True))
        if "deleted_batch_id" not in columns:
            op.add_column("subjects", sa.Column("deleted_batch_id", sa.Uuid(), nullable=True))

        inspector = sa.inspect(bind)
        fk_name = "fk_subjects_deleted_batch_id"
        if bind.dialect.name != "sqlite" and fk_name not in _foreign_keys(inspector, "subjects"):
            op.create_foreign_key(
                fk_name,
                "subjects",
                "deletion_batches",
                ["deleted_batch_id"],
                ["id"],
            )

    inspector = sa.inspect(bind)
    for table in TRASH_TABLES:
        if table not in tables:
            continue
        columns = _columns(inspector, table)
        if "deleted_at" not in columns:
            continue
        index_name = f"ix_{table}_deleted_at"
        if index_name not in _indexes(inspector, table):
            op.create_index(index_name, table, ["deleted_at"], unique=False)
        inspector = sa.inspect(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table in reversed(TRASH_TABLES):
        if table not in tables:
            continue
        index_name = f"ix_{table}_deleted_at"
        if index_name in PREEXISTING_INDEXES:
            continue
        if index_name in _indexes(inspector, table):
            op.drop_index(index_name, table_name=table)
        inspector = sa.inspect(bind)

    if "subjects" in tables:
        columns = _columns(inspector, "subjects")
        fk_name = "fk_subjects_deleted_batch_id"
        if bind.dialect.name != "sqlite" and fk_name in _foreign_keys(inspector, "subjects"):
            op.drop_constraint(fk_name, "subjects", type_="foreignkey")
        if "deleted_batch_id" in columns:
            op.drop_column("subjects", "deleted_batch_id")
        if "deleted_at" in columns:
            op.drop_column("subjects", "deleted_at")
