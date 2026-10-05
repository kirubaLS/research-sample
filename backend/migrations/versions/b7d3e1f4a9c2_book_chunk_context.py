"""book_chunk.context: a model-written sentence situating each passage in its chapter.

Additive only: one nullable column, no default, no backfill. Every reader treats NULL as
"no context written yet" and falls back to the chapter title and the chunk's reference.

Revision ID: b7d3e1f4a9c2
Revises: f3a9c6d2b8e1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b7d3e1f4a9c2"
down_revision: str | None = "f3a9c6d2b8e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("book_chunk", sa.Column("context", sa.String(length=400), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("book_chunk") as batch:
        batch.drop_column("context")
