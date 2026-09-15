"""teacher assignment

Adds the "teacher" role (StaffKey.role already stores a free string, not a DB enum, so no
column change is needed for that) and a table naming exactly which class or subject a
teacher key may touch: TeacherAssignment. Purely additive -- no existing table or column
is touched.

Revision ID: f3a8c1d92b47
Revises: a3c7e19f4b62
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f3a8c1d92b47"
down_revision: str | None = "a3c7e19f4b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teacher_assignment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("staff_key_id", sa.String(36), sa.ForeignKey("staff_key.id"), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("section_id", sa.String(36), sa.ForeignKey("section.id"), nullable=False),
        sa.Column("subject_code", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_teacher_assignment_staff_key_id", "teacher_assignment", ["staff_key_id"]
    )
    op.create_index(
        "ix_teacher_assignment_section_id", "teacher_assignment", ["section_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_assignment_section_id", table_name="teacher_assignment")
    op.drop_index("ix_teacher_assignment_staff_key_id", table_name="teacher_assignment")
    op.drop_table("teacher_assignment")
