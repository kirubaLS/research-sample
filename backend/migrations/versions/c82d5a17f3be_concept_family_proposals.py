"""concept_family_proposal: keep what was proposed, applied or not

Revision ID: c82d5a17f3be
Revises: a3c71f2e8b04

Reading both books to propose families costs about a dollar and takes one pass. Storing
the answer costs nothing, and three things later depend on it: the route can refuse to
re-run, an applied family stays explicable years later, and the proposals a person
rejected are the only evidence of whether the model's reading was worth paying for.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c82d5a17f3be"
down_revision: str | None = "a3c71f2e8b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept_family_proposal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("curriculum_version", sa.String(32), nullable=False),
        sa.Column("subject_code", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="llm"),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("chapter_id", sa.String(36), sa.ForeignKey("taxonomy_node.id"), nullable=True),
        sa.Column("rationale", sa.String(2000), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("from_sections", sa.JSON(), nullable=True),
        sa.Column("applied_at", sa.String(40), nullable=True),
        sa.UniqueConstraint(
            "curriculum_version", "subject_code", "run_id", "code",
            name="uq_family_proposal",
        ),
    )
    for column in ("curriculum_version", "subject_code", "run_id", "source", "code", "chapter_id"):
        op.create_index(f"ix_concept_family_proposal_{column}", "concept_family_proposal", [column])


def downgrade() -> None:
    op.drop_table("concept_family_proposal")
