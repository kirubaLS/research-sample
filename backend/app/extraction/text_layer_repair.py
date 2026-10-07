"""Fill a question whose text the reader lost, from the PDF's own text layer.

A page break can separate an assertion-and-reason instruction from the statements it
introduces: the instruction ends one page, the answer codes and "24. Assertion (A) : ...
Reason (R) : ..." start the next. A reader that works page by page can return the instruction
alone as the question. When the PDF has a text layer the statements are there, under the
question's printed number, and this puts them back -- word for word, deterministically, with
no model call.

It only ever FILLS a gap: a row is touched only when its stem is nothing but an instruction
(``app.classify.science_scope.instruction_only``), and a stem the reader did get is never
replaced. A photographed paper has no text layer, so nothing is found and the row stays as it
was (blocked with its reason by the Science instruction-row rule).
"""

from __future__ import annotations

import re

_PAGE_FURNITURE = re.compile(r"(?im)^\s*page\s+\d+\s+of\s+\d+\s*$")
#: the printed mark label ("1") that sits between the assertion and the reason on the line
_MARK_BETWEEN = re.compile(r"\s\d{1,2}\s+(?=Reason\s*\(R\)\s*[:：])")
_NUMBER = re.compile(r"^\d{1,3}$")


def pdf_text(originals) -> str:
    """The text layer of every PDF among ``originals`` ((bytes, content type, name))."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        return ""
    parts: list[str] = []
    for content, content_type, _name in originals:
        if "pdf" not in (content_type or "").lower():
            continue
        try:
            with pymupdf.open(stream=content, filetype="pdf") as doc:
                parts.extend(page.get_text() for page in doc)
        except Exception:  # noqa: BLE001 -- an unreadable file simply has no text to offer
            continue
    return "\n".join(parts)


def assertion_reason_for(number: str, text: str) -> str | None:
    """The assertion and reason printed under question ``number``, or None."""
    if not _NUMBER.match(number or ""):
        return None
    pattern = re.compile(
        r"(?ms)^\s*" + re.escape(number) + r"\.\s*"
        r"(Assertion\s*\(A\)\s*[:：].*?Reason\s*\(R\)\s*[:：].*?)"
        r"(?=^\s*\d{1,3}\.\s|\Z)"
    )
    m = pattern.search(text)
    if not m:
        return None
    body = _PAGE_FURNITURE.sub(" ", m.group(1))
    body = " ".join(body.split())
    return _MARK_BETWEEN.sub(" ", body).strip() or None


def repair_instruction_stems(questions, originals) -> list[str]:
    """Fill every instruction-only stem among ``questions`` from the PDF text layer.
    Returns the addresses repaired."""
    from app.classify.science_scope import instruction_only

    pending = [q for q in questions if instruction_only(q.stem_text)]
    if not pending:
        return []
    text = pdf_text(originals)
    if not text:
        return []
    repaired: list[str] = []
    for q in pending:
        found = assertion_reason_for(q.question_no, text)
        if found:
            q.stem_text = found
            repaired.append(q.address)
    return repaired
