"""exam, and assessment.exam_id

Adds the exam day as a real record: a name and a scheduled date a principal or admin
entered ("Unit Test 2", "Quarterly Exam"), which may exist before any paper does so an
upcoming exam can be scheduled ahead of time. Each subject's paper stays its own
Assessment row; the new nullable assessment.exam_id only groups papers under one exam.

Additive -- every existing paper keeps exam_id null and behaves exactly as before.

Revision ID: b3e9c5a17d42
Revises: 9f27ac6081e4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b3e9c5a17d42"
down_revision: str | None = "9f27ac6081e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("school_id", sa.String(36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_exam_school_id", "exam", ["school_id"])
    op.create_index("ix_exam_scheduled_date", "exam", ["scheduled_date"])
    # batch_alter_table so SQLite (the test suite's database) can add the foreign key
    with op.batch_alter_table("assessment") as batch:
        batch.add_column(sa.Column("exam_id", sa.String(36), nullable=True))
        batch.create_index("ix_assessment_exam_id", ["exam_id"])
        batch.create_foreign_key("fk_assessment_exam", "exam", ["exam_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("assessment") as batch:
        batch.drop_constraint("fk_assessment_exam", type_="foreignkey")
        batch.drop_index("ix_assessment_exam_id")
        batch.drop_column("exam_id")
    op.drop_index("ix_exam_scheduled_date", table_name="exam")
    op.drop_index("ix_exam_school_id", table_name="exam")
    op.drop_table("exam")
