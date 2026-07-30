"""Align UUID foreign-key nullability and indexes with the ORM models.

Revision ID: 0006_uuid_schema_alignment
Revises: 0005_uuid_object_ids
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_uuid_schema_alignment"
down_revision: Union[str, None] = "0005_uuid_object_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table, column in (
        ("groups", "owner_id"),
        ("group_memberships", "group_id"),
        ("group_memberships", "student_id"),
        ("class_sessions", "group_id"),
        ("class_sessions", "created_by_id"),
        ("attendance_records", "session_id"),
        ("attendance_records", "student_id"),
        ("refresh_tokens", "user_id"),
        ("students", "user_id"),
        ("student_photos", "student_id"),
        ("photo_processing_jobs", "student_id"),
    ):
        op.alter_column(table, column, nullable=False)
    op.drop_index("ix_photo_processing_jobs_photo_id", table_name="photo_processing_jobs")
    op.drop_index("ix_students_user_id", table_name="students")
    op.create_index("ix_students_user_id", "students", ["user_id"], unique=True)


def downgrade() -> None:
    raise NotImplementedError("UUID object IDs cannot be safely downgraded")
