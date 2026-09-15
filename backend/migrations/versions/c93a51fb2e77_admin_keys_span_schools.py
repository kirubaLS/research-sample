"""admin keys span schools

An admin creates schools and works across all of them, so an admin key names none. A
principal key names exactly one, and that is the only school it can ever resolve to.

Revision ID: c93a51fb2e77
Revises: b1d47e93c60a
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c93a51fb2e77"
down_revision: str | None = "b1d47e93c60a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch mode: SQLite cannot alter a column in place, and the dev database is SQLite
    with op.batch_alter_table("staff_key") as batch:
        batch.alter_column("school_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    # Not reversible without a decision: an admin key has no school to put back. Rows
    # without one are dropped rather than invented a home for.
    op.execute("DELETE FROM staff_key WHERE school_id IS NULL")
    with op.batch_alter_table("staff_key") as batch:
        batch.alter_column("school_id", existing_type=sa.String(36), nullable=False)
