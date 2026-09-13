"""A person confirms the extraction before anything downstream treats it as fact

Revision ID: f6c2b81a30e5
Revises: e7a3f81c94d2

Mapping, marks and every report after them treat the extracted questions as what the paper
says. An extraction nobody checked is not that -- it is a good guess that became a mark on
a child's report without anyone looking. So the confirmation is recorded, and mapping
refuses without it.

Per-row edited_at/edited_by because a corrected row and a row the machine got right are
different evidence about how well the extractor works.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f6c2b81a30e5"
down_revision: str | None = "e7a3f81c94d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assessment", sa.Column("scan_confirmed_at", sa.String(40), nullable=True))
    op.add_column("assessment", sa.Column("scan_confirmed_by", sa.String(64), nullable=True))
    op.add_column("scanned_question", sa.Column("edited_at", sa.String(40), nullable=True))
    op.add_column("scanned_question", sa.Column("edited_by", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("scanned_question", "edited_by")
    op.drop_column("scanned_question", "edited_at")
    op.drop_column("assessment", "scan_confirmed_by")
    op.drop_column("assessment", "scan_confirmed_at")
