"""Distinguish a class mark-entry sheet from one student's own answer script -- both are
read by the same vision-backed background job, but with a different prompt and a
different expectation for how many rows come back.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "e5a9c2d4f7b8"
down_revision: str | None = "d4f7b1c9a3e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grid_sheet_job",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="class_photo"),
    )


def downgrade() -> None:
    op.drop_column("grid_sheet_job", "kind")
