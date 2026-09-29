"""Add whatsapp_send: tracks a real Meta WhatsApp Cloud API send of an issued report

Revision ID: a7d3f19b4c62
Revises: f3a91c7b8e42

One row per attempt to put an issued report's PDF into a parent's WhatsApp via Meta's
Cloud API (direct, no BSP -- app.integrations.whatsapp.WhatsAppClient). Same durable-job-
row shape as GridSheetJob/PaperScanJob/PlacementJob: a background task does the slow
external network call (upload the PDF to Meta, send the template message), the row
records the real outcome, and the frontend polls it.

parent_whatsapp is captured at send time, not read live off StudentProfile, so a later
correction to the number on file cannot retroactively change what a historical send row
claims was messaged. meta_message_id is Meta's own id for the sent message -- the key a
delivery/read-status webhook later correlates back to this row.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3f19b4c62"
down_revision: str | None = "f3a91c7b8e42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_send",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(length=36), sa.ForeignKey("school.id"), nullable=False),
        sa.Column("report_id", sa.String(length=36), sa.ForeignKey("student_report.id"), nullable=False),
        sa.Column("parent_whatsapp", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("meta_message_id", sa.String(length=128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_whatsapp_send_school_id", "whatsapp_send", ["school_id"])
    op.create_index("ix_whatsapp_send_report_id", "whatsapp_send", ["report_id"])
    op.create_index("ix_whatsapp_send_status", "whatsapp_send", ["status"])
    op.create_index("ix_whatsapp_send_meta_message_id", "whatsapp_send", ["meta_message_id"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_send_meta_message_id", table_name="whatsapp_send")
    op.drop_index("ix_whatsapp_send_status", table_name="whatsapp_send")
    op.drop_index("ix_whatsapp_send_report_id", table_name="whatsapp_send")
    op.drop_index("ix_whatsapp_send_school_id", table_name="whatsapp_send")
    op.drop_table("whatsapp_send")
