"""concept_family_proposal: drop the updated_at column that no model has

Revision ID: d4b9e2c15a37
Revises: c82d5a17f3be

c82d5a17f3be declared updated_at NOT NULL. TimestampMixin carries only created_at, so
SQLAlchemy never sent the column and every insert failed against Postgres with a
NotNullViolation -- after the model calls had been paid for.

It passed the test suite because the tests build their schema with
Base.metadata.create_all() from the models, where the column simply does not exist, while
production builds it from these migrations. The two had drifted and nothing compared them.
test_migrations_match_the_models now does, which is the fix that matters; this revision
only clears up the damage.

Immutability holds: c82d5a17f3be has been applied to production and is not edited.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d4b9e2c15a37"
down_revision: str | None = "c82d5a17f3be"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("concept_family_proposal", "updated_at")


def downgrade() -> None:
    op.add_column(
        "concept_family_proposal",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
