"""Placing a paper's questions -- retrieval, the classifier judge, and the constraint
solver, over every question on the paper -- calls the classifier once per question, around
forty calls for an ordinary paper. The sum of those calls runs past a reverse proxy's
request timeout even though every individual call succeeds, the same reason
paper_scan_job and grid_sheet_job exist. placement_job is what the place endpoint writes
and hands to a background task instead of blocking, returning 202; the browser polls for
the result the endpoint used to return directly.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "a3c7e19f4b62"
down_revision: str | None = "e730bf13932b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "placement_job",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(length=36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessment.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_status", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_placement_job_school_id", "placement_job", ["school_id"])
    op.create_index("ix_placement_job_assessment_id", "placement_job", ["assessment_id"])
    op.create_index("ix_placement_job_status", "placement_job", ["status"])


def downgrade() -> None:
    op.drop_index("ix_placement_job_status", table_name="placement_job")
    op.drop_index("ix_placement_job_assessment_id", table_name="placement_job")
    op.drop_index("ix_placement_job_school_id", table_name="placement_job")
    op.drop_table("placement_job")
