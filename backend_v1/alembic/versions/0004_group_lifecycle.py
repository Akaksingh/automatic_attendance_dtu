"""Add group archive state.

Revision ID: 0004_group_lifecycle
Revises: 0003_photo_processing_jobs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_group_lifecycle"
down_revision: Union[str, None] = "0003_photo_processing_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("groups", "archived_at")
