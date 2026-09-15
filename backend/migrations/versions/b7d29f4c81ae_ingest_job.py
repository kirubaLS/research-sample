"""A book upload that has to finish outside the request that started it.

A Hindi chapter's real text has to come from Gemini -- tens of seconds, one blocking call
-- and Render's own reverse proxy kills a web request at a fixed timeout regardless of
what the app is doing. The synchronous upload endpoint every other subject uses returned
to the browser as a bare connection failure on a request that reached the backend fine.

ingest_job is what the upload endpoint writes and returns a 202 for instead of blocking:
the actual work runs in a background task and the browser polls GET .../jobs/{id}, the
same way the synchronous endpoints' own response used to arrive directly. pdf_bytes is a
column, not a path, because a Render instance keeps no disk between requests.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "b7d29f4c81ae"
down_revision: str | None = "a1c4f7e920b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingest_job",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject_code", sa.String(length=32), nullable=False),
        sa.Column("curriculum_version", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("edition", sa.String(length=120), nullable=True),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_status", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingest_job_subject_code", "ingest_job", ["subject_code"])
    op.create_index("ix_ingest_job_status", "ingest_job", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ingest_job_status", table_name="ingest_job")
    op.drop_index("ix_ingest_job_subject_code", table_name="ingest_job")
    op.drop_table("ingest_job")
