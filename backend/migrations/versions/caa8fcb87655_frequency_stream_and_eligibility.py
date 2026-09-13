"""Board frequency per stream, older syllabus versions, and eligibility provenance

Revision ID: caa8fcb87655
Revises: 24330d3cbda2

Maths is two board exams on one syllabus (Standard, Basic) and their sets must not be
pooled, so the frequency row is keyed by stream as well. Eligibility now reads which
curriculum version carried the family, and the row records per year whether that came
from a seeded syllabus, the node's dates, the family having appeared, or an assumption.
Sets of one year that disagree on whether a family appeared are recorded for a reviewer.

syllabus_version records what an older syllabus did NOT contain, one row per revision and
subject, rather than copying the taxonomy tree under a second version: the mapping path
finds nodes by code alone, and two nodes per code would place questions at random.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "caa8fcb87655"
down_revision: str | None = "24330d3cbda2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("family_board_frequency") as batch:
        batch.add_column(
            sa.Column("stream", sa.String(16), nullable=False, server_default="standard")
        )
        batch.add_column(sa.Column("eligibility", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("sets_disagree", sa.JSON(), nullable=True))
        batch.drop_constraint("uq_family_board_frequency", type_="unique")
        batch.create_unique_constraint(
            "uq_family_board_frequency", ["curriculum_version", "stream", "concept_family_id"]
        )
    op.create_index("ix_family_board_frequency_stream", "family_board_frequency", ["stream"])

    op.create_table(
        "syllabus_version",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("curriculum_version", sa.String(32), nullable=False),
        sa.Column("subject_code", sa.String(32), nullable=False),
        sa.Column("excluded_families", sa.JSON(), nullable=False),
        sa.Column("source_doc_url", sa.String(500), nullable=True),
        sa.Column("seeded_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("curriculum_version", "subject_code", name="uq_syllabus_version"),
    )
    op.create_index("ix_syllabus_version_curriculum_version", "syllabus_version", ["curriculum_version"])
    op.create_index("ix_syllabus_version_subject_code", "syllabus_version", ["subject_code"])


def downgrade() -> None:
    op.drop_index("ix_syllabus_version_subject_code", table_name="syllabus_version")
    op.drop_index("ix_syllabus_version_curriculum_version", table_name="syllabus_version")
    op.drop_table("syllabus_version")
    op.drop_index("ix_family_board_frequency_stream", table_name="family_board_frequency")
    with op.batch_alter_table("family_board_frequency") as batch:
        batch.drop_constraint("uq_family_board_frequency", type_="unique")
        batch.create_unique_constraint(
            "uq_family_board_frequency", ["curriculum_version", "concept_family_id"]
        )
        batch.drop_column("sets_disagree")
        batch.drop_column("eligibility")
        batch.drop_column("stream")
