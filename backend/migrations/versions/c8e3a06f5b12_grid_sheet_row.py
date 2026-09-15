"""A class mark-entry sheet: one photograph, many students.

A school that marks by hand often keeps one sheet per section rather than one script per
student -- rows are students, columns are questions. grid_sheet_row holds one student's
row as it was read, before it is resolved to a real student and turned into ordinary
ProposedMark rows: a roll the roster does not recognise, or a name that does not quite
match it, is a reason to ask a person once rather than to lose the marks next to it or to
guess.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "c8e3a06f5b12"
down_revision: str | None = "b7d29f4c81ae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grid_sheet_row",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(length=36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), sa.ForeignKey("assessment.id"), nullable=False),
        sa.Column("section_id", sa.String(length=36), sa.ForeignKey("section.id"), nullable=False),
        sa.Column(
            "document_id", sa.String(length=36),
            sa.ForeignKey("scan_document.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("roll_no", sa.String(length=16), nullable=False),
        sa.Column("name_as_written", sa.String(length=200), nullable=False, server_default=""),
        sa.Column(
            "student_id", sa.String(length=36),
            sa.ForeignKey("student_profile.id"), nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unmatched"),
        sa.Column("cells", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.UniqueConstraint("document_id", "roll_no", name="uq_grid_row"),
    )
    op.create_index("ix_grid_sheet_row_school_id", "grid_sheet_row", ["school_id"])
    op.create_index("ix_grid_sheet_row_assessment_id", "grid_sheet_row", ["assessment_id"])
    op.create_index("ix_grid_sheet_row_section_id", "grid_sheet_row", ["section_id"])
    op.create_index("ix_grid_sheet_row_document_id", "grid_sheet_row", ["document_id"])
    op.create_index("ix_grid_sheet_row_student_id", "grid_sheet_row", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_grid_sheet_row_student_id", table_name="grid_sheet_row")
    op.drop_index("ix_grid_sheet_row_document_id", table_name="grid_sheet_row")
    op.drop_index("ix_grid_sheet_row_section_id", table_name="grid_sheet_row")
    op.drop_index("ix_grid_sheet_row_assessment_id", table_name="grid_sheet_row")
    op.drop_index("ix_grid_sheet_row_school_id", table_name="grid_sheet_row")
    op.drop_table("grid_sheet_row")
