"""Real storage for the /attend/onboarding 6-step wizard

Revision ID: 9f27ac6081e4
Revises: d7e2f4a9c1b8

The onboarding wizard replaces the 36-item Likert RIASEC instrument as the thing a
student fills in at /attend/onboarding, but the instrument itself (TestSession,
ItemResponse, ScaleScore, ProfileResult) is untouched and stays independently callable --
this migration only adds columns to student_profile for the wizard's own answers, all
nullable so a profile created before this migration, or one that skips a step, is still a
valid row.

interests, group_reason, careers_known and future_concern are stored as JSON lists
(multi-select, capped at the API layer, not the schema layer, the same way
declared/skills lists are handled elsewhere in this codebase).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "9f27ac6081e4"
down_revision: str | None = "d7e2f4a9c1b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("student_profile", sa.Column("board", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("lives_in", sa.String(16), nullable=True))
    op.add_column("student_profile", sa.Column("decision_helper", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("responsibilities", sa.String(16), nullable=True))
    op.add_column("student_profile", sa.Column("subject_enjoy", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("subject_comfortable", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("learning_type", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("interests", sa.JSON(), nullable=True))
    op.add_column("student_profile", sa.Column("work_interest", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("new_learning_style", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("future_career", sa.String(400), nullable=True))
    op.add_column("student_profile", sa.Column("class11_group", sa.String(32), nullable=True))
    op.add_column("student_profile", sa.Column("group_reason", sa.JSON(), nullable=True))
    op.add_column("student_profile", sa.Column("confidence", sa.Integer(), nullable=True))
    op.add_column("student_profile", sa.Column("careers_known", sa.JSON(), nullable=True))
    op.add_column("student_profile", sa.Column("future_concern", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("student_profile", "future_concern")
    op.drop_column("student_profile", "careers_known")
    op.drop_column("student_profile", "confidence")
    op.drop_column("student_profile", "group_reason")
    op.drop_column("student_profile", "class11_group")
    op.drop_column("student_profile", "future_career")
    op.drop_column("student_profile", "new_learning_style")
    op.drop_column("student_profile", "work_interest")
    op.drop_column("student_profile", "interests")
    op.drop_column("student_profile", "learning_type")
    op.drop_column("student_profile", "subject_comfortable")
    op.drop_column("student_profile", "subject_enjoy")
    op.drop_column("student_profile", "responsibilities")
    op.drop_column("student_profile", "decision_helper")
    op.drop_column("student_profile", "lives_in")
    op.drop_column("student_profile", "board")
