"""scanned_question/question: attempt_required, for 'attempt any N of the following M'

Revision ID: c1a9f4e73b02
Revises: b6e21f7a9c34

A paper's internal-choice gap so far was only the binary OR shape (see choice.py:
ChoiceGroup, "attempt (a) OR (b)"). A separate, equally common shape prints a numbered
list of M sub-items with an instruction naming a required count N < M, and states the
group's per-item mark once as a printed 'N x M = Total' expression rather than bracketed
per item -- no OR marker, no choice_alt pairing, so the existing grouping had nothing to
key on and every sub-item's mark was counted as if all M had been attempted.

``attempt_required`` carries N for a row that is one member of such a group (null
otherwise); the group itself is the set of rows sharing (assessment, section,
question_no) with this column set. See app.extraction.choice.group_choices.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c1a9f4e73b02"
down_revision: str | None = "b6e21f7a9c34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scanned_question", sa.Column("attempt_required", sa.Integer(), nullable=True)
    )
    op.add_column(
        "question", sa.Column("attempt_required", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("question", "attempt_required")
    op.drop_column("scanned_question", "attempt_required")
