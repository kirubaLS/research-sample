"""A grid-sheet row keeps the sheet's own printed total, separate from any question

Revision ID: a1c4d8e5f963
Revises: b3e9c5a17d42

The vision reader is already instructed to read a sheet's own printed TOTAL column
alongside every question cell, but nothing kept what it read: match_address had no real
question address for a label like 'TOTAL' to resolve against, so the cell was silently
dropped in _write_proposed_marks's `if question is None: continue`. It is not a mark
against any question -- it is the sheet's own claim about the row's grand total, kept
here as its own field so a teacher can cross-check it against the sum of what was
actually read, in the same live marks-entry grid.

Nullable and not on the closed ProposedMark/MarkEvent vocabulary: most sheets do not
print a totals column at all, and this is never itself a scoreable question.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4d8e5f963"
down_revision: str | None = "b3e9c5a17d42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grid_sheet_row") as batch:
        batch.add_column(sa.Column("sheet_total", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("grid_sheet_row") as batch:
        batch.drop_column("sheet_total")
