"""Add progress_done/progress_total to the three background job tables

Revision ID: f3a91c7b8e42
Revises: c2e6a94d1f70

PaperScanJob, GridSheetJob and PlacementJob each only ever carried a status column
(pending/running/succeeded/failed) -- no real incremental progress, so a browser polling
one of these jobs had nothing honest to show beyond a generic "still working" spinner for
however long the job actually took. These two columns let each job's own run loop commit
real progress as it goes (pages read, questions classified) so the frontend can show
"page 3 of 8" / "classified 12 of 40" instead.

Both columns are nullable on all three tables, and stay nullable: null means "not tracked
yet" (an old job written before this migration, or one that failed before its first unit
of work committed), never "0 of 0" -- a job showing 0/0 would read as already done.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f3a91c7b8e42"
down_revision: str | None = "c2e6a94d1f70"
branch_labels = None
depends_on = None

_TABLES = ("paper_scan_job", "grid_sheet_job", "placement_job")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("progress_done", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("progress_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("progress_total")
            batch.drop_column("progress_done")
