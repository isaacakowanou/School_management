"""add classes table and Student/Course class_id FKs

Revision ID: c3e6a9d2f5b8
Revises: b2d5f8a1c4e7
Create Date: 2026-07-01 00:00:00.000000

A1.8 — minimal Class entity for the bulletin header + class stats. Creates the
`classes` table and adds nullable `class_id` FKs (ON DELETE SET NULL) to
students and courses. All nullable, no backfill; existing rows get NULL. The
FK columns use batch mode so the migration runs on both Postgres (prod) and
SQLite (local/dev).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3e6a9d2f5b8"
down_revision: Union[str, Sequence[str], None] = "b2d5f8a1c4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "classes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name_fr", sa.String(length=100), nullable=False),
        sa.Column("name_en", sa.String(length=100), nullable=True),
        sa.Column("school_level", sa.String(length=20), nullable=False),
        sa.Column("stream", sa.String(length=20), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("school_year", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_fr", "school_year", name="uq_class_name_fr_school_year"),
    )

    with op.batch_alter_table("students") as batch_op:
        batch_op.add_column(sa.Column("class_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_students_class_id_classes", "classes", ["class_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("courses") as batch_op:
        batch_op.add_column(sa.Column("class_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_courses_class_id_classes", "classes", ["class_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("courses") as batch_op:
        batch_op.drop_constraint("fk_courses_class_id_classes", type_="foreignkey")
        batch_op.drop_column("class_id")

    with op.batch_alter_table("students") as batch_op:
        batch_op.drop_constraint("fk_students_class_id_classes", type_="foreignkey")
        batch_op.drop_column("class_id")

    op.drop_table("classes")
