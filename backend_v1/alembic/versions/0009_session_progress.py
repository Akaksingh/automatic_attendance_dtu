"""Persist Celery classroom-image processing progress."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_session_progress"
down_revision: Union[str, None] = "0008_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("class_sessions", sa.Column("processing_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("class_sessions", sa.Column("processing_completed", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("class_sessions", sa.Column("processing_message", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("class_sessions", "processing_message")
    op.drop_column("class_sessions", "processing_completed")
    op.drop_column("class_sessions", "processing_total")
