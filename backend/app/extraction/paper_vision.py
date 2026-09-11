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
from concurrent.futures import ThreadPoolExecutor, as_completed
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


#: Read one page, and only one page, per Claude call -- not the whole paper in a single
#: request. This is the same shape app.ingest.gemini_ocr already uses for Hindi books,
#: and for the same underlying reason: a request built from every page at once is a
#: request whose size scales with how long the paper is, with no ceiling, which is what
#: turned into 'RequestTooLargeError: Error code: 413' in production even after
#: individual pages were compressed (a 20+ page paper's compressed pages can still add
#: up). One call per page makes the request size a function of ONE page, never of how
#: many the paper has, so it cannot recur no matter how long a paper gets -- and a page
#: ruined by glare or a bad photo fails on its own instead of taking the whole paper down
#: with it (see ``problems`` on the reading this returns).
class AnthropicPaperVisionReader:
    """One call per page, structured output -- the same shape as the grid-sheet vision
    reader (``app.extraction.gridsheet.AnthropicGridReader``): reading a scan accurately
    is exactly as uncertain as classifying a question, and both get the same discipline
    of a person reviewing before anything counts.
    """

    def __init__(
        self, api_key: str, model: str = "claude-opus-5", *, page_concurrency: int = 4,
    ) -> None:
        if not api_key:
            raise ValueError(
                "no Anthropic API key. Set YAADHUM_ANTHROPIC_API_KEY. Without it a "
                "scanned question paper cannot be read at all -- upload a PDF with a "
                "text layer instead."
            )
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.page_concurrency = max(1, page_concurrency)

    def _read_page(self, data: bytes, content_type: str, prompt: str) -> _PaperOut | None:
        """One page's worth of the call this reader makes. Returns None, with the
        problem recorded by the caller, rather than raising -- a page that fails to read
        is a fact about that page, not a reason to give up on the ones around it."""
        import anthropic

        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": content_type,
                           "data": base64.b64encode(data).decode()},
            },
            {"type": "text", "text": prompt},
        ]
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": content}],
                output_format=_PaperOut,
            )
        except anthropic.APIStatusError as exc:
            # Caught here, by name, rather than left to _run_paper_scan_job's own
            # try/except: that one only wraps the database write that follows this call,
            # not the call itself, so an uncaught error here used to crash the background
            # task outright and leave the job at "pending" forever (nothing left running
            # to ever write "failed" to its row). Raised again as a plain exception with
            # the detail read() needs, so one page's failure is reported against that
            # page rather than aborting every other page still to be read.
            raise RuntimeError(f"({exc.status_code}) {exc.message}") from exc
        return response.parsed_output

    def _read_all(self, pages: list[tuple[bytes, str]]) -> list[_PaperOut | RuntimeError]:
        """Every page's Claude call fired concurrently, not one after another.

        A page does not need any other page's *content* to be read -- the ordering
        this class still guarantees is in the merge step afterwards (read()'s own
        last_section comment), not in when each network call goes out. A 20-page paper
        used to be 20 sequential round trips (tens of seconds to a few minutes); this
        makes it bounded by however long the *slowest* page takes, not their sum.

        Bounded by page_concurrency, not fully unbounded: every concurrent call here is
        a concurrent draw against the same Anthropic rate limit every other paper or
        grid sheet this deployment is reading at that same moment also draws from.

        One prompt for every page now, not the page-specific "you are still in section
        X" hint the sequential version could give once it actually knew the prior
        page's section: that hint only ever assisted the model's own parsing of an
        unlabelled continuation page, and the Python-level fallback two lines below
        (``section = q.section.strip() or last_section``) already backfills the same
        answer regardless of whether the model was told -- the guarantee that survives
        this change is the *data's* section, not what the model was reminded of before
        producing it.
        """
        if not pages:
            return []
        prompt = "Read every question on this page, in order."
        results: list[_PaperOut | RuntimeError] = [
            RuntimeError("not read") for _ in pages
        ]
        with ThreadPoolExecutor(max_workers=min(len(pages), self.page_concurrency)) as pool:
            future_to_index = {
                pool.submit(self._read_page, data, content_type, prompt): i
                for i, (data, content_type) in enumerate(pages)
            }
            for future in as_completed(future_to_index):
                i = future_to_index[future]
                try:
                    results[i] = future.result()
                except RuntimeError as exc:
                    results[i] = exc
        return results

    def read(self, pages: list[tuple[bytes, str]]) -> PaperVisionReading:
        out = PaperVisionReading()
        # Carried across pages, not reset per page: a section header is often printed
        # once and left implicit on every page after it, and a page read on its own (no
        # longer seeing the whole paper in one call) has nothing else to infer it from.
        # This still runs strictly in page order -- only the network calls that feed it
        # are parallel (see _read_all above) -- so a section named on page 3 still
        # carries onto an unlabelled page 4 exactly as it did in the fully sequential
        # version.
        last_section: str | None = None
        results = self._read_all(pages)

        for index in range(1, len(pages) + 1):
            outcome = results[index - 1]
            if isinstance(outcome, RuntimeError):
                out.problems.append(f"page {index}: the vision read failed {outcome}")
                continue
            parsed = outcome

            for key, value in parsed.declared.sections.items():
                out.declared_sections.setdefault(key.upper(), value)
            if out.declared_count is None:
                out.declared_count = parsed.declared.question_count
            if out.declared_total is None:
                out.declared_total = parsed.declared.total_marks

            for q in parsed.questions:
                number = q.question_no.strip()
                if not number:
                    continue
                section = q.section.strip() or last_section
                if q.section.strip():
                    last_section = q.section.strip()
                out.questions.append(ExtractedQuestion(
                    section=section or None,
                    question_no=number,
                    sub_part=q.sub_part.strip().lower() or None,
                    choice_alt=q.choice_alt.strip().lower() or None,
                    max_marks=q.max_marks,
                    stem_text=q.stem_text.strip(),
                    # Known outright now, not a guess the model has to make: each call
                    # sees exactly one page, so there is only one page it could be.
                    logical_page=index,
                    is_context=q.is_context,
                ))

        if not out.questions:
            out.refused = (
                "; ".join(out.problems) if out.problems
                else "nothing readable as a question paper was found in the image(s) sent"
            )
        return out


#: Anthropic resizes any image bigger than this on its own side before the model ever
#: sees it (long edge ~1568px, ~1.15 megapixels) -- sending more resolution than that
#: buys nothing but bytes. Rendering straight for this size, rather than at a fixed high
#: DPI and letting the request balloon, is what keeps a normal multi-page paper (10-20
#: pages) safely under Anthropic's 32MB request-size cap: a 300dpi PNG scan of even a
#: dozen pages routinely exceeds it (this is what produced 'RequestTooLargeError: Error
#: code: 413' in production), while this size costs the same vision tokens either way.
_VISION_LONG_EDGE_PX = 1568
#: Never below this even for a tiny page -- stay legible for a paper with small print.
_VISION_MIN_DPI = 100
#: Never above this even for a huge page -- a giant page rendered at full DPI before
#: being downscaled is still a giant amount of memory to hold mid-render.
_VISION_MAX_DPI = 220


def rasterize_pdf(path) -> list[tuple[bytes, str]]:
    """A PDF's pages, as JPEG images sized for what the vision model actually looks at.

    JPEG, not PNG: these pages are photographs of paper (scans, phone photos of an answer
    script), and PNG's lossless compression does badly on photographic noise -- it can
    run 5-10x larger than a JPEG that looks identical to the model. Quality 85 keeps text
    edges sharp; nothing here needs pixel-perfect reproduction, only legibility.
    """
    import pymupdf

    pages: list[tuple[bytes, str]] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            long_edge_in = max(page.rect.width, page.rect.height) / 72
            dpi = max(_VISION_MIN_DPI, min(_VISION_MAX_DPI, _VISION_LONG_EDGE_PX / long_edge_in))
            pixmap = page.get_pixmap(dpi=round(dpi))
            pages.append((pixmap.tobytes("jpg", jpg_quality=85), "image/jpeg"))
    return pages


def read_paper_vision(
    pages: list[tuple[bytes, str]],
    *,
    api_key: str | None,
    model: str = "claude-opus-5",
    page_concurrency: int = 4,
) -> PaperVisionReading:
    """Dispatch to the vision reader, or refuse by name when there is none configured."""
    if not api_key:
        out = PaperVisionReading()
        out.refused = (
            "no Anthropic API key is configured, so a scanned question paper cannot be "
            "read. Upload a PDF that carries a text layer instead."
        )
        return out
    return AnthropicPaperVisionReader(
        api_key, model, page_concurrency=page_concurrency
    ).read(pages)
