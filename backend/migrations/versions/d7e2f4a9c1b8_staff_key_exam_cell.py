"""staff_key.exam_cell

Adds the flag that tells the exam cell (papers-and-marks rights across every subject in
a school, no teaching duty of their own) apart from a regular subject teacher. Before
this, whoami's only signal for "exam-cell only" was "holds zero TeacherAssignment rows,
but has scan/enter rights" -- a condition that can never actually hold, since scan/enter
rights themselves are only granted by holding a subject assignment (see
app.api.deps.teacher_subject_codes). This column replaces that unreachable inference
with a real, operator-set fact.

Additive, defaulted false -- no existing key's behaviour changes.

Revision ID: d7e2f4a9c1b8
Revises: c4d8e91a5f36
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d7e2f4a9c1b8"
down_revision: str | None = "c4d8e91a5f36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff_key",
        sa.Column("exam_cell", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("staff_key", "exam_cell")
