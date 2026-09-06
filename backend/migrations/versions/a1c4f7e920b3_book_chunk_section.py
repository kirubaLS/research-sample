"""Keep the section a book chunk came from.

The ingest already works out which section every chunk belongs to -- '12.2' -- and then
dropped it at the database boundary, storing every chunk against its chapter. So retrieval
could only ever answer "which chapter", the section was always unknown, and a question
could not be given a topic or matched to the concept family that claims that section.
Every question in a chapter with more than one family was blocked on a choice nothing had
the information to make.

Backfilled where the reference says it outright, so a book already loaded does not have to
be re-ingested to get its topics: 'Section 13.2' and 'EXERCISE 13.1' both name one. A
chunk whose reference does not name a section is left null rather than guessed at.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "a1c4f7e920b3"
down_revision: str | None = "d5f81ac26b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "book_chunk", sa.Column("section_number", sa.String(length=16), nullable=True)
    )
    op.execute(
        """
        UPDATE book_chunk
           SET section_number = substr(
                 reference,
                 CASE
                   WHEN reference LIKE 'Section %' THEN 9
                   WHEN reference LIKE 'EXERCISE %' THEN 10
                   WHEN reference LIKE 'Exercise %' THEN 10
                   WHEN reference LIKE 'Ex %' THEN 4
                 END
               )
         WHERE section_number IS NULL
           AND (reference LIKE 'Section _%._%'
                OR reference LIKE 'EXERCISE _%._%'
                OR reference LIKE 'Exercise _%._%'
                OR reference LIKE 'Ex _%._%')
        """
    )


def downgrade() -> None:
    op.drop_column("book_chunk", "section_number")
