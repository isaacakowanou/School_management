"""add student school_level

Revision ID: 43b4cc97eee6
Revises: 3c9c6f1f2a7b
Create Date: 2026-06-10 18:04:44.391188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '43b4cc97eee6'
down_revision: Union[str, Sequence[str], None] = '3c9c6f1f2a7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("students", sa.Column("school_level", sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("students", "school_level")
