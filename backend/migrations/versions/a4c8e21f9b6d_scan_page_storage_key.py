"""A page's bytes move to object storage (see app/storage.py and app/models/documents.py's
own docstring) instead of living in this database -- the AWS move puts them in an S3
bucket with a 30-day lifecycle rule, so a raw scan auto-expires while the extracted marks
and questions it produced stay in Postgres permanently. storage_key is where a page's
bytes live now; content stays nullable so a row written before this migration keeps
serving without a backfill.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "a4c8e21f9b6d"
down_revision: str | None = "f1b3e7a9c2d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table, not a bare op.*: SQLite (what this repo's own test suite runs
    # migrations against) has no ALTER COLUMN at all -- batch mode is what rebuilds the
    # table under the hood on SQLite while emitting a plain ALTER on Postgres.
    with op.batch_alter_table("scan_page", schema=None) as batch_op:
        batch_op.add_column(sa.Column("storage_key", sa.String(length=255), nullable=True))
        batch_op.alter_column("content", existing_type=sa.LargeBinary(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("scan_page", schema=None) as batch_op:
        batch_op.alter_column("content", existing_type=sa.LargeBinary(), nullable=False)
        batch_op.drop_column("storage_key")
