"""book_source: the chapter-title oracle, for books that publish no section list

Revision ID: a3c71f2e8b04
Revises: 17fdea04c379

The Science contents page stops at chapter titles, so expected_sections is empty for it
and a chapter upload had nothing to be checked against. This column holds what that page
does publish.

Defaulted server-side as well as in the model: existing Maths rows must come back as an
empty mapping, not NULL, or every read of them has to special-case a column that was
added later.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a3c71f2e8b04"
down_revision: str | None = "17fdea04c379"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "book_source",
        sa.Column("expected_chapters", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("book_source", "expected_chapters")
