"""Reading a scanned or photographed question paper calls the Anthropic vision API and
can run past Render's request timeout, the same reason ingest_job and grid_sheet_job
exist. paper_scan_job is what the scan endpoint writes and hands to a background task
instead of blocking, returning 202; the browser polls for the result the endpoint used to
return directly.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "f1b3e7a9c2d5"
down_revision: str | None = "e5a9c2d4f7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_scan_job",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(length=36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessment.id"), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_status", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_paper_scan_job_school_id", "paper_scan_job", ["school_id"])
    op.create_index("ix_paper_scan_job_assessment_id", "paper_scan_job", ["assessment_id"])
    op.create_index("ix_paper_scan_job_status", "paper_scan_job", ["status"])


def downgrade() -> None:
    op.drop_index("ix_paper_scan_job_status", table_name="paper_scan_job")
    op.drop_index("ix_paper_scan_job_assessment_id", table_name="paper_scan_job")
    op.drop_index("ix_paper_scan_job_school_id", table_name="paper_scan_job")
    op.drop_table("paper_scan_job")
