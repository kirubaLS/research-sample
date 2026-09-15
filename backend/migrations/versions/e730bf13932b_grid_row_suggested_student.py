"""A grid-sheet row whose roll is not on the roster may carry a suggested student

Revision ID: e730bf13932b
Revises: caa8fcb87655

The roll number is the join key and the handwritten name is only a check on it. When the
roll is unknown the name is now used for the one thing it is good for: suggesting the
single roster student it fits, for a person to accept with one click. The row's own
student_id stays null until they do; this column is the suggestion, kept apart from it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e730bf13932b"
down_revision: str | None = "caa8fcb87655"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grid_sheet_row") as batch:
        batch.add_column(sa.Column("suggested_student_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_grid_sheet_row_suggested_student", "student_profile",
            ["suggested_student_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("grid_sheet_row") as batch:
        batch.drop_constraint("fk_grid_sheet_row_suggested_student", type_="foreignkey")
        batch.drop_column("suggested_student_id")
