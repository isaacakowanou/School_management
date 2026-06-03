"""add scalability indexes

Revision ID: 3c9c6f1f2a7b
Revises: ba9dbad0d63e
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3c9c6f1f2a7b"
down_revision: Union[str, Sequence[str], None] = "ba9dbad0d63e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"], unique=False)
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"], unique=False)
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"], unique=False)

    op.create_index("ix_report_cards_student_id", "report_cards", ["student_id"], unique=False)
    op.create_index("ix_report_cards_status", "report_cards", ["status"], unique=False)
    op.create_index("ix_report_cards_created_at", "report_cards", ["created_at"], unique=False)

    op.create_index("ix_courses_teacher_id", "courses", ["teacher_id"], unique=False)
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"], unique=False)
    op.create_index("ix_grade_items_course_id", "grade_items", ["course_id"], unique=False)
    op.create_index("ix_course_results_course_id", "course_results", ["course_id"], unique=False)
    op.create_index(
        "ix_report_card_courses_report_card_id",
        "report_card_courses",
        ["report_card_id"],
        unique=False,
    )
    op.create_index("ix_ai_warnings_report_card_id", "ai_warnings", ["report_card_id"], unique=False)
    op.create_index("ix_grades_submitted_by_teacher_id", "grades", ["submitted_by_teacher_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_grades_submitted_by_teacher_id", table_name="grades")
    op.drop_index("ix_ai_warnings_report_card_id", table_name="ai_warnings")
    op.drop_index("ix_report_card_courses_report_card_id", table_name="report_card_courses")
    op.drop_index("ix_course_results_course_id", table_name="course_results")
    op.drop_index("ix_grade_items_course_id", table_name="grade_items")
    op.drop_index("ix_enrollments_course_id", table_name="enrollments")
    op.drop_index("ix_courses_teacher_id", table_name="courses")

    op.drop_index("ix_report_cards_created_at", table_name="report_cards")
    op.drop_index("ix_report_cards_status", table_name="report_cards")
    op.drop_index("ix_report_cards_student_id", table_name="report_cards")

    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
