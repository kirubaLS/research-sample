"""Seed a small, real, approved starter set for the BoardX remediation catalogue.

Idempotent: keyed on remediation_ref, which is unique, so re-running only fills in
whatever is missing. Covers the two finding types app.analysis.boardx_report actually
emits (complexity_gap, variant_low) for the three X.MATH chapters the sample BoardX
report itself discusses (Surface Areas and Volumes, Probability, Statistics) -- not the
spec's own demo rows verbatim (those were marked "not a real approved catalogue" in the
source document), but the same practices, keyed correctly for this codebase's finding
types.

Run with:  python -m scripts.seed_remediation
"""

from __future__ import annotations

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import RemediationRow

ROWS = [
    (
        "RM-X-MATH-SAV-COMPLEXITY-01", "X.MATH", "X.MATH.SAV", "complexity_gap",
        "Practise the approved Board-style multi-step Surface Areas and Volumes problem "
        "set, showing every intermediate step before checking the answer.",
    ),
    (
        "RM-X-MATH-SAV-VARIANT-01", "X.MATH", "X.MATH.SAV", "variant_low",
        "Practise the approved Surface Areas and Volumes problem set for the specific "
        "solid type you are losing marks on, working from the formula sheet each time.",
    ),
    (
        "RM-X-MATH-PROB-COMPLEXITY-01", "X.MATH", "X.MATH.PROB", "complexity_gap",
        "Practise the approved compound-probability problem set, writing the event setup "
        "before calculating the probability.",
    ),
    (
        "RM-X-MATH-PROB-VARIANT-01", "X.MATH", "X.MATH.PROB", "variant_low",
        "Practise the approved probability problem set for the specific event type you "
        "are losing marks on, listing the sample space before calculating.",
    ),
    (
        "RM-X-MATH-STATS-COMPLEXITY-01", "X.MATH", "X.MATH.STATS", "complexity_gap",
        "Practise the approved grouped-frequency mean and mode problem set, setting up "
        "the working table before calculating.",
    ),
    (
        "RM-X-MATH-STATS-VARIANT-01", "X.MATH", "X.MATH.STATS", "variant_low",
        "Practise the approved Statistics problem set for the specific measure (mean, "
        "median or mode) you are losing marks on, from a grouped frequency table.",
    ),
]


def main() -> None:
    init_db()
    db = SessionLocal()
    created = 0
    for ref, subject, domain, finding_type, text in ROWS:
        if db.scalar(select(RemediationRow).where(RemediationRow.remediation_ref == ref)):
            continue
        db.add(RemediationRow(
            remediation_ref=ref, subject_code=subject, domain_code=domain,
            finding_type=finding_type, student_action_text=text,
            approved=True, created_by="scripts.seed_remediation",
        ))
        created += 1
    db.commit()
    db.close()
    print(f"{created} remediation row(s) created, {len(ROWS) - created} already existed.")


if __name__ == "__main__":
    main()
