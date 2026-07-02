"""add subjects table, seed GGFK catalog, add Course.subject_id FK

Revision ID: d7a4c9e2f6b1
Revises: c3e6a9d2f5b8
Create Date: 2026-07-02 00:00:00.000000

A1.9 — Subject reference table seeded from backend/ggfk_subject_catalog.json
(78 subjects across the four level groups), plus a nullable subject_id FK on
courses (ON DELETE SET NULL, batch mode for SQLite parity — same pattern as
the A1.8 class_id FK). Course.name is untouched: it stays the operative
display column, denormalized from the subject at course create/update time.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from subject_catalog import build_subject_rows, load_catalog

# revision identifiers, used by Alembic.
revision: str = "d7a4c9e2f6b1"
down_revision: Union[str, Sequence[str], None] = "c3e6a9d2f5b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    subjects = op.create_table(
        "subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name_fr", sa.String(length=200), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("section", sa.String(length=20), nullable=False),
        sa.Column("level_group", sa.String(length=30), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("applicable_classes", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name_fr", "level_group", "section", name="uq_subject_name_fr_level_group_section"
        ),
    )

    op.bulk_insert(subjects, build_subject_rows(load_catalog()))

    with op.batch_alter_table("courses") as batch_op:
        batch_op.add_column(sa.Column("subject_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_courses_subject_id_subjects", "subjects", ["subject_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("courses") as batch_op:
        batch_op.drop_constraint("fk_courses_subject_id_subjects", type_="foreignkey")
        batch_op.drop_column("subject_id")

    op.drop_table("subjects")
