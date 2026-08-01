"""Add durable asynchronous spreadsheet import jobs."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_import_jobs"
down_revision: Union[str, None] = "0009_session_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE importjobstatus AS ENUM ('pending', 'processing', 'completed', 'failed')")
    status_type = postgresql.ENUM("pending", "processing", "completed", "failed", name="importjobstatus", create_type=False)
    op.create_table(
        "import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", status_type, nullable=False, server_default="pending"),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=True),
        sa.Column("spreadsheet_key", sa.String(length=512), nullable=False),
        sa.Column("images_zip_key", sa.String(length=512), nullable=True),
        sa.Column("error_file_key", sa.String(length=512), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_import_jobs_kind", "import_jobs", ["kind"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])
    op.create_index("ix_import_jobs_created_by_id", "import_jobs", ["created_by_id"])
    op.create_index("ix_import_jobs_group_id", "import_jobs", ["group_id"])
    op.create_index("ix_import_jobs_created_at", "import_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("import_jobs")
    op.execute("DROP TYPE importjobstatus")
