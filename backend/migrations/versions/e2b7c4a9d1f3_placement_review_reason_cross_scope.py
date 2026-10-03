"""question_placement: curriculum_section_fine, review_reason, cross_scope.

Additive only: three nullable columns, no default, no backfill. Rows written before this
revision read NULL in all three, which every reader treats as "not recorded".

Revision ID: e2b7c4a9d1f3
Revises: c4e8a1f7b2d9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e2b7c4a9d1f3"
down_revision: str | None = "c4e8a1f7b2d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "question_placement",
        sa.Column("curriculum_section_fine", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "question_placement",
        sa.Column("review_reason", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "question_placement",
        sa.Column("cross_scope", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("question_placement") as batch:
        batch.drop_column("cross_scope")
        batch.drop_column("review_reason")
        batch.drop_column("curriculum_section_fine")
