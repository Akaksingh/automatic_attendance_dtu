"""Add session lifecycle and expiring classroom images.

Revision ID: 0007_class_sessions
Revises: 0006_uuid_schema_alignment
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_class_sessions"
down_revision: Union[str, None] = "0006_uuid_schema_alignment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE sessionstate AS ENUM ('created', 'processing', 'review', 'finalized', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    session_state = postgresql.ENUM("created", "processing", "review", "finalized", "failed", name="sessionstate", create_type=False)
    op.add_column("class_sessions", sa.Column("state", session_state, nullable=False, server_default="created"))
    op.add_column("class_sessions", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_class_sessions_state", "class_sessions", ["state"], unique=False)
    op.create_table(
        "session_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_session_photos_session_id", "session_photos", ["session_id"], unique=False)
    op.create_index("ix_session_photos_storage_key", "session_photos", ["storage_key"], unique=True)
    op.create_index("ix_session_photos_expires_at", "session_photos", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_table("session_photos")
    op.drop_index("ix_class_sessions_state", table_name="class_sessions")
    op.drop_column("class_sessions", "finalized_at")
    op.drop_column("class_sessions", "state")
    sa.Enum(name="sessionstate").drop(op.get_bind(), checkfirst=True)
