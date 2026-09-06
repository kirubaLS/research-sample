"""Scanned documents, kept as they were scanned.

A mark on a report is a claim about a piece of paper. If the paper is gone, the claim
cannot be checked -- so the pages are kept, not just what was read off them. A principal
sending a report to a parent must be able to answer "show me his answer sheet", and the
only honest way to answer is the sheet itself.

Bytes live in the database rather than in object storage. At pilot scale -- one school,
forty students, a handful of papers a term -- that keeps the pages inside the same backup,
the same restore and the same access control as the marks they justify, with no second
system to configure or leak. It is the wrong choice at a thousand schools; ``storage.py``
is where that move goes when it is needed, and nothing outside this module assumes bytes
are local.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PkMixin, TimestampMixin

#: What a stored document is. A question paper belongs to an assessment; an answer sheet
#: belongs to an assessment *and* a student, which is what joins a script to the marks.
#: A mark grid belongs to an assessment and a section -- it holds many students at once,
#: so it carries no single student_id of its own.
DOCUMENT_KINDS = ("question_paper", "answer_sheet", "mark_grid")


class ScanDocument(Base, PkMixin, TimestampMixin):
    __tablename__ = "scan_document"

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    #: null for a question paper: it belongs to the paper, not to any one student
    student_id: Mapped[str | None] = mapped_column(
        ForeignKey("student_profile.id"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(24))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    #: over the concatenated page bytes, in page order -- two uploads of the same script
    #: are recognisable as the same script
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(120), default="")
    #: set when a person confirms these are the right pages, in the right order
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    pages: Mapped[list[ScanPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="ScanPage.index"
    )
    grid_rows: Mapped[list[GridSheetRow]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ScanPage(Base, PkMixin, TimestampMixin):
    __tablename__ = "scan_page"
    __table_args__ = (UniqueConstraint("document_id", "index", name="uq_scan_page"),)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("scan_document.id", ondelete="CASCADE"), index=True
    )
    #: position in the script, from zero. A retake replaces the bytes and keeps the index.
    index: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    #: the capture-time quality metrics, kept because a disputed reading is usually a
    #: disputed photograph, and "it was blurred" is checkable only if we wrote it down
    quality: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)

    document: Mapped[ScanDocument] = relationship(back_populates="pages")


class StudentReport(Base, PkMixin, TimestampMixin):
    """A report as it was issued, kept whole.

    The diagnosis is computed from the marks, so it is always regenerable -- until a mark
    is corrected, a placement is confirmed or the book is reloaded, after which the same
    endpoint returns something different. A parent holding a sheet from last term must be
    able to have it explained, so what was issued is stored rather than recomputed.

    ``payload`` is the whole report body, not a summary. Storing a subset would mean the
    stored copy and the printed one could differ in exactly the parts nobody thought to
    keep.
    """

    __tablename__ = "student_report"

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profile.id"), index=True)
    #: who pressed save, and when. A report nobody put their name to is not issued.
    issued_by: Mapped[str] = mapped_column(String(120), default="")
    #: over the payload, so an altered copy is detectable
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    earned: Mapped[float] = mapped_column(Numeric(7, 2), default=0)
    available: Mapped[float] = mapped_column(Numeric(7, 2), default=0)
    payload: Mapped[dict] = mapped_column(JSON)


class ProposedMark(Base, PkMixin, TimestampMixin):
    """A mark read out of a file, waiting for a person to confirm it.

    Deliberately not a MarkEvent. Everything read is staged here first, so that reading a
    file and accepting what it said are two separate acts by two different parties: the
    machine proposes, a person disposes. Nothing here counts towards any figure until it
    is confirmed, and confirming writes MarkEvents with source 'teacher', because the
    person who pressed the button is the one standing behind the number.

    ``origin`` and ``raw_value`` are kept as the file wrote them -- "row 12, column Q4",
    "3/5" -- so a disputed mark can be traced to the cell it came from without reopening
    the file, which by then may have been edited.
    """

    __tablename__ = "proposed_mark"
    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", "address", name="uq_proposed_mark"),
    )

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("student_profile.id"), index=True)
    #: resolved against the frozen Q-matrix. An address the paper does not have is not
    #: stored at all -- it is reported as unmatched, never invented.
    address: Mapped[str] = mapped_column(String(64))
    marks: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="awarded")
    source_kind: Mapped[str] = mapped_column(String(24), default="file")
    source_name: Mapped[str] = mapped_column(String(200), default="")
    origin: Mapped[str] = mapped_column(String(200), default="")
    raw_value: Mapped[str] = mapped_column(String(64), default="")
    #: why this row cannot be accepted as it stands: unreadable, above the maximum, and so
    #: on. A row with a problem is shown and blocked, never dropped and never repaired.
    problem: Mapped[str | None] = mapped_column(String(300), nullable=True)
    edited_by: Mapped[str | None] = mapped_column(String(120), nullable=True)


#: A row's standing on a class mark-entry sheet, before its marks are trusted.
GRID_ROW_STATUSES = ("unmatched", "name_mismatch", "clean")


class GridSheetRow(Base, PkMixin, TimestampMixin):
    """One student's row on a class mark-entry sheet, before it becomes an ordinary
    per-student proposal.

    A grid sheet holds many students at once, so a roll number has to be resolved to a
    real student before anything from its row can join the same ProposedMark table every
    other reading writes to. Until that happens the row's cells are held here, exactly as
    read; once resolved, they become ProposedMarks like any other reading and this row
    keeps only the identity trail -- who it was on the sheet, who it turned out to be, and
    whether a person had to decide that.
    """

    __tablename__ = "grid_sheet_row"
    __table_args__ = (UniqueConstraint("document_id", "roll_no", name="uq_grid_row"),)

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    section_id: Mapped[str] = mapped_column(ForeignKey("section.id"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("scan_document.id", ondelete="CASCADE"), index=True
    )
    roll_no: Mapped[str] = mapped_column(String(16))
    #: exactly as the sheet spelled it -- a display check against the roster, never the
    #: join key itself
    name_as_written: Mapped[str] = mapped_column(String(200), default="")
    student_id: Mapped[str | None] = mapped_column(
        ForeignKey("student_profile.id"), index=True, nullable=True
    )
    #: "unmatched" -- no student found for this roll; "name_mismatch" -- matched, but the
    #: handwritten name and the roster name disagree enough to ask a person; "clean" --
    #: matched and named consistently, or a person has since said so. Only a "clean" row
    #: is offered by the bulk-confirm action.
    status: Mapped[str] = mapped_column(String(16), default="unmatched")
    #: the sheet's own cells for this row, kept exactly as read -- {question_label,
    #: raw_value} -- so a row can be re-resolved to a different or a new student without
    #: reading the image again
    cells: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    document: Mapped[ScanDocument] = relationship(back_populates="grid_rows")


class GridSheetJob(Base, PkMixin, TimestampMixin):
    """Reading a class mark-entry sheet cannot finish inside one HTTP request.

    It calls the Anthropic vision API -- seconds to tens of seconds for one sheet -- as
    one blocking call, and Render's own reverse proxy kills a web request at a fixed
    timeout regardless of what the app is doing (see ``IngestJob``, which exists for the
    identical reason on a Hindi book upload). A synchronous handler here would return to
    the browser as a bare "Could not reach the API" on a request that reached the backend
    fine and was still working.

    So the upload endpoint does no more than store the sheet's pages (fast: no network)
    and hand this row to a background task, returning 202 immediately; the browser polls
    GET .../gridsheet/jobs/{id} for the result the endpoint used to return directly. The
    pages themselves are not duplicated here -- the background task reads them back off
    the ScanDocument this job points at, the same rows the synchronous handler wrote.
    """

    __tablename__ = "grid_sheet_job"

    school_id: Mapped[str] = mapped_column(ForeignKey("school.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessment.id"), index=True)
    section_id: Mapped[str] = mapped_column(ForeignKey("section.id"))
    document_id: Mapped[str] = mapped_column(ForeignKey("scan_document.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    #: whatever the synchronous handler used to return as its response body
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: an HTTPException's (status_code, detail), so a failed job surfaces the same 422/502
    #: a synchronous read would have raised, not a bare "failed"
    error_status: Mapped[int | None] = mapped_column(nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
