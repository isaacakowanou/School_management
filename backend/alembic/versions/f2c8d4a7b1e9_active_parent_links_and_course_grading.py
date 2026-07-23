"""guard active parent links and persist course grading identity

Revision ID: f2c8d4a7b1e9
Revises: e6f9a2b5c8d3
Create Date: 2026-07-23
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2c8d4a7b1e9"
down_revision: Union[str, Sequence[str], None] = "e6f9a2b5c8d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(inspector: sa.Inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table) if index.get("name")}


def _unique_constraints(inspector: sa.Inspector, table: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table)
        if constraint.get("name")
    }


def _delete_duplicate_links(*, active_only: bool) -> None:
    where_clause = "WHERE deleted_at IS NULL" if active_only else ""
    op.execute(
        sa.text(
            f"""
            DELETE FROM student_parents
            WHERE id IN (
                SELECT duplicate_id
                FROM (
                    SELECT
                        id AS duplicate_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY student_id, parent_id
                            ORDER BY id
                        ) AS duplicate_rank
                    FROM student_parents
                    {where_clause}
                ) AS ranked_links
                WHERE duplicate_rank > 1
            )
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "grading_system" not in _columns(inspector, "courses"):
        op.add_column("courses", sa.Column("grading_system", sa.String(length=20), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE courses
            SET grading_system = CASE
                WHEN language_group = 'FRENCH'
                 AND class_id IN (SELECT id FROM classes WHERE school_level = 'college')
                THEN 'BENINESE'
                ELSE 'WEIGHTED'
            END
            WHERE grading_system IS NULL
            """
        )
    )

    # Production may already contain active duplicates. Keep one canonical
    # link before the partial unique index is installed.
    _delete_duplicate_links(active_only=True)

    inspector = sa.inspect(bind)
    if "uq_student_parent" in _unique_constraints(inspector, "student_parents"):
        with op.batch_alter_table("student_parents") as batch_op:
            batch_op.drop_constraint("uq_student_parent", type_="unique")

    inspector = sa.inspect(bind)
    if "uq_active_student_parent" not in _indexes(inspector, "student_parents"):
        op.create_index(
            "uq_active_student_parent",
            "student_parents",
            ["student_id", "parent_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "uq_active_student_parent" in _indexes(inspector, "student_parents"):
        op.drop_index("uq_active_student_parent", table_name="student_parents")

    # The original unconditional constraint also covered deleted links.
    _delete_duplicate_links(active_only=False)
    inspector = sa.inspect(bind)
    if "uq_student_parent" not in _unique_constraints(inspector, "student_parents"):
        with op.batch_alter_table("student_parents") as batch_op:
            batch_op.create_unique_constraint(
                "uq_student_parent",
                ["student_id", "parent_id"],
            )

    inspector = sa.inspect(bind)
    if "grading_system" in _columns(inspector, "courses"):
        with op.batch_alter_table("courses") as batch_op:
            batch_op.drop_column("grading_system")
