"""pages to the object store

Page bytes were columns in Postgres, which was right for one school and stops being right
quickly: a term of scripts is gigabytes, and every backup, restore and replica carries
them. Pages now live in the object store and the row keeps only where.

``content`` stays and becomes nullable rather than being backfilled and dropped. Rewriting
a school's stored scripts to move them is a worse risk than reading two places, and a page
already written is already correct.

Revision ID: e4a70cd91b58
Revises: d5f81ac26b90
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e4a70cd91b58"
down_revision: str | None = "d5f81ac26b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scan_page", sa.Column("storage_key", sa.String(400), nullable=True))
    op.add_column("scan_page", sa.Column("storage_uri", sa.String(600), nullable=True))
    op.add_column("scan_page", sa.Column("sha256", sa.String(64), nullable=True))
    with op.batch_alter_table("scan_page") as batch:
        batch.alter_column("content", existing_type=sa.LargeBinary(), nullable=True)


def downgrade() -> None:
    # Not reversible in fact: the bytes are in the object store, and a page whose content
    # column is null cannot be made NOT NULL again without fetching every one back. The
    # rows are left alone and only the columns go.
    op.drop_column("scan_page", "sha256")
    op.drop_column("scan_page", "storage_uri")
    op.drop_column("scan_page", "storage_key")
