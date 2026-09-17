"""Seed a starter set for the BoardX remediation catalogue, for every subject that has
a chapter loaded -- not one subject hand-listed here.

One generic, honest row per chapter per finding type app.analysis.boardx_report actually
emits (complexity_gap, variant_low), generated from the same CURRICULA registry every
book-loading screen already reads from. A chapter added to the curriculum later is picked
up the next time this runs; nothing here has to be edited by hand to add a subject.

These rows are deliberately generic ("practise the chapter's own exercises, step by
step") rather than naming specific NCERT exercise numbers -- naming real exercises needs a
person who has actually reviewed the book's exercises to approve it, which is exactly what
RemediationRow.approved and app/api/remediation.py's admin endpoint are for. A more
specific row for a chapter (POST /platform/remediation with a more specific
remediation_ref) simply resolves first, ahead of nothing -- there is no ranking here, only
one row can match a given (subject, chapter, finding_type), so replace a generic row by
approving a specific one under a new ref and withdrawing the generic one
(PATCH .../{old_ref} {"approved": false}).

Idempotent: keyed on remediation_ref, so re-running only fills in what is missing.

Run with:  python -m scripts.seed_remediation
"""

from __future__ import annotations

from sqlalchemy import select

from app.curriculum import CURRICULA
from app.db import SessionLocal, init_db
from app.models import RemediationRow

_TEMPLATES = {
    "complexity_gap": (
        "Practise {chapter}'s own exercises in order of difficulty, starting from the "
        "questions that ask you to state or identify something and working up to the "
        "questions that ask you to apply it -- write out every step rather than jumping "
        "to the answer."
    ),
    "variant_low": (
        "Go back to {chapter} and practise the specific type of question you are losing "
        "marks on, using the book's own worked examples as the model for how to set up "
        "each step before you calculate."
    ),
}


def _ref(subject_code: str, chapter_code: str, finding_type: str) -> str:
    slug = finding_type.upper().replace("_", "-")
    return f"RM-{chapter_code.replace('.', '-')}-{slug}-01"


def main() -> None:
    init_db()
    db = SessionLocal()
    created = 0
    seen_chapters: set[tuple[str, str]] = set()
    for curriculum in CURRICULA.values():
        for chapter in curriculum.chapters:
            key = (curriculum.subject_code, chapter.code)
            if key in seen_chapters:
                continue
            seen_chapters.add(key)
            for finding_type, template in _TEMPLATES.items():
                ref = _ref(curriculum.subject_code, chapter.code, finding_type)
                if db.scalar(select(RemediationRow).where(RemediationRow.remediation_ref == ref)):
                    continue
                db.add(RemediationRow(
                    remediation_ref=ref, subject_code=curriculum.subject_code,
                    domain_code=chapter.code, finding_type=finding_type,
                    student_action_text=template.format(chapter=chapter.label),
                    approved=True, created_by="scripts.seed_remediation",
                ))
                created += 1
    db.commit()
    db.close()
    print(f"{created} remediation row(s) created across {len(seen_chapters)} chapter(s).")


if __name__ == "__main__":
    main()
