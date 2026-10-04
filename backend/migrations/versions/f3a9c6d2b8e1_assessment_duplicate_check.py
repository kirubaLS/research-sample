"""assessment: source_file_hashes, class_section_id, duplicate_check.

Additive only: three nullable columns, no default, no backfill. Rows written before this
revision read NULL in all three -- no per-file hashes recorded, no class section known,
no duplicate check run -- and every reader treats NULL that way.

Revision ID: f3a9c6d2b8e1
Revises: e2b7c4a9d1f3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f3a9c6d2b8e1"
down_revision: str | None = "e2b7c4a9d1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assessment", sa.Column("source_file_hashes", sa.JSON(), nullable=True))
    with op.batch_alter_table("assessment") as batch:
        batch.add_column(sa.Column("class_section_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_assessment_class_section_id", ["class_section_id"])
        batch.create_foreign_key(
            "fk_assessment_class_section_id", "section", ["class_section_id"], ["id"],
        )
    op.add_column("assessment", sa.Column("duplicate_check", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("assessment") as batch:
        batch.drop_column("duplicate_check")
        batch.drop_constraint("fk_assessment_class_section_id", type_="foreignkey")
        batch.drop_index("ix_assessment_class_section_id")
        batch.drop_column("class_section_id")
        batch.drop_column("source_file_hashes")
