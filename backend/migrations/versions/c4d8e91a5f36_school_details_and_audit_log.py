"""school details, staff contact fields, student parent fields, audit log

Adds the columns the ops console's 6-tab school detail screen needs, plus a new
audit_log table it writes to:

* School gains code/city/address/academic_year -- purely descriptive, operator-editable
  "school details" fields, no code elsewhere touches them.
* StaffKey gains name/email/phone (contact details for the Principal/Teachers tabs) and
  last_used_at (set on every successful X-API-Key authentication -- see
  app.api.deps.current_staff).
* StudentProfile gains parent_name/parent_whatsapp for the Students tab's roster.
* audit_log is a new, append-only table: app.api.platform writes one row per
  state-changing call it makes (school create/edit, key issue/revoke/rotate/edit,
  student bulk-add, teacher-assignment edit) so the Activity tab has something real to
  show.

All additive, all nullable (or default) -- no existing row needs a value, and nothing
here changes what an existing row already means.

Revision ID: c4d8e91a5f36
Revises: b2c3d4e5f6a7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8e91a5f36"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("school", sa.Column("code", sa.String(32), nullable=True))
    op.add_column("school", sa.Column("city", sa.String(120), nullable=True))
    op.add_column("school", sa.Column("address", sa.String(500), nullable=True))
    op.add_column("school", sa.Column("academic_year", sa.String(16), nullable=True))

    op.add_column("staff_key", sa.Column("name", sa.String(200), nullable=True))
    op.add_column("staff_key", sa.Column("email", sa.String(200), nullable=True))
    op.add_column("staff_key", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column(
        "staff_key", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column("student_profile", sa.Column("parent_name", sa.String(200), nullable=True))
    op.add_column(
        "student_profile", sa.Column("parent_whatsapp", sa.String(32), nullable=True)
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.String(36), sa.ForeignKey("school.id"), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=False, server_default="platform_admin"),
        sa.Column("actor_label", sa.String(200), nullable=False, server_default=""),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail", sa.String(2000), nullable=True),
    )
    op.create_index("ix_audit_log_school_id", "audit_log", ["school_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_school_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_column("student_profile", "parent_whatsapp")
    op.drop_column("student_profile", "parent_name")

    op.drop_column("staff_key", "last_used_at")
    op.drop_column("staff_key", "phone")
    op.drop_column("staff_key", "email")
    op.drop_column("staff_key", "name")

    op.drop_column("school", "academic_year")
    op.drop_column("school", "address")
    op.drop_column("school", "city")
    op.drop_column("school", "code")
