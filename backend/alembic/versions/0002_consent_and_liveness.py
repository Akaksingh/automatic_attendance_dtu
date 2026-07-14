"""v1.x: consent audit fields on students + liveness_fail attendance method.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "students",
        sa.Column(
            "consent_recorded_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_students_consent_recorded_by"),
            nullable=True,
        ),
    )
    # Postgres 12+ allows ADD VALUE inside a transaction.
    op.execute("ALTER TYPE attendancemethod ADD VALUE IF NOT EXISTS 'liveness_fail'")


def downgrade() -> None:
    op.drop_column("students", "consent_recorded_by")
    op.drop_column("students", "consent_recorded_at")
    # Postgres cannot remove a value from an enum type; leaving 'liveness_fail'
    # in place is harmless for the v1 code path.
