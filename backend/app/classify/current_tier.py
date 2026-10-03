"""The current tier of each question, read from its append-only QuestionTier rows.

QuestionTier is never edited: every classify run and every review appends a row, and a
run that could not decide appends one with ``tier`` None (an abstain). The current tier
is the newest row that names one -- oldest first, so each later named tier replaces the
one before, and an abstain never erases a tier already decided. Every reader (the scan
screen, the reports, the academics views) reads it here, so they cannot disagree.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuestionTier


def current_tiers(db: Session, question_ids) -> tuple[dict[str, str], set[str]]:
    """(question id -> its current tier, every question id that has any tier row)."""
    ids = [i for i in question_ids if i]
    tiers: dict[str, str] = {}
    seen: set[str] = set()
    if not ids:
        return tiers, seen
    for row in db.scalars(
        select(QuestionTier).where(QuestionTier.question_id.in_(ids))
        .order_by(QuestionTier.created_at, QuestionTier.id)
    ):
        seen.add(row.question_id)
        if row.tier:
            tiers[row.question_id] = row.tier
    return tiers, seen
