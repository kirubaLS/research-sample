"""scanned_question: the paper as printed, before the curriculum is known

Revision ID: e7a3f81c94d2
Revises: d4b9e2c15a37

A separate table rather than nullable columns on question. question.board_unit_id and
concept_family_id are NOT NULL precisely because a null there drops a question out of
board-impact reporting while the report still renders. A scan cannot know either -- they
come from the book, through retrieval and the judge -- so it writes here and mapping
promotes the row once the chapter is known.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e7a3f81c94d2"
down_revision: str | None = "d4b9e2c15a37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scanned_question",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessment.id"), nullable=False),
        sa.Column("address", sa.String(40), nullable=False),
        sa.Column("section", sa.String(8), nullable=True),
        sa.Column("question_no", sa.String(12), nullable=False),
        sa.Column("sub_part", sa.String(12), nullable=True),
        sa.Column("choice_alt", sa.String(4), nullable=True),
        sa.Column("max_marks", sa.Numeric(5, 2), nullable=True),
        sa.Column("stem_text", sa.String(4000), nullable=True),
        sa.Column("logical_page", sa.Integer(), nullable=True),
        sa.Column("question_id", sa.String(36), sa.ForeignKey("question.id"), nullable=True),
        sa.Column("blocked_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("assessment_id", "address", name="uq_scanned_address"),
    )
    for column in ("assessment_id", "address", "question_id"):
        op.create_index(f"ix_scanned_question_{column}", "scanned_question", [column])


def downgrade() -> None:
    op.drop_table("scanned_question")
