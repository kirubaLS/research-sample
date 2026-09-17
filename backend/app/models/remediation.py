"""The remediation catalogue: approved practice text a BoardX student report is allowed
to show under "what to practise next".

R4 and R7 of the BoardX composition spec forbid the report writing an action ad hoc --
a recommendation may render only when it resolves to a row here with ``approved`` set.
Keyed by subject x chapter (``domain_code``) x finding type, because that is exactly what
a finding names and exactly what a resolver needs to look a row up by.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin


class RemediationRow(Base, PkMixin, TimestampMixin):
    """One approved 'what to practise next' text, for one subject/chapter/finding shape.

    Never edited into a different meaning once approved: a report issued last term must
    still be explicable from what it cited, so a correction is a new row (approved=False
    on the old one, a fresh one in its place), not an in-place rewrite.
    """

    __tablename__ = "remediation_row"
    __table_args__ = (
        UniqueConstraint("remediation_ref", name="uq_remediation_ref"),
    )

    remediation_ref: Mapped[str] = mapped_column(String(80), index=True)
    subject_code: Mapped[str] = mapped_column(String(32), index=True)
    #: the chapter's taxonomy code (e.g. 'X.MATH.SAV') -- a report finding's own chapter
    #: code, so a resolver never has to translate a label back into an identity first.
    domain_code: Mapped[str] = mapped_column(String(80), index=True)
    #: what shape of loss this practice text answers -- 'multi_step', 'compound_event',
    #: 'grouped_mean', etc. Free text by design: the finding types a rule engine emits are
    #: not a closed set this table should have to be migrated to keep up with.
    finding_type: Mapped[str] = mapped_column(String(80), index=True)
    student_action_text: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[str] = mapped_column(String(120), default="")
