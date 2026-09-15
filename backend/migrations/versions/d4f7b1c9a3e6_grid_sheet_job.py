"""Reading a class mark-entry sheet cannot finish inside one HTTP request -- it calls the
Anthropic vision API, and Render's own reverse proxy kills a web request at a fixed
timeout regardless of what the app is doing (see ingest_job, added for the identical
reason on a Hindi book upload). grid_sheet_job is what the upload endpoint writes and
hands to a background task instead of blocking, returning 202; the browser polls
GET .../gridsheet/jobs/{id} for the result the endpoint used to return directly.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "d4f7b1c9a3e6"
down_revision: str | None = "c8e3a06f5b12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grid_sheet_job",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(length=36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessment.id"), nullable=False),
        sa.Column("section_id", sa.String(length=36), sa.ForeignKey("section.id"), nullable=False),
        sa.Column(
            "document_id", sa.String(length=36),
            sa.ForeignKey("scan_document.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_status", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_grid_sheet_job_school_id", "grid_sheet_job", ["school_id"])
    op.create_index("ix_grid_sheet_job_assessment_id", "grid_sheet_job", ["assessment_id"])
    op.create_index("ix_grid_sheet_job_status", "grid_sheet_job", ["status"])


def downgrade() -> None:
    op.drop_index("ix_grid_sheet_job_status", table_name="grid_sheet_job")
    op.drop_index("ix_grid_sheet_job_assessment_id", table_name="grid_sheet_job")
    op.drop_index("ix_grid_sheet_job_school_id", table_name="grid_sheet_job")
    op.drop_table("grid_sheet_job")
