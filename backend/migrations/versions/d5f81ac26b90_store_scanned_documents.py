"""store scanned documents and issued reports

A mark on a report is a claim about a piece of paper. The pages were read and thrown
away, so the claim could not be checked and a principal could not answer "show me his
answer sheet". They are kept now, joined to the assessment and, for a script, the student.

Revision ID: d5f81ac26b90
Revises: c93a51fb2e77
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d5f81ac26b90"
down_revision: str | None = "c93a51fb2e77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_document",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessment.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("student_profile.id"), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.String(120), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(120), nullable=True),
    )
    op.create_index("ix_scan_document_school_id", "scan_document", ["school_id"])
    op.create_index("ix_scan_document_assessment_id", "scan_document", ["assessment_id"])
    op.create_index("ix_scan_document_student_id", "scan_document", ["student_id"])
    op.create_index("ix_scan_document_sha256", "scan_document", ["sha256"])

    op.create_table(
        "scan_page",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "document_id", sa.String(36),
            sa.ForeignKey("scan_document.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.UniqueConstraint("document_id", "index", name="uq_scan_page"),
    )
    op.create_index("ix_scan_page_document_id", "scan_page", ["document_id"])

    op.create_table(
        "student_report",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessment.id"), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("student_profile.id"), nullable=False),
        sa.Column("issued_by", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("earned", sa.Numeric(7, 2), nullable=False),
        sa.Column("available", sa.Numeric(7, 2), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for column in ("school_id", "assessment_id", "student_id", "sha256"):
        op.create_index(f"ix_student_report_{column}", "student_report", [column])


def downgrade() -> None:
    for column in ("sha256", "student_id", "assessment_id", "school_id"):
        op.drop_index(f"ix_student_report_{column}", table_name="student_report")
    op.drop_table("student_report")
    op.drop_index("ix_scan_page_document_id", table_name="scan_page")
    op.drop_table("scan_page")
    for name in ("sha256", "student_id", "assessment_id", "school_id"):
        op.drop_index(f"ix_scan_document_{name}", table_name="scan_document")
    op.drop_table("scan_document")
