"""Rendering an issued student report to an actual PDF file.

An issued ``StudentReport`` already carries its own proof -- every strength and every
gap traces to real confirmed marks, with the questions behind the number listed as
evidence, never inferred -- so this module computes nothing new. It only lays the same
payload the API already returns out on a page, so a principal can hand a parent a file
rather than a screen, with the same figures either way.

Pure-Python (fpdf2, no system library like wkhtmltopdf or weasyprint need), imported
lazily here the same way ``AnthropicJudge`` imports ``anthropic``: a missing install
degrades only the PDF download, not the whole API's boot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import StudentReport

#: Core PDF fonts are Latin-1 only. A name or a label outside that range is shown with its
#: unencodable characters replaced rather than raising -- a report that fails to render at
#: all over one character is a worse failure than a handful of "?" in it.
def _safe(text: object) -> str:
    return str(text if text is not None else "").encode("latin-1", "replace").decode("latin-1")


def render_student_report_pdf(
    record: StudentReport, *, student_name: str, roll_no: str, school_name: str,
) -> bytes:
    from fpdf import FPDF

    payload = record.payload or {}

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "Yaadhum -- Assessment Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 7, _safe(school_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, _safe(f"{student_name} (roll {roll_no})"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _safe(payload.get("assessment_title", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    total = payload.get("total") or {}
    rate = total.get("rate")
    pdf.set_font("Helvetica", "B", 12)
    pct = f"  ({rate * 100:.0f}%)" if rate is not None else ""
    pdf.cell(
        0, 8, _safe(f"Score: {total.get('earned')} / {total.get('available')}{pct}"),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(2)

    def section(title: str, findings: list[dict], empty_text: str) -> None:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_fill_color(240, 242, 247)
        pdf.cell(0, 8, _safe(title), new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(1)
        if not findings:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, _safe(empty_text), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            return
        for f in findings:
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, _safe(f.get("label") or f.get("key") or ""), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            if f.get("message"):
                pdf.multi_cell(0, 5, _safe(f["message"]), new_x="LMARGIN", new_y="NEXT")
            evidence = f.get("evidence") or []
            if evidence:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(100, 100, 100)
                parts = []
                for e in evidence:
                    address = e.get("address", "")
                    earned = e.get("earned")
                    available = e.get("max_marks", e.get("available"))
                    parts.append(f"{address}: {earned}/{available}" if earned is not None else str(address))
                pdf.multi_cell(0, 5, _safe("Source: " + "; ".join(parts)), new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

    section(
        "Strengths", payload.get("strengths") or [],
        "No chapter yet has enough confirmed marks to call it a strength.",
    )
    section(
        "Needs attention", payload.get("focus") or [],
        "No chapter yet has enough confirmed marks to flag as a gap.",
    )

    not_offered = payload.get("not_offered") or []
    if not_offered:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Not attempted (other choice taken):", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _safe(", ".join(not_offered)), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    issued_at = record.created_at.isoformat() if record.created_at else "unknown date"
    pdf.multi_cell(
        0, 5,
        _safe(
            f"Issued by {record.issued_by or 'unknown'} on {issued_at}. "
            f"Checksum {record.sha256[:16]}... -- every figure above traces to a "
            f"confirmed mark; nothing here is inferred."
        ),
        new_x="LMARGIN", new_y="NEXT",
    )

    return bytes(pdf.output())
