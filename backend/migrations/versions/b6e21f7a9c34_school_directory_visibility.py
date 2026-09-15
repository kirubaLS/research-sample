"""school directory visibility

Adds School.hidden_from_directory, which GET /t/classes (the public, unauthenticated
student entry page) now checks before listing a school's sections.

Judgment call, flagged for the operator to override if this guessed wrong: the ORM
default for a *newly created* school is ``True`` (hidden) -- the ask was "don't show
until [the operator chooses to] create schools", meaning a school must not become
publicly listed merely by existing. But that same default cannot be applied
retroactively to schools already running a pilot today: doing so would silently vanish
every live school from the student entry page the next time this migrates, which is a
production outage, not a privacy improvement nobody asked for. So this migration
backfills existing rows to ``False`` (visible) -- every school live before this shipped
keeps exactly the visibility it has today -- while the column's server default is
``True``, so any school created by a direct SQL insert (bypassing the ORM) after this
migration also starts hidden. Only schools created through the API from this point on
inherit the ORM's ``True`` default and start hidden until an operator opts them in via
the new toggle endpoint.

Revision ID: b6e21f7a9c34
Revises: f3a8c1d92b47
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b6e21f7a9c34"
down_revision: str | None = "f3a8c1d92b47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "school",
        sa.Column(
            "hidden_from_directory", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    # Backfill: schools that already existed before this column arrived keep the
    # visibility they have today (listed), rather than inheriting the "hidden by
    # default" rule meant for schools created from here on.
    op.execute("UPDATE school SET hidden_from_directory = FALSE")


def downgrade() -> None:
    op.drop_column("school", "hidden_from_directory")
