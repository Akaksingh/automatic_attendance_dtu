"""Add student identity and verified photo enrollment history.

Revision ID: 0002_student_profiles_and_photos
Revises: 0001_initial_v1_schema
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_student_profiles_and_photos"
down_revision: Union[str, None] = "0001_initial_v1_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("roll_no", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("profile_image_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_students_user_id", "students", ["user_id"], unique=True)
    op.create_index("ix_students_roll_no", "students", ["roll_no"], unique=True)

    op.create_table(
        "student_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=False),
        sa.Column("similarity_to_previous", sa.Float(), nullable=True),
        sa.Column("is_profile", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_student_photos_student_id", "student_photos", ["student_id"], unique=False)
    op.create_index("ix_student_photos_storage_key", "student_photos", ["storage_key"], unique=True)


def downgrade() -> None:
    op.drop_table("student_photos")
    op.drop_table("students")
