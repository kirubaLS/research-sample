"""Widen skill_required to match Classification's real max_length

Revision ID: c2e6a94d1f70
Revises: a1c4d8e5f963

Classification.skill_required (app.classify.judge) was raised from max_length=200 to 400
earlier this session -- the judge's own instructions invite a full descriptive phrase, not
a short label. Nobody widened the matching columns, so a legitimately longer, valid answer
now passes Pydantic validation and then fails at the database write with
StringDataRightTruncation. question.skill_required and question_placement.skill_required
are the two columns Classification's value is actually written into;
question_judgment.value is widened alongside them since it holds the same field's value in
the Layer 2B human review trail.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c2e6a94d1f70"
down_revision: str | None = "a1c4d8e5f963"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("question") as batch:
        batch.alter_column(
            "skill_required", existing_type=sa.String(200), type_=sa.String(400)
        )
    with op.batch_alter_table("question_placement") as batch:
        batch.alter_column(
            "skill_required", existing_type=sa.String(200), type_=sa.String(400)
        )
    with op.batch_alter_table("question_judgment") as batch:
        batch.alter_column("value", existing_type=sa.String(200), type_=sa.String(400))


def downgrade() -> None:
    with op.batch_alter_table("question_judgment") as batch:
        batch.alter_column("value", existing_type=sa.String(400), type_=sa.String(200))
    with op.batch_alter_table("question_placement") as batch:
        batch.alter_column(
            "skill_required", existing_type=sa.String(400), type_=sa.String(200)
        )
    with op.batch_alter_table("question") as batch:
        batch.alter_column(
            "skill_required", existing_type=sa.String(400), type_=sa.String(200)
        )
