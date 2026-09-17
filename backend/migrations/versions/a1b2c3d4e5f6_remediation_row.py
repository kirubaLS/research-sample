"""remediation row

The approved-practice-text catalogue the BoardX student report composer resolves
"what to practise next" against (see app/analysis/boardx_report.py and
app/models/remediation.py). Purely additive.

Revision ID: a1b2c3d4e5f6
Revises: c1a9f4e73b02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c1a9f4e73b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remediation_row",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("remediation_ref", sa.String(80), nullable=False),
        sa.Column("subject_code", sa.String(32), nullable=False),
        sa.Column("domain_code", sa.String(80), nullable=False),
        sa.Column("finding_type", sa.String(80), nullable=False),
        sa.Column("student_action_text", sa.Text, nullable=False),
        sa.Column("approved", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(120), nullable=False, server_default=""),
        sa.UniqueConstraint("remediation_ref", name="uq_remediation_ref"),
    )
    op.create_index("ix_remediation_row_subject_code", "remediation_row", ["subject_code"])
    op.create_index("ix_remediation_row_domain_code", "remediation_row", ["domain_code"])
    op.create_index("ix_remediation_row_finding_type", "remediation_row", ["finding_type"])
    op.create_index("ix_remediation_row_approved", "remediation_row", ["approved"])
    op.create_index("ix_remediation_row_remediation_ref", "remediation_row", ["remediation_ref"])


def downgrade() -> None:
    op.drop_index("ix_remediation_row_remediation_ref", table_name="remediation_row")
    op.drop_index("ix_remediation_row_approved", table_name="remediation_row")
    op.drop_index("ix_remediation_row_finding_type", table_name="remediation_row")
    op.drop_index("ix_remediation_row_domain_code", table_name="remediation_row")
    op.drop_index("ix_remediation_row_subject_code", table_name="remediation_row")
    op.drop_table("remediation_row")
