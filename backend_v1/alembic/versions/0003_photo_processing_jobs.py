"""Add durable asynchronous photo-processing jobs.

Revision ID: 0003_photo_processing_jobs
Revises: 0002_student_profiles_and_photos
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_photo_processing_jobs"
down_revision: Union[str, None] = "0002_student_profiles_and_photos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE photojobstatus AS ENUM ('pending', 'processing', 'approved', 'rejected', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    status_column = postgresql.ENUM("pending", "processing", "approved", "rejected", "failed", name="photojobstatus", create_type=False)
    op.create_table(
        "photo_processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("status", status_column, nullable=False, server_default="pending"),
        sa.Column("similarity_to_previous", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("photo_id", sa.Integer(), sa.ForeignKey("student_photos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_photo_processing_jobs_student_id", "photo_processing_jobs", ["student_id"], unique=False)
    op.create_index("ix_photo_processing_jobs_storage_key", "photo_processing_jobs", ["storage_key"], unique=True)
    op.create_index("ix_photo_processing_jobs_status", "photo_processing_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("photo_processing_jobs")
    sa.Enum(name="photojobstatus").drop(op.get_bind(), checkfirst=True)
