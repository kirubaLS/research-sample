"""student report sharing

Real "Share with student" support: a teacher issues a one-time PIN for one issued
report (app/api/student.py), the student trades roll number + PIN for a StudentSession
token, and everything the student portal reads afterward is checked against that
report's own share state fresh on every request. Purely additive.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("student_report", sa.Column("share_pin_hash", sa.String(64), nullable=True))
    op.add_column("student_report", sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("student_report", sa.Column("shared_by", sa.String(120), nullable=True))
    op.add_column("student_report", sa.Column("share_revoked_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "student_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("student_id", sa.String(36), sa.ForeignKey("student_profile.id"), nullable=False),
        sa.Column("school_id", sa.String(36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token", name="uq_student_session_token"),
    )
    op.create_index("ix_student_session_student_id", "student_session", ["student_id"])
    op.create_index("ix_student_session_school_id", "student_session", ["school_id"])
    op.create_index("ix_student_session_token", "student_session", ["token"])


def downgrade() -> None:
    op.drop_index("ix_student_session_token", table_name="student_session")
    op.drop_index("ix_student_session_school_id", table_name="student_session")
    op.drop_index("ix_student_session_student_id", table_name="student_session")
    op.drop_table("student_session")

    op.drop_column("student_report", "share_revoked_at")
    op.drop_column("student_report", "shared_by")
    op.drop_column("student_report", "shared_at")
    op.drop_column("student_report", "share_pin_hash")
