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
    # Safe to re-run: a column that is already there (a database touched by hand or by an
    # earlier partial run) is left alone.
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("school")}
    if "contact_phone" not in have:
        op.add_column("school", sa.Column("contact_phone", sa.String(length=20), nullable=True))
    if "contact_email" not in have:
        op.add_column("school", sa.Column("contact_email", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("school") as batch:
        batch.drop_column("contact_email")
        batch.drop_column("contact_phone")
