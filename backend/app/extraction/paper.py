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

#: a mark label in its bare form, for the span-level split below
_BARE_NUMBER = re.compile(r"^\d{1,2}$")

#: 'SECTION A', 'SECTION-B', 'Section C'. The middot is not decorative: a dash whose glyph
#: is missing from the embedded font extracts as one. Any letter, not A to E: how many
#: sections a paper has is the paper's business, and a Section F went unrecognised, which
#: filed every question under it as belonging to no section at all.
SECTION = re.compile(r"^\s*SECTION\s*[-–—·]?\s*([A-Z])\b", re.IGNORECASE)
#: '1.', '21 .', '39.' at the start of a line -- the question number as the paper prints it
QUESTION = re.compile(r"^\s*(\d{1,2})\s*\.\s*(.*)$", re.DOTALL)
#: '(i)', '(ii)', '(iii)' at the start of a line -- a sub-part. Roman only: CBSE numbers
#: sub-parts in roman and internal choices in latin, and conflating the two made every
#: '(a)' in a paper look like a part of a question.
SUB_PART = re.compile(r"^\(\s*(i{1,3}|iv|vi{0,3}|ix|x)\s*\)\s*(.*)$")
#: '(a)', '(b)', '(c)' -- a lettered part of a question. Lower case only, because an MCQ
#: prints its options as '(A) (B) (C) (D)' and those are not parts of anything.
#:
#: Whether the lettered parts are an internal choice or sub-parts is NOT decided here,
#: because it is not a property of the marker: 'OR' between them makes them a choice and
#: nothing else does. A paper that asks 1(a), 1(b) and 1(c) for 1, 2 and 3 marks is worth
#: six, and reading its letters as choices made it worth one.
LETTERED_PART = re.compile(r"^\(\s*([a-h])\s*\)\s*(.*)$")
#: the internal-choice marker, in the languages this pilot sees. Whitespace is stripped
#: before matching: the word is often letter-spaced for emphasis and extracts as 'O R',
#: which the plain word never matched, so every choice in the paper was read as more of
#: the question before it.
OR_MARKER = re.compile(r"^(OR|अथवा|அல்லது)$", re.IGNORECASE)
#: 'Maximum Marks: 80' on the cover. The total the paper claims for itself, and the one
#: figure that catches a mark this reader failed to see anywhere on any page.
DECLARED_TOTAL = re.compile(
    r"(?:maximum|max\.?|total)\s*marks\s*[:\-–—]?\s*(\d{1,3})\b", re.IGNORECASE
)
#: 'This section comprises 20 questions of 1 mark each.' -- printed under every section
#: heading, and the same self-check one section at a time.
SECTION_COMPRISES = re.compile(
    r"comprises\s+(\d{1,3})\s+[a-z\- ]{0,40}?questions?\s+of\s+"
    r"(\d{1,2}(?:\.\d)?)\s*marks?\s+each",
    re.IGNORECASE,
)
#: 'Section A : Biology (30 marks)' in the instructions block
DECLARED_SECTION = re.compile(
    r"Section\s+([A-Z])\s*[:\-]?\s*([A-Za-z ]{0,30}?)\s*\((\d{1,3})\s*marks?\)",
    re.IGNORECASE,
)
DECLARED_COUNT = re.compile(r"contains?\s+(\d{1,3})\s+questions?", re.IGNORECASE)

#: A scanned page yields at most a header and a stamped page number. Below this per page,
#: with images present, the document is a picture of a paper rather than a paper.
SCAN_CHARS_PER_PAGE = 25
#: A stem shorter than this is a fragment, not a question.
MIN_STEM_CHARS = 12


def is_or_marker(text: str) -> bool:
    """Is this line the word OR standing alone?

    Whitespace is removed first. Papers letter-space the word to set it apart, and
    'O R' is what that extracts as.
    """
    squeezed = "".join(text.split())
    return bool(squeezed) and len(squeezed) <= 8 and bool(OR_MARKER.match(squeezed))


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
    #: This row is the shared stem of its sub-parts, not a question worth marks of its
    #: own. A case study prints a paragraph of context and then (i), (ii), (iii); the
    #: paragraph is worth nothing on its own and counting it as a question made the paper
    #: read as three 1-mark questions where it has three worth four.
    is_context: bool = False
    #: set while parsing, cleared by the passes below -- see _classify_lettered_parts
    provisional_sub_part: bool = False
    provisional_choice: bool = False
    #: '(a)', '(b)', '(c)' as printed, before anything has decided what they mean
    lettered_part: str | None = None
    #: whether the word OR stood between this part and the one before it
    preceded_by_or: bool = False

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

    declared_total: float | None = None

    @property
    def total_marks(self) -> float:
        """What the paper is worth, counting each mark exactly once.

        One half of an internal choice, because a student answers one of the two. Never a
        context stem, whose marks live on its sub-parts.
        """
        return sum(
            q.max_marks or 0.0
            for q in self.questions
            if q.choice_alt in (None, "a") and not q.is_context
        )


def readable_letters(text: str) -> int:
    """How much of this stem a person could actually read.

    The bilingual discriminator, and it counts rather than takes a ratio. A ratio was the
    obvious choice and was wrong: the Hindi printing of an MCQ extracts as nothing but its
    option markers, "(A) (B) (C) (D)", whose only letters are Latin -- so it scored a
    perfect ratio of 1.0 and beat the English printing every time. Counting cannot be
    fooled that way: four letters is four letters, and the English stem has ninety.
    """
    return sum(1 for c in text if c.isalpha() and "LATIN" in unicodedata.name(c, ""))


def _split_trailing_mark(spans: list[dict], width: float) -> tuple[list[dict], list[dict]]:
    """Separate a mark label that shares its row with the stem it belongs to.

    A paper usually prints the mark on its own row. Sometimes the stem is short enough
    that the typesetter puts the label at the right margin of the same row, and then the
    two arrive as one visual line: question 23 of the pilot paper read as "... the missing
    frequency f. 2" and was recorded as carrying no marks at all.

    Three conditions together, because any one alone is a sentence that happens to end in
    a number: the trailing span is nothing but a small whole number, it ends inside the
    right-aligned mark band, and it is set in a different font from the text before it.
    A number that is part of the sentence is set in the sentence's own font and stays
    where it is -- the totals check will then report the shortfall rather than this
    guessing at one.
    """
    body = [s for s in spans if s["text"].strip()]
    if len(body) < 2:
        return spans, []
    last, previous = body[-1], body[-2]
    if not _BARE_NUMBER.match(last["text"].strip()):
        return spans, []
    if not (MARK_BAND[0] <= last["bbox"][2] / (width or 1.0) <= MARK_BAND[1]):
        return spans, []
    if last.get("font") == previous.get("font"):
        return spans, []
    cut = spans.index(last)
    return spans[:cut], spans[cut:]


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
                    stem, mark = _split_trailing_mark(spans, width)
                    for group in (stem, mark):
                        text = "".join(s["text"] for s in group)
                        characters += len(text.strip())
                        if not text.strip():
                            continue
                        x0 = min(s["bbox"][0] for s in group)
                        x1 = max(s["bbox"][2] for s in group)
                        top = min(s["bbox"][1] for s in group)
                        lines.append(Line(text, number, top, x0, x1 / width, width))
    lines.sort(key=lambda line: (line.page, round(line.top, 1), line.left))
    return lines, pages, characters, images


#: A line shorter than this cannot be told apart from a mark label or a table cell, and
#: those legitimately repeat on every page.
FURNITURE_MIN_CHARS = 12
#: Repeating on this many pages is what makes a line furniture rather than a coincidence.
FURNITURE_PAGES = 3


def _drop_furniture(lines: list[Line], pages: int) -> list[Line]:
    """Remove the running header and footer printed on every page.

    An internal choice that falls at a page break puts the footer, the next page's header
    and the school's name between the word OR and the alternative it introduces. The
    alternative to question 27 was recorded as "Bharat International Senior Secondary
    School x Yaadhum" -- a stem no student ever answered.

    Furniture is what repeats: the same line, with its page number blanked, on three or
    more pages. Short lines are exempt because a mark label is a short line and "2"
    repeats on every page of every paper.
    """
    if pages < FURNITURE_PAGES:
        return lines
    seen: dict[str, set[int]] = {}
    for line in lines:
        shape = _furniture_shape(line)
        if shape:
            seen.setdefault(shape, set()).add(line.page)
    repeating = {
        shape for shape, on in seen.items() if len(on) >= FURNITURE_PAGES
    }
    return [
        line for line in lines
        if not (
            (shape := _furniture_shape(line))
            and shape in repeating
            and _marks_on(line) is None
        )
    ]


def _furniture_shape(line: Line) -> str | None:
    """The line with its page number blanked, or None if it is too short to judge."""
    text = " ".join(line.text.split())
    if len(text) < FURNITURE_MIN_CHARS:
        return None
    return re.sub(r"\d+", "#", text)


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


def _declared(lines: list[Line]) -> tuple[dict[str, float], int | None, float | None]:
    """What the paper says about itself, which is what the extraction is held to."""
    blob = "\n".join(line.text for line in lines[:220])
    sections = {
        letter.upper(): float(marks)
        for letter, _subject, marks in DECLARED_SECTION.findall(blob)
    }

    # 'This section comprises 6 questions of 3 marks each', printed under each heading.
    # Walked in order because the sentence names no section: it means the one above it.
    section: str | None = None
    for line in lines:
        heading = SECTION.match(line.text.strip())
        if heading:
            section = heading.group(1).upper()
            continue
        comprises = SECTION_COMPRISES.search(line.text)
        if comprises and section and section not in sections:
            sections[section] = float(comprises.group(1)) * float(comprises.group(2))

    count = DECLARED_COUNT.search(blob)
    total = DECLARED_TOTAL.search(blob)
    return (
        sections,
        int(count.group(1)) if count else None,
        float(total.group(1)) if total else None,
    )


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

    lines = _drop_furniture(lines, pages)
    declared_sections, declared_count, declared_total = _declared(lines)
    out = PaperExtract(
        route="text", page_count=pages,
        declared_sections=declared_sections, declared_count=declared_count,
        declared_total=declared_total,
    )

    section: str | None = None
    current: ExtractedQuestion | None = None
    #: the question a sub-part or an alternative belongs to. In CBSE an internal choice
    #: prints the alternative UNNUMBERED after the word OR, so it inherits the address of
    #: the row just closed -- treating the next numbered question as the alternative made
    #: every following question the choice-half of the one before it.
    last_closed: ExtractedQuestion | None = None
    after_or = False
    collected: list[ExtractedQuestion] = []

    def close() -> None:
        nonlocal current, last_closed
        if current is not None:
            current.stem_text = " ".join(current.stem_text.split())[:4000]
            collected.append(current)
            last_closed = current
            current = None

    def open_row(
        question_no: str, sub_part: str | None, choice_alt: str | None,
        stem: str, page: int,
    ) -> ExtractedQuestion:
        nonlocal current
        close()
        current = ExtractedQuestion(
            section=section, question_no=question_no, sub_part=sub_part,
            choice_alt=choice_alt, max_marks=None, stem_text=stem, logical_page=page,
        )
        return current

    for line in lines:
        text = line.text.strip()

        heading = SECTION.match(text)
        if heading:
            close()
            section = heading.group(1).upper()
            last_closed = None
            after_or = False
            continue

        if is_or_marker(text):
            close()
            after_or = True
            continue

        marks = _marks_on(line)
        if marks is not None:
            if current is not None and current.max_marks is None:
                current.max_marks = marks
            continue

        start = QUESTION.match(text)
        if start and line.left < line.page_width * 0.22:
            after_or = False
            rest = start.group(2)
            # '22. (a) Find the mean ...' -- a lettered part printed on the number's own
            # line. Whether it is half a choice or the first of several sub-parts is
            # settled once the whole question has been read, not here.
            opening = LETTERED_PART.match(rest.strip())
            row = open_row(
                start.group(1), None, None,
                opening.group(2) if opening else rest,
                line.page,
            )
            if opening:
                row.lettered_part = opening.group(1)
                row.provisional_sub_part = True
            continue

        anchor = current or last_closed
        if anchor is not None and line.left < line.page_width * 0.35:
            sub = SUB_PART.match(text)
            if sub:
                # '(iii) (a) Find the total surface area.' -- a sub-part that is itself an
                # internal choice. Both markers are on the one line.
                body = sub.group(2).strip()
                inner = LETTERED_PART.match(body)
                row = open_row(
                    anchor.question_no, sub.group(1).lower(),
                    inner.group(1) if inner else None,
                    inner.group(2) if inner else body, line.page,
                )
                row.provisional_sub_part = True
                row.provisional_choice = inner is not None
                after_or = False
                continue

            lettered = LETTERED_PART.match(text)
            if lettered:
                # '(b) The following table shows ...' -- another lettered part of the
                # question above. Whether the OR came first is recorded and decides, once
                # the question is complete, whether these letters are a choice.
                row = open_row(
                    anchor.question_no, anchor.sub_part, None,
                    lettered.group(2), line.page,
                )
                row.lettered_part = lettered.group(1)
                row.provisional_sub_part = True
                row.preceded_by_or = after_or
                after_or = False
                continue

        if current is None and after_or and last_closed is not None and len(text) > MIN_STEM_CHARS:
            # Unnumbered text after an OR: the second alternative, unmarked as such.
            open_row(
                last_closed.question_no, last_closed.sub_part, "b", text, line.page,
            )
            after_or = False
            continue

        if current is not None:
            current.stem_text += " " + text

    close()

    # Order matters. A part with no mark of its own is text and folds back into the stem
    # first, so that only the parts a paper really marks separately are then classified.
    collected = _demote_unmarked_sub_parts(collected)
    collected = _classify_lettered_parts(collected)
    collected = _demote_unpaired_choices(collected)
    out.questions = _mark_context_rows(
        _inherit_choice_marks(_resolve_bilingual(collected))
    )
    _check(out)
    return out


def _demote_unmarked_sub_parts(
    questions: list[ExtractedQuestion],
) -> list[ExtractedQuestion]:
    """A sub-part becomes its own row only when it carries its own mark label.

    This is the rule that keeps the split honest. "(iii) (a) Find the total surface area.
    2" is a question worth two marks and has to be addressed separately or its two marks
    are lost. "(ii) not black", the tail of a wrapped sentence in question 24, carries no
    label and is not a question at all -- it is text, and it goes back into the stem it
    came from, exactly where it was.
    """
    out: list[ExtractedQuestion] = []
    for question in questions:
        if question.provisional_sub_part and question.max_marks is None:
            parent = next(
                (
                    q for q in reversed(out)
                    if q.question_no == question.question_no
                    and q.sub_part is None and q.lettered_part is None
                ),
                None,
            )
            if parent is not None:
                marker = f"({question.sub_part or question.lettered_part})"
                if question.choice_alt:
                    marker += f" ({question.choice_alt})"
                parent.stem_text = " ".join(
                    f"{parent.stem_text} {marker} {question.stem_text}".split()
                )[:4000]
                continue
        question.provisional_sub_part = False
        out.append(question)
    return out


def _classify_lettered_parts(
    questions: list[ExtractedQuestion],
) -> list[ExtractedQuestion]:
    """Decide what a question's (a), (b), (c) mean, from the paper rather than the letter.

    The word OR between them is the whole of the evidence, and it is the only thing that
    can be evidence: the letters look identical either way.

      21. (a) ...  OR  (b) ...        one question, answered once, worth its marks once
      21. (a) 1    (b) 2    (c) 3     one question worth six, in three separately marked
                                      parts a student answers all of

    Reading the second shape as the first is how a six-mark question came out worth one.
    A single lettered part is neither: nothing is being chosen between and nothing is
    being divided, so the letter goes back into the stem where it was printed.
    """
    groups: dict[tuple[str, str | None], list[ExtractedQuestion]] = {}
    for question in questions:
        if question.lettered_part:
            groups.setdefault(
                (question.question_no, question.sub_part), []
            ).append(question)

    for members in groups.values():
        if len(members) == 1:
            only = members[0]
            only.stem_text = " ".join(
                f"({only.lettered_part}) {only.stem_text}".split()
            )[:4000]
            only.provisional_sub_part = False
        elif any(m.preceded_by_or for m in members):
            for member in members:
                member.choice_alt = member.lettered_part
                member.provisional_sub_part = False
        else:
            for member in members:
                member.sub_part = member.lettered_part
        for member in members:
            member.lettered_part = None
    return questions


def _demote_unpaired_choices(
    questions: list[ExtractedQuestion],
) -> list[ExtractedQuestion]:
    """An '(a)' with no '(b)' anywhere was never a choice.

    Reading '(a)' as the first half of an internal choice is a guess until the second half
    turns up. A paper that opens a question with a lettered part and never offers an
    alternative would otherwise be recorded as a paper full of choices nobody can take.
    """
    partners = {
        (q.question_no, q.sub_part) for q in questions if q.choice_alt == "b"
    }
    for question in questions:
        if question.provisional_choice and question.choice_alt == "a":
            if (question.question_no, question.sub_part) not in partners:
                question.stem_text = " ".join(
                    f"(a) {question.stem_text}".split()
                )[:4000]
                question.choice_alt = None
        question.provisional_choice = False
    return questions


def _mark_context_rows(questions: list[ExtractedQuestion]) -> list[ExtractedQuestion]:
    """Flag the shared stem of a question whose sub-parts carry the marks."""
    with_sub_parts = {q.question_no for q in questions if q.sub_part}
    for question in questions:
        question.is_context = (
            question.sub_part is None
            and question.question_no in with_sub_parts
            and question.max_marks is None
        )
    return questions


def _inherit_choice_marks(questions: list[ExtractedQuestion]) -> list[ExtractedQuestion]:
    """An internal choice is worth what the question it replaces is worth.

    That is what "attempt either (a) or (b)" means, so a paper often prints the mark label
    once, above the OR. Leaving the alternative unmarked would drop it out of every
    denominator the moment a student answered it.
    """
    primary = {
        (q.question_no, q.sub_part): q.max_marks
        for q in questions
        if q.choice_alt in (None, "a") and q.max_marks is not None
    }
    for question in questions:
        if question.choice_alt == "b" and question.max_marks is None:
            question.max_marks = primary.get((question.question_no, question.sub_part))
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

    # The total the paper prints for itself, against the total that was read off it. This
    # is the check that catches a mark the reader never saw: a sub-part whose label was
    # missed costs marks nothing else notices, because every row that was read looks fine.
    if out.declared_total is not None:
        short = out.declared_total - out.total_marks
        if abs(short) > 0.01:
            out.problems.append(
                f"the paper is worth {out.declared_total:g} marks and "
                f"{out.total_marks:g} were read"
                + (
                    f", so {short:g} are unaccounted for. A question with sub-parts worth "
                    f"different marks is the usual cause: check that each sub-part carries "
                    f"its own mark."
                    if short > 0
                    else ", so more were read than the paper carries. A mark counted twice "
                    "is the usual cause: check the questions with an internal choice."
                )
            )

    both = [
        q.address for q in out.questions
        if q.sub_part is None and q.max_marks is not None
        and any(s.question_no == q.question_no and s.sub_part for s in out.questions)
    ]
    if both:
        out.problems.append(
            "these questions carry marks of their own and also have sub-parts that carry "
            f"marks, so one of the two is wrong: {', '.join(both[:8])}"
        )

    missing = [
        q.address for q in out.questions
        if q.max_marks is None and not q.is_context
    ]
    if missing:
        out.problems.append(
            f"{len(missing)} question(s) carry no mark label: {', '.join(missing[:8])}"
            + (" ..." if len(missing) > 8 else "")
        )

    # The count a paper declares is of questions. The second half of an internal choice is
    # not another question -- counting it made a correct 39-question extraction report as
    # 46 and look broken.
    # A question is a number on the paper. Neither the second half of an internal choice
    # nor a sub-part is another question: counting the choice halves made a correct
    # 39-question extraction report as 46, and counting sub-parts hid six questions that
    # print only as "(a) ... OR ... (b)" and so have no unlettered row at all.
    numbers = sorted({
        int(q.question_no) for q in out.questions if q.question_no.isdigit()
    })
    if out.declared_count and len(numbers) != out.declared_count:
        out.problems.append(
            f"the paper declares {out.declared_count} questions and "
            f"{len(numbers)} were found"
        )

    gaps = [n for n in range(1, (numbers[-1] if numbers else 0) + 1) if n not in numbers]
    if gaps:
        out.problems.append(f"question numbers missing from the paper: {gaps[:12]}")

    for letter, declared in out.declared_sections.items():
        found = sum(
            q.max_marks or 0.0
            for q in out.questions
            if q.section == letter and q.choice_alt in (None, "a") and not q.is_context
        )
        if abs(found - declared) > 0.01:
            out.problems.append(
                f"section {letter} declares {declared:g} marks, {found:g} were found"
            )


def context_addresses(rows) -> set[str]:
    """The addresses among these rows that are a shared stem rather than a question.

    Takes anything with ``question_no``, ``sub_part``, ``max_marks`` and ``address``, so
    the same rule serves both the freshly parsed rows and the staged rows read back from
    the database. It has to be one rule: a stem the reader knows is context and the
    confirm step does not would block a paper from ever being confirmed.
    """
    with_sub_parts = {row.question_no for row in rows if row.sub_part}
    return {
        row.address for row in rows
        if row.sub_part is None
        and row.question_no in with_sub_parts
        and row.max_marks is None
    }
