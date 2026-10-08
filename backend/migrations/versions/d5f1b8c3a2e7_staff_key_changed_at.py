"""staff_key.credential_changed_at: when the holder set their own key.

Additive only: one nullable column, no default, no backfill.

Revision ID: d5f1b8c3a2e7
Revises: c9e2a4b7d1f3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d5f1b8c3a2e7"
down_revision: str | None = "c9e2a4b7d1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("staff_key")}
    if "credential_changed_at" not in have:
        op.add_column("staff_key", sa.Column("credential_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("staff_key") as batch:
        batch.drop_column("credential_changed_at")
