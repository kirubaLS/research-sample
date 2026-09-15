"""Board papers as a kind of assessment, and the per-family board-frequency table

Revision ID: 24330d3cbda2
Revises: a4c8e21f9b6d

A real CBSE board paper goes through the same scan, confirm and map route as a school
test, because that route already does the work the frequency layer needs: it extracts
every question with its marks and tags each one with a concept family. What was missing
was a way to say "this paper is the 2024 board exam, not a unit test" -- hence paper_kind
and exam_year on assessment.

family_board_frequency is the materialised result: per family, how many of the last N
board years it appeared in, for how many marks, and the multiplier that follows. Stored
with its evidence so the number can be explained, and rebuilt whenever a board paper is
mapped so it is never staler than the last paper.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "24330d3cbda2"
down_revision: str | None = "a4c8e21f9b6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment",
        sa.Column("paper_kind", sa.String(16), nullable=False, server_default="school"),
    )
    op.add_column("assessment", sa.Column("exam_year", sa.Integer(), nullable=True))
    op.create_index("ix_assessment_paper_kind", "assessment", ["paper_kind"])
    op.create_index("ix_assessment_exam_year", "assessment", ["exam_year"])

    op.create_table(
        "family_board_frequency",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("curriculum_version", sa.String(32), nullable=False),
        sa.Column("subject_code", sa.String(32), nullable=False),
        sa.Column("concept_family_id", sa.String(36), sa.ForeignKey("taxonomy_node.id"), nullable=False),
        sa.Column("window_years", sa.JSON(), nullable=False),
        sa.Column("years_eligible", sa.Integer(), nullable=False),
        sa.Column("years_appeared", sa.Integer(), nullable=False),
        sa.Column("marks_by_year", sa.JSON(), nullable=False),
        sa.Column("marks_range", sa.Float(), nullable=True),
        sa.Column("base_multiplier", sa.Float(), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=False),
        sa.Column("adjustments", sa.JSON(), nullable=False),
        sa.Column("papers_used", sa.Integer(), nullable=False),
        sa.Column("config_version", sa.String(16), nullable=False),
        sa.Column("computed_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "curriculum_version", "concept_family_id", name="uq_family_board_frequency"
        ),
    )
    op.create_index(
        "ix_family_board_frequency_curriculum_version", "family_board_frequency", ["curriculum_version"]
    )
    op.create_index(
        "ix_family_board_frequency_subject_code", "family_board_frequency", ["subject_code"]
    )
    op.create_index(
        "ix_family_board_frequency_concept_family_id", "family_board_frequency", ["concept_family_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_family_board_frequency_concept_family_id", table_name="family_board_frequency")
    op.drop_index("ix_family_board_frequency_subject_code", table_name="family_board_frequency")
    op.drop_index("ix_family_board_frequency_curriculum_version", table_name="family_board_frequency")
    op.drop_table("family_board_frequency")
    op.drop_index("ix_assessment_exam_year", table_name="assessment")
    op.drop_index("ix_assessment_paper_kind", table_name="assessment")
    op.drop_column("assessment", "exam_year")
    op.drop_column("assessment", "paper_kind")
