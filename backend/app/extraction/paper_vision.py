"""Reading a scanned or photographed question paper with a vision model.

``paper.py`` documents the gap this fills: its **vision** route is a scan carrying no
text at all -- Real board papers are often this shape, and until now nothing here could
read one. This module is that reader, called only when the text route has already
concluded the PDF is a scan (see ``extract_paper``'s own vision-route check), and
producing the same ``ExtractedQuestion`` rows the text route does, so everything
downstream -- staging, review, mapping -- is one pipeline regardless of which route read
the paper.

Every question is still a proposal: ``scan_paper``'s own review step, and the confirm
gate before mapping, apply exactly as they do to a text-route read. Nothing here writes a
mark or a question directly.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.extraction.paper import ExtractedQuestion


@dataclass
class PaperVisionReading:
    questions: list[ExtractedQuestion] = field(default_factory=list)
    #: set when nothing usable could be read at all, rather than read badly
    refused: str | None = None
    problems: list[str] = field(default_factory=list)
    #: what the paper says about itself -- "Maximum Marks: 80", "this paper contains 38
    #: questions", "Section A (20 marks)" -- read straight off the cover/instructions,
    #: never computed from the questions the model itself just extracted. This is what
    #: makes the guardrail real: confirm_scan checks the extracted total against this
    #: figure and refuses to let a mismatch through, exactly as it already does for a
    #: text-route read (see paper.py's own DECLARED_TOTAL). A vision read that skipped
    #: this would be checked against nothing.
    declared_sections: dict[str, float] = field(default_factory=dict)
    declared_count: int | None = None
    declared_total: float | None = None


class _QuestionOut(BaseModel):
    section: str = ""
    question_no: str
    sub_part: str = ""
    choice_alt: str = ""
    max_marks: float | None = None
    stem_text: str = ""
    logical_page: int = 1
    #: true for a shared stem (a case-study paragraph before (i), (ii), (iii)) that is not
    #: itself worth marks
    is_context: bool = False


class _DeclaredOut(BaseModel):
    #: {"A": 20.0, "B": 24.0, ...} -- only sections the paper states a mark total for
    #: on its own cover or instructions page, never inferred by adding up questions
    sections: dict[str, float] = {}
    question_count: int | None = None
    total_marks: float | None = None


class _PaperOut(BaseModel):
    questions: list[_QuestionOut] = []
    declared: _DeclaredOut = _DeclaredOut()


SYSTEM = (
    "You are reading a scanned or photographed CBSE question paper -- a picture of a "
    "page, not a text document -- in any of the languages CBSE Class X sets one in "
    "(English, Hindi, Tamil, or a bilingual paper printing both). "
    "\n\n"
    "GUARDRAIL, more important than completeness: this paper is being read to build a "
    "school's official record of marks. A confident wrong answer is worse than an "
    "honest gap. Never invent, estimate, or round a value you cannot actually see. "
    "Every number and every word of stem text must be traceable to ink on the page. If "
    "a mark, a question number, or any other field is not legible, leave it blank -- do "
    "not fill it in from what a typical CBSE paper usually has. Do not let familiarity "
    "with common paper patterns substitute for what THIS paper actually shows.  "
    "\n\n"
    "Extract every question in the order it is printed: its section letter if the "
    "paper has sections (A, B, C...), its question number, a sub-part letter if it has "
    "one (i, ii, iii or a, b, c), an internal-choice letter if this is the alternative "
    "offered after the word OR (the first of a pair is blank, the alternative is 'b'), "
    "how many marks it is worth, its stem text (the question exactly as printed, "
    "transliterated faithfully if not in English -- never your summary or translation "
    "of it), and the page it is on. "
    "A bilingual paper prints each question twice, once in Hindi (or Tamil) and once in "
    "English -- extract only the English copy, never both, and never invent an English "
    "translation of a question that was only printed in the other language. "
    "A case-study or comprehension question prints a shared paragraph before several "
    "numbered sub-questions: extract that paragraph as its own row with is_context=true "
    "and no marks of its own; the marks belong to its sub-parts. "
    "Read marks exactly as printed (often in brackets at the right margin, like [2] or "
    "(3)) -- do not compute or guess a total. If a question's marks are not legible, "
    "leave max_marks blank rather than guessing. "
    "\n\n"
    "Separately, read what the paper's own cover or instructions page declares about "
    "itself, if anything is printed there: the maximum marks for the whole paper "
    "(e.g. 'Maximum Marks: 80'), how many questions it contains (e.g. 'This question "
    "paper contains 38 questions'), and any per-section mark total (e.g. 'Section A: "
    "20 marks', or 'This section comprises 6 questions of 3 marks each' -- multiply "
    "those two numbers together for that section's total). Leave any of these blank "
    "if the paper does not state it outright -- never calculate it yourself from the "
    "questions you extracted; it must be a number the paper itself prints."
)


class AnthropicPaperVisionReader:
    """One call, one paper, structured output -- the same shape as the grid-sheet vision
    reader (``app.extraction.gridsheet.AnthropicGridReader``): reading a scan accurately
    is exactly as uncertain as classifying a question, and both get the same discipline
    of a person reviewing before anything counts.
    """

    def __init__(self, api_key: str, model: str = "claude-opus-5") -> None:
        if not api_key:
            raise ValueError(
                "no Anthropic API key. Set YAADHUM_ANTHROPIC_API_KEY. Without it a "
                "scanned question paper cannot be read at all -- upload a PDF with a "
                "text layer instead."
            )
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def read(self, pages: list[tuple[bytes, str]]) -> PaperVisionReading:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": content_type,
                    "data": base64.b64encode(data).decode(),
                },
            }
            for data, content_type in pages
        ]
        content.append({"type": "text", "text": "Read every question on this paper, in order."})
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=_PaperOut,
        )
        parsed: _PaperOut = response.parsed_output
        out = PaperVisionReading(
            declared_sections={k.upper(): v for k, v in parsed.declared.sections.items()},
            declared_count=parsed.declared.question_count,
            declared_total=parsed.declared.total_marks,
        )
        for q in parsed.questions:
            number = q.question_no.strip()
            if not number:
                continue
            out.questions.append(ExtractedQuestion(
                section=q.section.strip() or None,
                question_no=number,
                sub_part=q.sub_part.strip().lower() or None,
                choice_alt=q.choice_alt.strip().lower() or None,
                max_marks=q.max_marks,
                stem_text=q.stem_text.strip(),
                logical_page=max(1, q.logical_page),
                is_context=q.is_context,
            ))
        if not out.questions:
            out.refused = "nothing readable as a question paper was found in the image(s) sent"
        return out


def rasterize_pdf(path, *, dpi: int = 300) -> list[tuple[bytes, str]]:
    """A PDF's pages, as PNG images -- what the vision model actually needs to look at.
    300dpi matches the render used elsewhere in this codebase for a page a model has to
    read (see app.ingest.gemini_ocr.RENDER_DPI)."""
    import pymupdf

    pages: list[tuple[bytes, str]] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pages.append((page.get_pixmap(dpi=dpi).tobytes("png"), "image/png"))
    return pages


def read_paper_vision(
    pages: list[tuple[bytes, str]],
    *,
    api_key: str | None,
    model: str = "claude-opus-5",
) -> PaperVisionReading:
    """Dispatch to the vision reader, or refuse by name when there is none configured."""
    if not api_key:
        out = PaperVisionReading()
        out.refused = (
            "no Anthropic API key is configured, so a scanned question paper cannot be "
            "read. Upload a PDF that carries a text layer instead."
        )
        return out
    return AnthropicPaperVisionReader(api_key, model).read(pages)
