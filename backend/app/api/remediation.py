"""The remediation catalogue: approved 'what to practise next' text a BoardX report may
cite (R4 and R7 of the composition spec -- see app/analysis/boardx_report.py).

Platform-scoped, not per-school: the catalogue is curated content -- the same shape as a
concept family -- and a school never invents its own row, it only draws on this shared,
reviewed set.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_admin
from app.db import get_session
from app.models import RemediationRow

router = APIRouter(
    prefix="/platform/remediation", tags=["remediation"],
    dependencies=[Depends(require_platform_admin)],
)


@router.get("")
def list_remediation(
    subject: str | None = None, db: Session = Depends(get_session),
) -> dict:
    """Every row in the catalogue, optionally narrowed to one subject."""
    stmt = select(RemediationRow)
    if subject:
        stmt = stmt.where(RemediationRow.subject_code == subject)
    rows = list(db.scalars(stmt.order_by(RemediationRow.subject_code, RemediationRow.domain_code)))
    return {
        "rows": [
            {
                "id": r.id, "remediation_ref": r.remediation_ref,
                "subject_code": r.subject_code, "domain_code": r.domain_code,
                "finding_type": r.finding_type, "student_action_text": r.student_action_text,
                "approved": r.approved, "created_by": r.created_by,
            }
            for r in rows
        ],
    }


class RemediationIn(BaseModel):
    remediation_ref: str = Field(min_length=1, max_length=80)
    subject_code: str = Field(min_length=1, max_length=32)
    domain_code: str = Field(min_length=1, max_length=80)
    finding_type: str = Field(min_length=1, max_length=80)
    student_action_text: str = Field(min_length=1)
    approved: bool = False
    by: str = ""


@router.post("", status_code=201)
def create_remediation(body: RemediationIn, db: Session = Depends(get_session)) -> dict:
    """Add one catalogue row. Never a rename in place -- see RemediationRow's own
    docstring: a correction is a new ref, so a report already issued citing the old one
    stays explicable from exactly what it cited."""
    if db.scalar(
        select(RemediationRow).where(RemediationRow.remediation_ref == body.remediation_ref)
    ) is not None:
        raise HTTPException(409, f"{body.remediation_ref!r} already exists")
    row = RemediationRow(
        remediation_ref=body.remediation_ref, subject_code=body.subject_code,
        domain_code=body.domain_code, finding_type=body.finding_type,
        student_action_text=body.student_action_text, approved=body.approved,
        created_by=body.by[:120],
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "remediation_ref": row.remediation_ref}


class ApproveIn(BaseModel):
    approved: bool = True


@router.patch("/{remediation_ref}")
def set_remediation_approval(
    remediation_ref: str, body: ApproveIn, db: Session = Depends(get_session),
) -> dict:
    """Approve or withdraw one row. Withdrawing (approved=False) is how a wrong row is
    retired -- it stops resolving for new reports without deleting the ref an old, already
    -issued report may have cited."""
    row = db.scalar(select(RemediationRow).where(RemediationRow.remediation_ref == remediation_ref))
    if row is None:
        raise HTTPException(404, f"no remediation row {remediation_ref!r}")
    row.approved = body.approved
    db.commit()
    return {"remediation_ref": row.remediation_ref, "approved": row.approved}
