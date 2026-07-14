"""Initial schema (v1): users, students, embeddings, courses, rosters,
sessions, attendance, audit log.

Matches the schema `create_all` produced for v1 deployments, so existing
databases can be adopted with `alembic stamp 0001` (see app/migrations.py).

Revision ID: 0001
Revises:
Create Date: 2026-07-14
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBED_DIM = 512


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "teacher", name="role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("roll_no", sa.String(64), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("department", sa.String(128), nullable=False),
        sa.Column("biometric_consent", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_students_roll_no", "students", ["roll_no"], unique=True)

    op.create_table(
        "face_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vector", Vector(EMBED_DIM), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_face_embeddings_student_id", "face_embeddings", ["student_id"], unique=True)

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("department", sa.String(128), nullable=False),
    )
    op.create_index("ix_courses_code", "courses", ["code"], unique=True)

    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("course_id", "student_id", name="uq_course_student"),
    )
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])

    op.create_table(
        "class_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "state",
            sa.Enum("created", "processing", "review", "finalized", "failed", name="sessionstate"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("photo_path", sa.String(512), nullable=True),
        sa.Column("photo_purged", sa.Boolean(), nullable=False),
        sa.Column("faces_detected", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_class_sessions_course_id", "class_sessions", ["course_id"])

    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("class_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Enum("present", "absent", name="attendancestatus"), nullable=False),
        sa.Column("method", sa.Enum("auto", "manual", name="attendancemethod"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "corrected_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("session_id", "student_id", name="uq_session_student"),
    )
    op.create_index("ix_attendance_session_id", "attendance", ["session_id"])
    op.create_index("ix_attendance_student_id", "attendance", ["student_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("attendance")
    op.drop_table("class_sessions")
    op.drop_table("enrollments")
    op.drop_table("courses")
    op.drop_table("face_embeddings")
    op.drop_table("students")
    op.drop_table("users")
    for enum_name in ("attendancemethod", "attendancestatus", "sessionstate", "role"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
