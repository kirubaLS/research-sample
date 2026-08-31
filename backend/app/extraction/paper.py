"""Read a question paper into questions, in the order the paper puts them.

The primitives this builds on already existed -- address parsing, the mark grammar and its
right-aligned band, choice grouping, the verification gates. What was missing was the pass
that turns a PDF into rows: until now a Q-matrix had to be typed in by hand as JSON.

Two routes, decided by the file rather than by the caller:

**text** -- the PDF carries a text layer, so spans have positions and the mark band works.
Every CBSE paper generated from source is like this.

**vision** -- the PDF is a scan, and carries no text at all. Real board papers are often
this: the Class X Maths paper in this project is six pages, 116 images and zero characters.
Nothing here can read it, and this module says so rather than returning an empty paper that
looks like a successful extraction of nothing.

The bilingual case is not an edge case. A CBSE paper prints each question in Hindi and
English, so question 2 legitimately appears twice, and one of the two is usually unreadable
because the Devanagari is not in the font's cmap. Keeping both would double every mark
total; keeping the wrong one would store a stem nobody can read.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from app.extraction.mark_grammar import MARK_BAND, parse_label

#: 'SECTION A', 'SECTION-B', 'Section C'. The middot is not decorative: a dash whose glyph
#: is missing from the embedded font extracts as one.
SECTION = re.compile(r"^\s*SECTION\s*[-–—·]?\s*([A-E])\b", re.IGNORECASE)
#: '1.', '21 .', '39.' at the start of a line -- the question number as the paper prints it
QUESTION = re.compile(r"^\s*(\d{1,2})\s*\.\s*(.*)$", re.DOTALL)
#: '(i)', '(a)' -- a sub-part carrying its own marks
SUB_PART = re.compile(r"^\s*\(([ivx]{1,4}|[a-d])\)\s*(.*)$", re.IGNORECASE | re.DOTALL)
#: the internal-choice marker, in the languages this pilot sees
OR_MARKER = re.compile(r"^\s*(OR|अथवा|அல்லது)\s*$", re.IGNORECASE)
#: 'Section A : Biology (30 marks)' in the instructions block
DECLARED_SECTION = re.compile(
    r"Section\s+([A-E])\s*[:\-]?\s*([A-Za-z ]{0,30}?)\s*\((\d{1,3})\s*marks?\)",
    re.IGNORECASE,
)
DECLARED_COUNT = re.compile(r"contains?\s+(\d{1,3})\s+questions?", re.IGNORECASE)

#: A scanned page yields at most a header and a stamped page number. Below this per page,
#: with images present, the document is a picture of a paper rather than a paper.
SCAN_CHARS_PER_PAGE = 25
#: A stem shorter than this is a fragment, not a question.
MIN_STEM_CHARS = 12


@dataclass
class Line:
    """One visual line: the spans that share a row, in reading order."""

    text: str
    page: int
    top: float
    left: float
    right_fraction: float
    page_width: float


@dataclass
class ExtractedQuestion:
    section: str | None
    question_no: str
    sub_part: str | None
    choice_alt: str | None
    max_marks: float | None
    stem_text: str
    logical_page: int

    @property
    def identity(self) -> tuple[str, str | None, str | None]:
        """What makes two printings the same question.

        Deliberately excludes the section. A bilingual paper prints "SECTION B" in
        Devanagari too, which does not match, so the Hindi copy of question 27 is still
        filed under section A while the English copy is under B. Keyed on the address they
        look like two questions and both survive, which is how a 39-question paper
        extracted as 54.
        """
        return (self.question_no, self.sub_part, self.choice_alt)

    @property
    def address(self) -> str:
        return "/".join([
            self.section or "", self.question_no, self.sub_part or "", self.choice_alt or ""
        ])


@dataclass
class PaperExtract:
    route: str                      # 'text' | 'vision'
    page_count: int
    questions: list[ExtractedQuestion] = field(default_factory=list)
    #: what the instructions page claims, for the verification gates to check against
    declared_sections: dict[str, float] = field(default_factory=dict)
    declared_count: int | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def total_marks(self) -> float:
        return sum(q.max_marks or 0.0 for q in self.questions if q.choice_alt in (None, "a"))


def readable_letters(text: str) -> int:
    """How much of this stem a person could actually read.

    The bilingual discriminator, and it counts rather than takes a ratio. A ratio was the
    obvious choice and was wrong: the Hindi printing of an MCQ extracts as nothing but its
    option markers, "(A) (B) (C) (D)", whose only letters are Latin -- so it scored a
    perfect ratio of 1.0 and beat the English printing every time. Counting cannot be
    fooled that way: four letters is four letters, and the English stem has ninety.
    """
    return sum(1 for c in text if c.isalpha() and "LATIN" in unicodedata.name(c, ""))


def read_lines(path: str | Path) -> tuple[list[Line], int, int, int]:
    """Assemble spans into visual lines. Returns (lines, pages, characters, images)."""
    lines: list[Line] = []
    characters = 0
    images = 0
    with pymupdf.open(path) as doc:
        pages = len(doc)
        for number, page in enumerate(doc, start=1):
            images += len(page.get_images(full=True))
            width = page.rect.width or 1.0
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(s["text"] for s in spans)
                    characters += len(text.strip())
                    if not text.strip():
                        continue
                    x0 = min(s["bbox"][0] for s in spans)
                    x1 = max(s["bbox"][2] for s in spans)
                    top = min(s["bbox"][1] for s in spans)
                    lines.append(
                        Line(text, number, top, x0, x1 / width, width)
                    )
    lines.sort(key=lambda line: (line.page, round(line.top, 1), line.left))
    return lines, pages, characters, images


def _marks_on(line: Line) -> float | None:
    """A mark label, only if it sits in the right-aligned band.

    The band is what separates '2' meaning two marks from '2' meaning option (2) or a
    numbered instruction. Measured from real papers, not chosen.
    """
    label = parse_label(line.text)
    if label is None or label.form == "section_total":
        return None
    if not (MARK_BAND[0] <= line.right_fraction <= MARK_BAND[1]):
        return None
    return label.value


def _declared(lines: list[Line]) -> tuple[dict[str, float], int | None]:
    blob = "\n".join(line.text for line in lines[:220])
    sections = {
        letter.upper(): float(marks)
        for letter, _subject, marks in DECLARED_SECTION.findall(blob)
    }
    count = DECLARED_COUNT.search(blob)
    return sections, int(count.group(1)) if count else None


def extract_paper(path: str | Path) -> PaperExtract:
    """Read a question paper. The result is checkable, never merely plausible."""
    lines, pages, characters, images = read_lines(path)

    # Both conditions, not either. Character count alone called a short cyclic test a scan;
    # images alone would call any illustrated paper one. A scan is pictures WITH no text:
    # the Class X Maths board paper is six pages, 116 images and zero characters.
    if characters < SCAN_CHARS_PER_PAGE * max(pages, 1) and images >= pages:
        out = PaperExtract(route="vision", page_count=pages)
        out.problems.append(
            f"this paper carries no usable text layer ({characters} characters and "
            f"{images} images across {pages} pages), so it is a scan. Reading it needs "
            f"the vision route; nothing was extracted."
        )
        return out

    declared_sections, declared_count = _declared(lines)
    out = PaperExtract(
        route="text", page_count=pages,
        declared_sections=declared_sections, declared_count=declared_count,
    )

    section: str | None = None
    current: ExtractedQuestion | None = None
    #: the number of the question an OR belongs to. In CBSE an internal choice prints the
    #: alternative UNNUMBERED after the word OR, so it inherits the number just closed --
    #: treating the next numbered question as the alternative made every following
    #: question the choice-half of the one before it.
    alternative_to: str | None = None
    collected: list[ExtractedQuestion] = []

    def close() -> None:
        nonlocal current
        if current is not None:
            current.stem_text = " ".join(current.stem_text.split())[:4000]
            collected.append(current)
            current = None

    for line in lines:
        text = line.text.strip()

        heading = SECTION.match(text)
        if heading:
            close()
            section = heading.group(1).upper()
            alternative_to = None
            continue

        if OR_MARKER.match(text):
            alternative_to = current.question_no if current else None
            close()
            continue

        marks = _marks_on(line)
        if marks is not None:
            if current is not None and current.max_marks is None:
                current.max_marks = marks
            continue

        start = QUESTION.match(text)
        if start and line.left < line.page_width * 0.22:
            close()
            alternative_to = None
            current = ExtractedQuestion(
                section=section, question_no=start.group(1), sub_part=None,
                choice_alt=None, max_marks=None,
                stem_text=start.group(2), logical_page=line.page,
            )
            continue

        if current is None and alternative_to is not None and len(text) > MIN_STEM_CHARS:
            # Unnumbered text after an OR: the second alternative of the question before.
            current = ExtractedQuestion(
                section=section, question_no=alternative_to, sub_part=None,
                choice_alt="b", max_marks=None, stem_text=text, logical_page=line.page,
            )
            continue

        if current is not None:
            current.stem_text += " " + text

    close()

    out.questions = _inherit_choice_marks(_resolve_bilingual(collected))
    _check(out)
    return out


def _inherit_choice_marks(questions: list[ExtractedQuestion]) -> list[ExtractedQuestion]:
    """An internal choice is worth what the question it replaces is worth.

    That is what "attempt either (a) or (b)" means, so a paper often prints the mark label
    once, above the OR. Leaving the alternative unmarked would drop it out of every
    denominator the moment a student answered it.
    """
    primary = {
        q.question_no: q.max_marks
        for q in questions
        if q.choice_alt is None and q.max_marks is not None
    }
    for question in questions:
        if question.choice_alt == "b" and question.max_marks is None:
            question.max_marks = primary.get(question.question_no)
    return questions


def _resolve_bilingual(questions: list[ExtractedQuestion]) -> list[ExtractedQuestion]:
    """One row per address, keeping the printing a person can actually read.

    A CBSE paper prints every question twice, once per language. Keeping both doubles
    every mark total; keeping whichever came first keeps the Devanagari, which extracts
    as punctuation because the font carries no usable cmap. The Latin ratio decides, and
    marks are taken from whichever printing carried them -- the mark label is language
    independent and is sometimes only on one of the two.
    """
    sectioned = any(q.section for q in questions)
    best: dict[tuple[str, str | None, str | None], ExtractedQuestion] = {}
    for question in questions:
        if len(question.stem_text) < MIN_STEM_CHARS and question.max_marks is None:
            continue
        if sectioned and question.section is None:
            # A question outside every section on a sectioned paper comes from the cover
            # or the instructions page. It is furniture, not a question.
            continue
        key = question.identity
        seen = best.get(key)
        if seen is None:
            best[key] = question
            continue
        marks = question.max_marks if question.max_marks is not None else seen.max_marks
        if readable_letters(question.stem_text) > readable_letters(seen.stem_text):
            question.max_marks = marks
            best[key] = question
        else:
            seen.max_marks = marks
    return list(best.values())


def _check(out: PaperExtract) -> None:
    """Everything the extraction can be held to, said plainly."""
    if not out.questions:
        out.problems.append("no questions were found in a paper that does carry text")
        return

    missing = [q.address for q in out.questions if q.max_marks is None]
    if missing:
        out.problems.append(
            f"{len(missing)} question(s) carry no mark label: {', '.join(missing[:8])}"
            + (" ..." if len(missing) > 8 else "")
        )

    # The count a paper declares is of questions. The second half of an internal choice is
    # not another question -- counting it made a correct 39-question extraction report as
    # 46 and look broken.
    primaries = [q for q in out.questions if q.choice_alt is None]
    if out.declared_count and len(primaries) != out.declared_count:
        out.problems.append(
            f"the paper declares {out.declared_count} questions and "
            f"{len(primaries)} were found"
        )

    numbers = sorted({int(q.question_no) for q in primaries if q.question_no.isdigit()})
    gaps = [n for n in range(1, (numbers[-1] if numbers else 0) + 1) if n not in numbers]
    if gaps:
        out.problems.append(f"question numbers missing from the paper: {gaps[:12]}")

    for letter, declared in out.declared_sections.items():
        found = sum(
            q.max_marks or 0.0
            for q in out.questions
            if q.section == letter and q.choice_alt in (None, "a")
        )
        if abs(found - declared) > 0.01:
            out.problems.append(
                f"section {letter} declares {declared:g} marks, {found:g} were found"
            )
