"""add student class assignments

Revision ID: e8a4c7d1f3b6
Revises: d4f7c9a1b2e3
Create Date: 2026-07-24
"""

from collections import defaultdict
from collections.abc import Sequence
from typing import Union
import uuid

import sqlalchemy as sa
from alembic import op


revision: str = "e8a4c7d1f3b6"
down_revision: Union[str, Sequence[str], None] = "d4f7c9a1b2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_assignments(bind) -> dict[str, int]:
    """Insert only missing student/year rows, so the data step is rerunnable."""
    assignments = sa.table(
        "student_class_assignments",
        sa.column("id", sa.Uuid()),
        sa.column("student_id", sa.Uuid()),
        sa.column("school_year", sa.String()),
        sa.column("class_id", sa.Uuid()),
        sa.column("class_name_snapshot", sa.String()),
    )
    students = sa.table(
        "students",
        sa.column("id", sa.Uuid()),
        sa.column("class_id", sa.Uuid()),
    )
    classes = sa.table(
        "classes",
        sa.column("id", sa.Uuid()),
        sa.column("name_fr", sa.String()),
        sa.column("school_year", sa.String()),
    )
    courses = sa.table(
        "courses",
        sa.column("id", sa.Uuid()),
        sa.column("class_id", sa.Uuid()),
        sa.column("school_year", sa.String()),
    )
    enrollments = sa.table(
        "enrollments",
        sa.column("student_id", sa.Uuid()),
        sa.column("course_id", sa.Uuid()),
        sa.column("deleted_at", sa.DateTime()),
    )

    existing = {
        (row.student_id, row.school_year)
        for row in bind.execute(
            sa.select(assignments.c.student_id, assignments.c.school_year)
        )
    }
    live_rows = bind.execute(
        sa.select(
            students.c.id.label("student_id"),
            classes.c.school_year,
            classes.c.id.label("class_id"),
            classes.c.name_fr,
        ).join(classes, students.c.class_id == classes.c.id)
    ).all()

    live_count = 0
    for row in live_rows:
        key = (row.student_id, row.school_year)
        if key in existing:
            continue
        bind.execute(
            assignments.insert().values(
                id=uuid.uuid4(),
                student_id=row.student_id,
                school_year=row.school_year,
                class_id=row.class_id,
                class_name_snapshot=row.name_fr,
            )
        )
        existing.add(key)
        live_count += 1

    evidence: dict[tuple, dict] = defaultdict(dict)
    evidence_rows = bind.execute(
        sa.select(
            enrollments.c.student_id,
            courses.c.school_year,
            classes.c.id.label("class_id"),
            classes.c.name_fr,
        )
        .join(courses, enrollments.c.course_id == courses.c.id)
        .join(classes, courses.c.class_id == classes.c.id)
        .where(enrollments.c.deleted_at.is_(None))
    ).all()
    for row in evidence_rows:
        evidence[(row.student_id, row.school_year)][row.class_id] = row.name_fr

    enrollment_count = 0
    ambiguous_count = 0
    for key, class_evidence in evidence.items():
        if key in existing:
            continue
        if len(class_evidence) != 1:
            ambiguous_count += 1
            continue
        class_id, class_name = next(iter(class_evidence.items()))
        bind.execute(
            assignments.insert().values(
                id=uuid.uuid4(),
                student_id=key[0],
                school_year=key[1],
                class_id=class_id,
                class_name_snapshot=class_name,
            )
        )
        existing.add(key)
        enrollment_count += 1

    unresolved_count = bind.scalar(
        sa.select(sa.func.count(students.c.id)).where(
            ~sa.exists().where(assignments.c.student_id == students.c.id)
        )
    ) or 0
    counts = {
        "live_pointer": live_count,
        "enrollment_evidence": enrollment_count,
        "ambiguous_student_years": ambiguous_count,
        "students_unresolved": unresolved_count,
    }
    print(f"student_class_assignments backfill: {counts}")
    return counts


def upgrade() -> None:
    op.create_table(
        "student_class_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("school_year", sa.String(length=20), nullable=False),
        sa.Column("class_id", sa.Uuid(), nullable=True),
        sa.Column("class_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "school_year", name="uq_student_class_assignment_year"
        ),
    )
    op.create_index(
        "ix_student_class_assignments_year_class",
        "student_class_assignments",
        ["school_year", "class_id"],
        unique=False,
    )
    _backfill_assignments(op.get_bind())


def downgrade() -> None:
    op.drop_index(
        "ix_student_class_assignments_year_class",
        table_name="student_class_assignments",
    )
    op.drop_table("student_class_assignments")
