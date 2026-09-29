"""placement_job.kind: the same job table now also carries the map step.

Revision ID: c4e8a1f7b2d9
Revises: a7d3f19b4c62
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a1f7b2d9"
down_revision: str | None = "a7d3f19b4c62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "placement_job",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="place"),
    )


def downgrade() -> None:
    op.drop_column("placement_job", "kind")
