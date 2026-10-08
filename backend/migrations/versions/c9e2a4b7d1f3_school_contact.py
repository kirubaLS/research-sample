"""school.contact_phone and school.contact_email: the school office's contact.

Additive only: two nullable columns, no default, no backfill. Every reader treats NULL as
"not recorded", which is what every school onboarded before this revision has.

Revision ID: c9e2a4b7d1f3
Revises: b7d3e1f4a9c2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c9e2a4b7d1f3"
down_revision: str | None = "b7d3e1f4a9c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("school", sa.Column("contact_phone", sa.String(length=20), nullable=True))
    op.add_column("school", sa.Column("contact_email", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("school") as batch:
        batch.drop_column("contact_email")
        batch.drop_column("contact_phone")
