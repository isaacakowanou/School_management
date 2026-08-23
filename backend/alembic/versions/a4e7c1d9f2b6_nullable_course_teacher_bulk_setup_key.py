"""allow unassigned courses and guard active catalog setup duplicates

Revision ID: a4e7c1d9f2b6
Revises: f3b7d1e5a9c4
Create Date: 2026-07-30
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4e7c1d9f2b6"
down_revision: Union[str, Sequence[str], None] = "f3b7d1e5a9c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("courses") as batch_op:
        batch_op.alter_column("teacher_id", existing_type=sa.Uuid(), nullable=True)

    op.create_index(
        "uq_active_course_year_class_subject",
        "courses",
        ["school_year", "class_id", "subject_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND class_id IS NOT NULL AND subject_id IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND class_id IS NOT NULL AND subject_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    courses = sa.table("courses", sa.column("teacher_id", sa.Uuid()))
    if bind.execute(sa.select(courses.c.teacher_id).where(courses.c.teacher_id.is_(None)).limit(1)).first():
        raise RuntimeError("Assign teachers to all courses before downgrading teacher_id to NOT NULL.")

    op.drop_index("uq_active_course_year_class_subject", table_name="courses")
    with op.batch_alter_table("courses") as batch_op:
        batch_op.alter_column("teacher_id", existing_type=sa.Uuid(), nullable=False)
