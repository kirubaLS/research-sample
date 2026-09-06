"""staff keys and roles

A principal and an admin were the same credential. This adds a table of per-person keys
carrying a role, so a principal can be given access that reads every student's progress
without being able to scan a paper, create a class or rotate a credential.

The school's own ``api_key`` is untouched and continues to work as that school's admin
key, so no deployment loses access by this arriving.

Revision ID: b1d47e93c60a
Revises: f6c2b81a30e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b1d47e93c60a"
down_revision: str | None = "f6c2b81a30e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_key",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("api_key", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_staff_key_school_id", "staff_key", ["school_id"])
    op.create_index("ix_staff_key_api_key", "staff_key", ["api_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_staff_key_api_key", table_name="staff_key")
    op.drop_index("ix_staff_key_school_id", table_name="staff_key")
    op.drop_table("staff_key")
