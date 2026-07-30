"""Convert all v1 object identifiers and foreign keys to UUIDs.

Revision ID: 0005_uuid_object_ids
Revises: 0004_group_lifecycle
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_uuid_object_ids"
down_revision: Union[str, None] = "0004_group_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Generate replacement IDs and reference values while the old integer keys
    # are still available. This preserves existing rows during the conversion.
    for table in ("users", "groups", "group_memberships", "class_sessions", "attendance_records", "refresh_tokens", "students", "student_photos", "photo_processing_jobs"):
        op.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN id_uuid uuid DEFAULT gen_random_uuid() NOT NULL"))

    op.execute("ALTER TABLE groups ADD COLUMN owner_uuid uuid")
    op.execute("ALTER TABLE group_memberships ADD COLUMN group_uuid uuid, ADD COLUMN student_uuid uuid")
    op.execute("ALTER TABLE class_sessions ADD COLUMN group_uuid uuid, ADD COLUMN created_by_uuid uuid")
    op.execute("ALTER TABLE attendance_records ADD COLUMN session_uuid uuid, ADD COLUMN student_uuid uuid")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN user_uuid uuid")
    op.execute("ALTER TABLE students ADD COLUMN user_uuid uuid")
    op.execute("ALTER TABLE student_photos ADD COLUMN student_uuid uuid")
    op.execute("ALTER TABLE photo_processing_jobs ADD COLUMN student_uuid uuid, ADD COLUMN photo_uuid uuid")

    op.execute("UPDATE groups g SET owner_uuid = u.id_uuid FROM users u WHERE u.id = g.owner_id")
    op.execute("UPDATE group_memberships m SET group_uuid = g.id_uuid, student_uuid = u.id_uuid FROM groups g, users u WHERE g.id = m.group_id AND u.id = m.student_id")
    op.execute("UPDATE class_sessions s SET group_uuid = g.id_uuid, created_by_uuid = u.id_uuid FROM groups g, users u WHERE g.id = s.group_id AND u.id = s.created_by_id")
    op.execute("UPDATE attendance_records a SET session_uuid = s.id_uuid, student_uuid = u.id_uuid FROM class_sessions s, users u WHERE s.id = a.session_id AND u.id = a.student_id")
    op.execute("UPDATE refresh_tokens r SET user_uuid = u.id_uuid FROM users u WHERE u.id = r.user_id")
    op.execute("UPDATE students s SET user_uuid = u.id_uuid FROM users u WHERE u.id = s.user_id")
    op.execute("UPDATE student_photos p SET student_uuid = s.id_uuid FROM students s WHERE s.id = p.student_id")
    op.execute("UPDATE photo_processing_jobs j SET student_uuid = (SELECT s.id_uuid FROM students s WHERE s.id = j.student_id), photo_uuid = (SELECT p.id_uuid FROM student_photos p WHERE p.id = j.photo_id)")

    # Drop old foreign keys/unique constraints before replacing their columns.
    for statement in (
        "ALTER TABLE groups DROP CONSTRAINT groups_owner_id_fkey",
        "ALTER TABLE group_memberships DROP CONSTRAINT group_memberships_group_id_fkey",
        "ALTER TABLE group_memberships DROP CONSTRAINT group_memberships_student_id_fkey",
        "ALTER TABLE class_sessions DROP CONSTRAINT class_sessions_group_id_fkey",
        "ALTER TABLE class_sessions DROP CONSTRAINT class_sessions_created_by_id_fkey",
        "ALTER TABLE attendance_records DROP CONSTRAINT attendance_records_session_id_fkey",
        "ALTER TABLE attendance_records DROP CONSTRAINT attendance_records_student_id_fkey",
        "ALTER TABLE refresh_tokens DROP CONSTRAINT refresh_tokens_user_id_fkey",
        "ALTER TABLE students DROP CONSTRAINT students_user_id_fkey",
        "ALTER TABLE student_photos DROP CONSTRAINT student_photos_student_id_fkey",
        "ALTER TABLE photo_processing_jobs DROP CONSTRAINT photo_processing_jobs_student_id_fkey",
        "ALTER TABLE photo_processing_jobs DROP CONSTRAINT photo_processing_jobs_photo_id_fkey",
        "ALTER TABLE group_memberships DROP CONSTRAINT uq_group_membership",
        "ALTER TABLE attendance_records DROP CONSTRAINT uq_session_attendance",
    ):
        op.execute(statement)

    for table in ("users", "groups", "group_memberships", "class_sessions", "attendance_records", "refresh_tokens", "students", "student_photos", "photo_processing_jobs"):
        op.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT {table}_pkey"))

    for table, columns in {
        "users": ("id",),
        "groups": ("id", "owner_id"),
        "group_memberships": ("id", "group_id", "student_id"),
        "class_sessions": ("id", "group_id", "created_by_id"),
        "attendance_records": ("id", "session_id", "student_id"),
        "refresh_tokens": ("id", "user_id"),
        "students": ("id", "user_id"),
        "student_photos": ("id", "student_id"),
        "photo_processing_jobs": ("id", "student_id", "photo_id"),
    }.items():
        for column in columns:
            op.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))

    for table in ("users", "groups", "group_memberships", "class_sessions", "attendance_records", "refresh_tokens", "students", "student_photos", "photo_processing_jobs"):
        op.execute(sa.text(f"ALTER TABLE {table} RENAME COLUMN id_uuid TO id"))
    for table, old, new in (
        ("groups", "owner_uuid", "owner_id"),
        ("group_memberships", "group_uuid", "group_id"),
        ("group_memberships", "student_uuid", "student_id"),
        ("class_sessions", "group_uuid", "group_id"),
        ("class_sessions", "created_by_uuid", "created_by_id"),
        ("attendance_records", "session_uuid", "session_id"),
        ("attendance_records", "student_uuid", "student_id"),
        ("refresh_tokens", "user_uuid", "user_id"),
        ("students", "user_uuid", "user_id"),
        ("student_photos", "student_uuid", "student_id"),
        ("photo_processing_jobs", "student_uuid", "student_id"),
        ("photo_processing_jobs", "photo_uuid", "photo_id"),
    ):
        op.execute(sa.text(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}"))

    for table in ("users", "groups", "group_memberships", "class_sessions", "attendance_records", "refresh_tokens", "students", "student_photos", "photo_processing_jobs"):
        op.execute(sa.text(f"ALTER TABLE {table} ADD CONSTRAINT {table}_pkey PRIMARY KEY (id)"))

    for statement in (
        "ALTER TABLE groups ADD CONSTRAINT groups_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES users(id)",
        "ALTER TABLE group_memberships ADD CONSTRAINT group_memberships_group_id_fkey FOREIGN KEY (group_id) REFERENCES groups(id)",
        "ALTER TABLE group_memberships ADD CONSTRAINT group_memberships_student_id_fkey FOREIGN KEY (student_id) REFERENCES users(id)",
        "ALTER TABLE class_sessions ADD CONSTRAINT class_sessions_group_id_fkey FOREIGN KEY (group_id) REFERENCES groups(id)",
        "ALTER TABLE class_sessions ADD CONSTRAINT class_sessions_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES users(id)",
        "ALTER TABLE attendance_records ADD CONSTRAINT attendance_records_session_id_fkey FOREIGN KEY (session_id) REFERENCES class_sessions(id)",
        "ALTER TABLE attendance_records ADD CONSTRAINT attendance_records_student_id_fkey FOREIGN KEY (student_id) REFERENCES users(id)",
        "ALTER TABLE refresh_tokens ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id)",
        "ALTER TABLE students ADD CONSTRAINT students_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
        "ALTER TABLE student_photos ADD CONSTRAINT student_photos_student_id_fkey FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE",
        "ALTER TABLE photo_processing_jobs ADD CONSTRAINT photo_processing_jobs_student_id_fkey FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE",
        "ALTER TABLE photo_processing_jobs ADD CONSTRAINT photo_processing_jobs_photo_id_fkey FOREIGN KEY (photo_id) REFERENCES student_photos(id) ON DELETE SET NULL",
        "ALTER TABLE group_memberships ADD CONSTRAINT uq_group_membership UNIQUE (group_id, student_id)",
        "ALTER TABLE attendance_records ADD CONSTRAINT uq_session_attendance UNIQUE (session_id, student_id)",
    ):
        op.execute(statement)

    op.execute("ALTER TABLE student_photos ALTER COLUMN storage_key DROP NOT NULL")
    op.execute("CREATE INDEX ix_groups_owner_id ON groups (owner_id)")
    op.execute("CREATE INDEX ix_group_memberships_group_id ON group_memberships (group_id)")
    op.execute("CREATE INDEX ix_group_memberships_student_id ON group_memberships (student_id)")
    op.execute("CREATE INDEX ix_class_sessions_group_id ON class_sessions (group_id)")
    op.execute("CREATE INDEX ix_class_sessions_created_by_id ON class_sessions (created_by_id)")
    op.execute("CREATE INDEX ix_attendance_records_session_id ON attendance_records (session_id)")
    op.execute("CREATE INDEX ix_attendance_records_student_id ON attendance_records (student_id)")
    op.execute("CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id)")
    op.execute("CREATE INDEX ix_students_user_id ON students (user_id)")
    op.execute("CREATE INDEX ix_student_photos_student_id ON student_photos (student_id)")
    op.execute("CREATE INDEX ix_photo_processing_jobs_student_id ON photo_processing_jobs (student_id)")
    op.execute("CREATE INDEX ix_photo_processing_jobs_photo_id ON photo_processing_jobs (photo_id)")


def downgrade() -> None:
    raise NotImplementedError("UUID object IDs cannot be safely downgraded")
