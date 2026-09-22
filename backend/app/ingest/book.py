"""Extract a chapter's structure and content from an NCERT PDF.

Two decisions, both forced by the real book rather than chosen:

**Section numbers are scoped to the chapter.** A bare ``\\d+\\.\\d+`` finds "28.5
Therefore," in a worked answer in chapter 9 and loads it as a section. Since the chapter
number is known from the filename, the pattern is anchored to it and body-text decimals
cannot pose as headings.

**The prelims table of contents is an oracle.** It lists every section of every chapter,
so an extraction can be *checked* rather than trusted. Without it a missing section is
invisible once loaded -- there is nothing to contradict it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from app.ingest.tamil_text import clean_tamil_text

#: the prelims file: the verification oracle, never content
CONTENTS = "00-contents.pdf"

#: bucket T -- taught as content, so a question using this method is T_VERBATIM
#: "Theorem 1.1 (Fundamental Theorem of Arithmetic) :" carries a parenthetical name
THEOREM = re.compile(r"^\s*Theorem\s+(\d+\.\d+)\s*(?:\([^)]*\))?\s*(\*?)\s*:\s*(.*)$", re.M)
#: Science teaches through Activities where Maths teaches through Theorems -- a labelled,
#: numbered procedure a student has performed, which is taught content by any reading.
#: Harmless on a Maths book, which has none.
ACTIVITY = re.compile(r"^\s*Activity\s+(\d+\.\d+)\s*(\*?)\s*$", re.M)
#: NCERT writes both "Example 3 :" and "Example 3:", so the space is optional -- but the
#: colon is REQUIRED. Without it the pattern matched "Example 2, all the three events..."
#: in running prose, which both invented a chunk and truncated the real one before it.
#: "Example 5* :" -- the asterisk marks it as beyond the examinable set, like an
#: optional exercise, so it is captured and flagged rather than treated as taught content
EXAMPLE = re.compile(r"^\s*Example\s+(\d+)\s*(\*?)\s*(?:\([^)]*\))?\s*:\s*(.*)$", re.M)
#: bucket E -- drilled, so a question resembling this is PRACTISED.
#: The trailing group matters: NCERT writes "EXERCISE 5.4 (Optional)*", and anchoring
#: straight to end-of-line silently dropped it. An optional exercise is also outside the
#: examinable set, so it is worth knowing rather than merely worth matching.
EXERCISE = re.compile(r"^\s*EXERCISE\s+(\d+\.\d+)\s*(\(Optional\)\*?)?\s*$", re.M)
#: bucket E for a book that numbers nothing. Science's QUESTIONS/EXERCISES close a
#: teaching block; History has no single word for it, and end-of-chapter questions sit
#: under 'Discuss', 'Write in brief' or 'Project' instead, each followed by a numbered
#: list a student actually answers. 'Activity' and 'Source' are left out on purpose: a
#: Source is reading material, not a question, and an Activity here is an unnumbered
#: margin prompt beside a figure, not the graded end-of-chapter drill. Matched only after
#: the vertical-heading collapse in read_text -- Science sets its labels one character
#: per line.
#:
#: '(?:\s+\1)*' -- Geography draws its EXERCISES heading sideways, and the text layer
#: reads that back as the same word several times across one line ('EXERCISES  EXERCISES
#: EXERCISES  EXERCISES  EXERCISES') rather than Science's one-character-per-line split.
#: A second rendering quirk for the same underlying problem, absorbed here rather than
#: added to _collapse_vertical, which is built for the other one.
#: case-insensitive: Science sets EXERCISES/QUESTIONS in caps, History sets Discuss and
#: Write in brief in title case, and Political Science sets Exercises in title case too
#: -- one word, three books, three castings of it.
#: "Let's work these/this out" -- Economics' own recurring in-chapter drill prompt,
#: repeated several times through a chapter the same way Discuss is for History. '.'
#: rather than a literal apostrophe: NCERT sets a curly one ('’'), and a PDF's own
#: text layer is not guaranteed to agree with this file's encoding of it.
#: English (First Flight, Footprints without Feet) numbers nothing and has no
#: chapter-scoped sections at all -- see `single_section` in extract_chapter -- but still
#: closes a teaching block with a fixed-name checkpoint rather than a numbered exercise:
#: 'Oral Comprehension Check' repeats through a story at each reading break, 'Think about
#: it' and 'Talk about it' close it. Real names, read off the actual jeff1xx/jefp1xx
#: files, not the wider "Thinking about the Text"/"Working with Words" naming the older
#: (pre-rationalisation) edition used, which is not what these files contain.
BARE_DRILL_LABEL = re.compile(
    r"^\s*(QUESTIONS|EXERCISES|Discuss|Write in brief|Project|Let.s work (?:these|this) out|"
    r"Oral Comprehension Check|Think about it|Talk about it)"
    r"(?:\s+\1)*\s*$",
    re.M | re.I,
)

#: 'अभ्यास' ("Abhyas") is the standard NCERT Hindi word for an end-of-chapter exercise
#: block, the same way 'EXERCISES' is standard across the English books -- not specific to
#: any one of Kshitij/Kritika/Sparsh/Sanchayan. Kept even though it did not fire on the
#: first real chapter checked (jhkr101.pdf, Kritika's माता का अँचल): that book sets the
#: heading as decorative art rather than plain text, and Tesseract renders the artwork as
#: unrecognisable noise, not the word itself -- HINDI_NUMBERED_QUESTION below is what
#: actually catches that chapter's exercises. A book that sets the heading as plain text
#: still needs this.
HINDI_DRILL_LABEL = re.compile(r"^\s*अभ्यास\s*$", re.M)

#: Tamil's own fixed end-of-chapter heading, confirmed against the real jhtl101-equivalent
#: chapter file (chapter 1): a standing phrase introducing the questions that close a
#: literature chapter, the same role 'EXERCISES'/'अभ्यास' play elsewhere in this module.
#: Trailing dots vary (the real heading ends in an ellipsis).
TAMIL_DRILL_LABEL = re.compile(r"^\s*கற்பவை\s+கற்றபின்\.*\s*$", re.M)

#: Some First Flight chapters (Two Stories about Flying, The Sermon at Benares, The
#: Proposal -- jeff103/108/109) close a story, poem or play with a plain numbered
#: question list and NO fixed label at all in front of it: the play's own last line
#: ('CURTAIN') is followed directly by '1.\nWhat does Chubukov at first suspect...',
#: nothing named 'Exercises' or 'Think about it' anywhere. '\d{1,2}\.' with the text on
#: the FOLLOWING line -- as opposed to BOOK_NUMBERED_SECTION's same-line shape -- is what
#: a real end-of-chapter question looks like everywhere in this book, so it is trusted
#: here despite carrying no label, unlike a numbered *heading* in a book that does number
#: its headings (History), which would be far too easy to fake this way.
ENGLISH_NUMBERED_QUESTION = re.compile(r"^[ \t]*(\d{1,2})\.[ \t]*\n(?=[A-Z(\"'‘’])", re.M)

#: Hindi's own shape of the same "no fixed label" case, confirmed against the real
#: jhkr101.pdf (Kritika, chapter 1, माता का अँचल): its exercises begin directly after the
#: story's last line with no heading text at all -- HINDI_DRILL_LABEL's 'अभ्यास' is set as
#: decorative art there and Tesseract renders it as unrecognisable noise, never the word.
#: Devanagari sets each question on the SAME line as its number (unlike English's Latin
#: layout, where the number sits alone on its own line), and Tesseract drops question 1's
#: leading digit the same way it drops chapter 1's on a contents page (see
#: _recover_hindi_first_chapter_number) -- the digit group is optional so a bare '. <text>'
#: still counts.
HINDI_NUMBERED_QUESTION = re.compile(r"^[ \t]*(\d{1,2})?\.[ \t]+(?=[ऀ-ॿ])", re.M)

#: Tamil's own shape of the same numbered-list-under-a-fixed-heading pattern (see
#: TAMIL_DRILL_LABEL): the number and a trailing tab sit alone on their own line, like
#: English's layout rather than Hindi's same-line one, with the question text starting on
#: the next line -- confirmed against the real chapter 1 file, where each question opens
#: with a quotation mark rather than a bare Tamil letter, hence the quote characters in
#: the lookahead alongside the Tamil block itself.
TAMIL_NUMBERED_QUESTION = re.compile(r"^[ \t]*(\d{1,2})\.[ \t]*\n(?=[ \t]*[஀-௿\"“])", re.M)
#: The one place a bare numbered list is NOT a student exercise: 'WHAT YOU CAN DO', a
#: teacher-facing box of classroom instructions ('1.\nRead and discuss the following
#: extract... with the students'), sitting right beside real exercises the same shape.
#: Its own numbered list starts within a few characters of the label, so a short lookback
#: is enough to tell the two apart without having to delimit the whole box.
_TEACHER_INSTRUCTION_LABEL = "WHAT YOU CAN DO"


@dataclass(frozen=True)
class Section:
    number: str          # '12.2'
    title: str           # 'Volume of Combination of Solids'
    start: int = -1      # character offset of the heading, for body-text attribution
    end: int = -1


@dataclass(frozen=True)
class Chunk:
    bucket: str          # 'T' | 'E'
    kind: str            # 'body' | 'theorem' | 'activity' | 'example' | 'exercise'
    reference: str       # 'Theorem 1.3', 'Example 4', 'EXERCISE 12.1'
    text: str
    stem_hash: str
    section: str = ""    # '2.2' -- which section this came from
    #: an optional exercise is not examinable, so a question resembling it should not
    #: count as "practised" for board-facing reporting
    examinable: bool = True


@dataclass
class ChapterExtract:
    number: int
    title: str
    source_path: str
    sha256: str
    sections: list[Section] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    #: populated by verify_against_toc; empty means the extraction agrees with the book
    problems: list[str] = field(default_factory=list)
    #: Real, worth surfacing, but never a reason to discard a chapter's real content: a
    #: missing drill marker is at least as likely to mean "this chapter's exercises use a
    #: heading this pattern hasn't seen" as "this chapter genuinely has none" -- unlike a
    #: TOC disagreement, which really does mean the wrong file was uploaded.
    warnings: list[str] = field(default_factory=list)
    #: What the extraction was actually checked against. None means no section-level
    #: oracle existed -- the Science contents page lists chapters only -- and every
    #: section number from this chapter must stay visibly unverified downstream. An
    #: unverified number that looks like a verified one is the failure this field exists
    #: to prevent.
    verified_against: str | None = None

    @property
    def ok(self) -> bool:
        return not self.problems

    def counts(self) -> dict[str, int]:
        out = {"sections": len(self.sections), "body": 0, "theorem": 0, "activity": 0,
               "example": 0, "exercise": 0}
        for c in self.chunks:
            out[c.kind] = out.get(c.kind, 0) + 1
        return out


def normalise(text: str) -> str:
    """Fold presentation noise. Digits survive -- they are what make a stem specific."""
    return re.sub(r"\s+", " ", text).strip()


#: en dash, em dash and a doubled hyphen all appear for the same mark: NCERT prints
#: "Light – Reflection and Refraction" with an en dash, source files carry "--", and a
#: reprint may switch either way.
_DASHES = re.compile(r"\s*(?:--+|[\u2010-\u2015])\s*")

#: A curly apostrophe in the book's own text ("The Thief's Story") against a straight one
#: typed into the curriculum -- the same presentation-only difference the dash folding
#: above exists for. Real mismatch, caught on jefp102.pdf: the contents page reads
#: "The Thief\u2019s Story", typed here with a plain "'".
_APOSTROPHES = re.compile(r"[\u2018\u2019\u02bc]")


def title_key(text: str) -> str:
    """Compare two spellings of the same chapter title.

    Kept apart from ``normalise`` deliberately: normalise feeds stem_hash, and folding
    characters there would change every hash already stored. This only ever compares
    titles, where the difference between an en dash and two hyphens, or a curly
    apostrophe and a straight one, is presentation and rejecting a correct chapter over
    it would be absurd.
    """
    folded = _APOSTROPHES.sub("'", normalise(text))
    return _DASHES.sub(" - ", folded).casefold()


def stem_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


#: A heading NCERT sets vertically arrives as one character per line. Four is not enough
#: to be sure -- "n" bullet runs and single-letter algebra reach four -- so require five,
#: which "QUESTIONS" (9) and "EXERCISES" (9) clear comfortably.
_MIN_VERTICAL_RUN = 5
#: Fake bold is the same string drawn several times at small offsets. Three is the
#: threshold: two identical consecutive lines happen in real prose, three do not.
_MIN_BOLD_REPEAT = 3


def _collapse_vertical(lines: list[str]) -> list[str]:
    """Rejoin a heading the typesetter set one character per line.

    Science renders EXERCISES and QUESTIONS vertically, so the text layer holds
    'E\\nX\\nE\\nR\\nC\\nI\\nS\\nE\\nS'. Every exercise pattern missed it, which meant no
    Science question could ever be marked PRACTISED -- the drilled bucket was empty and
    nothing said so.

    A run of the same character repeated (five 'n' bullets) is left alone: that is a list,
    not a word.
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and len(lines[j].strip()) == 1 and lines[j].strip().isalnum():
            j += 1
        run = [ln.strip() for ln in lines[i:j]]
        if len(run) >= _MIN_VERTICAL_RUN and len(set(run)) > 1:
            out.append("".join(run))
        else:
            out.extend(lines[i:j])
        out.append(lines[j]) if j < len(lines) else None
        i = j + 1
    return out


def _overlap(acc: str, fragment: str) -> int:
    """Length of the longest prefix of ``fragment`` that ``acc`` already ends with."""
    for k in range(min(len(acc), len(fragment)), 0, -1):
        if acc.endswith(fragment[:k]):
            return k
    return 0


def _collapse_bold(lines: list[str]) -> list[str]:
    """Rebuild a heading that fake bold split across overlapping draws.

    Science draws each heading five times at small offsets, and the text layer records the
    passes interleaved with a bridge line that spans two fragments:

        12.2 (x4) / 12.2 MA / MA (x3) / MAGNETIC FIELD DUE TO A CURRENT
        / GNETIC FIELD DUE TO A CURRENT (x3) / GNETIC FIELD DUE TO A CURRENT-CARRYING
        / ARRYING (x4) / CONDUCTOR (x5)

    Concatenating the fragments is wrong ('MA' + 'MAGNETIC...'), and so is deduplicating
    them ('MAGNETIC FIELD DUE TO A CURRENT' and its '-CARRYING' continuation are not
    duplicates). What is stable is the *overlap*: every fragment either repeats the tail
    of what has been read so far, or extends it. So merge on the longest overlap, and take
    a fragment sharing nothing with the tail as the next line of the heading.

    A run only ever starts at a line opening with a section number, which is what keeps a
    fake-bold 'Activity 1.2' from being glued to the 'Figure 1.2' drawn beside it.
    """
    groups: list[tuple[str, int]] = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and lines[j] == lines[i]:
            j += 1
        groups.append((lines[i], j - i))
        i = j

    out: list[str] = []
    k = 0
    opens_section = re.compile(r"^\s*\d+\.\d+\s+\S")
    #: Where the number is drawn in its own box, it arrives as a bold line of its own and
    #: the title follows as the next fragment -- '13.2' (x5) then 'HOW DO OUR ACTIVITIES
    #: AFFECT THE' (x5). Without this the heading has no number and the section is lost.
    bare_number = re.compile(r"^\s*\d+\.\d+\s*$")
    while k < len(groups):
        line, count = groups[k]
        starts = bool(opens_section.match(line)) or (
            count >= _MIN_BOLD_REPEAT and bool(bare_number.match(line))
        )
        if not starts:
            out.append(line)
            k += 1
            continue

        acc = line.strip()
        k += 1
        while k < len(groups):
            candidate, candidate_count = groups[k]
            fragment = candidate.strip()
            bold = candidate_count >= _MIN_BOLD_REPEAT
            # Science sets its section headings in capitals, and that is the guard that
            # stops a one-character overlap from swallowing the paragraph underneath:
            # 'SCATTERING OF LIGHT' followed by 'The interplay of light...' shares a 'T'.
            if not fragment or any(ch.islower() for ch in fragment):
                break
            if acc.endswith(fragment):        # another pass over the same fragment
                k += 1
                continue
            shared = 0 if bold else _overlap(acc, fragment)
            if shared:
                # Only a bridge line -- one drawn once, between two repeated fragments --
                # extends the tail mid-word. Tested before the section-number check
                # because the first bridge repeats the number: '1.1 CHEMIC' is continued
                # by '1.1 CHEMICAL EQUA', not ended by it.
                acc += fragment[shared:]
            elif opens_section.match(candidate):
                break
            elif bold:
                # A fresh repeated fragment starts the heading's next line. Joined with a
                # space, never on overlap: 'AFFECT THE' and 'ENVIRONMENT?' share a 'T',
                # and merging on it produced 'AFFECT THENVIRONMENT?'.
                acc += " " + fragment
            else:
                break
            k += 1
        out.append(acc)
    return out


def read_text(path: str | Path) -> str:
    """Page text, with the two layout tricks Science uses undone.

    Both are no-ops on a book that does not use them: Maths has no vertical headings and
    no repeated draws, so nothing in it matches either rule.
    """
    # Tried ``sort=True`` here to fix a real page-order bug (see _heading_styled_lines'
    # own note on "Globalisation and the Indian Economy"): it does reorder spans into the
    # page's true reading order, but it also runs every fake-bold repeated draw of the
    # same text together onto ONE line with no separator ('ChineseChineseChineseChinese
    # ToysToysToysToys ininininin IndiaIndiaIndiaIndia' -- confirmed against the real
    # file), instead of the default mode's one-repeat-per-line layout that
    # ``_collapse_bold`` below depends on to dedupe them. That is corrupted chunk text
    # reaching students, a far worse failure than a mis-ordered heading -- reverted.
    with pymupdf.open(path) as doc:
        raw = "\n".join(page.get_text() for page in doc)
    return "\n".join(_collapse_bold(_collapse_vertical(raw.split("\n"))))


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


#: NCERT's own filenames: jemh101 = Maths chapter 1, jesc105 = Science chapter 5. The two
#: trailing characters are the chapter number, and the non-chapter files are exactly the
#: ones whose trailing pair is not digits: 'ps' prelims, 'an' answers, 'a1'/'a2' appendices.
NCERT_CHAPTER = re.compile(r"^[a-z]{3,5}\d(\d{2})$")
NCERT_CONTENTS = re.compile(r"^[a-z]{3,5}\dps$")


def chapter_number(path: str | Path) -> int | None:
    """The chapter this file is, from either naming convention.

    Accepts NCERT's own codes as well as NN-slug, because renaming eighteen files by hand
    before an upload is a requirement with nothing behind it: jemh101 already says
    "chapter 1" unambiguously, and a rename is one more place to make a mistake.

    None for the contents page, the answers and the appendices -- deliberately, since the
    answers file matches EXERCISE 31 times and would load the answer key as practice.
    """
    stem = Path(path).stem
    if m := re.match(r"^(\d{2})-", Path(path).name):
        return int(m.group(1))
    if m := NCERT_CHAPTER.match(stem):
        return int(m.group(1))
    return None


def is_contents(path: str | Path) -> bool:
    """The prelims file, under either convention."""
    name = Path(path).name
    return name == CONTENTS or bool(NCERT_CONTENTS.match(Path(path).stem))


def chapter_files(directory: str | Path) -> list[Path]:
    """The chapter PDFs, and only those.

    Excluded by construction, not by convention: the answers file matches 'EXERCISE' 31
    times and would load the answer key as practice content, and the appendices are
    outside the Class X syllabus. Lives here rather than in the script so the ingest and
    its tests cannot disagree about what counts as a chapter.
    """
    return sorted(
        (p for p in Path(directory).glob("*.pdf") if chapter_number(p) not in (None, 0)),
        key=lambda p: chapter_number(p) or 0,
    )


def parse_toc(contents_pdf: str | Path, *, text: str | None = None) -> dict[int, list[Section]]:
    """The expected section tree, from the prelims file, where the book publishes one.

    Maths lists every section of every chapter here, which is what makes a Maths
    extraction checkable. Science does not -- its contents page stops at chapter titles --
    so this returns empty for Science and the caller must fall back to
    ``verify_structure``. Returning empty is the honest answer; inventing an expectation
    would make an unchecked load look checked.

    ``text``, when given, is used in place of reading ``contents_pdf``'s own text layer --
    a Hindi book's caller has already had that read by app.ingest.gemini_ocr, since the
    PDF's own layer decodes as mojibake.
    """
    text = text if text is not None else read_text(contents_pdf)
    out: dict[int, list[Section]] = {}
    # '[ \t]+', not '\s+': the Workbook's copyright page prints a price as ' 120.00' on
    # its own line, immediately followed by 'Printed on 80 GSM paper with NCERT' on the
    # next -- '\s+' matches straight across that newline and reads the two as one
    # 'chapter.section' heading. A real heading never has its title on the following
    # line; only same-line survives, the same fix BOOK_NUMBERED_SECTION needed for a bare
    # page number swallowing the running header below it.
    for number, title in re.findall(r"^\s*(\d+\.\d+)[ \t]+([A-Z][^\n]{2,120})$", text, re.M):
        chapter = int(number.split(".")[0])
        out.setdefault(chapter, []).append(Section(number, title.strip()))
    return out


#: 'Chapter 9' then the title on the following line, as the Science prelims sets it. The
#: title must not itself start with 'Chapter': a table whose 'Chapter N' labels and titles
#: sit in separate blocks reads, in linear order, as one label followed by the next label,
#: and without this exclusion that reads as a real match instead of the garbage it is.
TOC_CHAPTER = re.compile(r"^\s*Chapter\s+(\d{1,2})\s*$\n^\s*((?!Chapter\b)\S[^\n]{2,80})$", re.M)

#: 'I. The Rise of Nationalism in Europe' then the page number on the following line, as
#: the History prelims numbers its chapters -- it never says 'Chapter'. Titled with an
#: initial capital, like a real title and unlike a stray Roman-numeral bullet elsewhere in
#: the prelims, and anchored to a page number on the next line so a numeral in running
#: text cannot match.
TOC_CHAPTER_ROMAN = re.compile(
    r"^\s*([IVXLCDM]{1,6})\.\s+([A-Z][^\n]{2,120})\n\s*\d{1,4}\s*$", re.M
)

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(numeral: str) -> int:
    total, previous = 0, 0
    for letter in reversed(numeral.upper()):
        value = _ROMAN_VALUES[letter]
        total += -value if value < previous else value
        previous = max(previous, value)
    return total


#: '1.' alone on a line, then the title, then the page number, as the Geography prelims
#: lays its contents out -- neither 'Chapter' nor a Roman numeral, just the plain number.
TOC_CHAPTER_DOTTED = re.compile(
    r"^\s*(\d{1,2})\.\s*\n\s*([A-Z][^\n]{2,120})\n\s*\d{1,4}\s*$", re.M
)

#: '1. A Letter to God' -- number, dot AND title all on the one line -- then the page
#: number on the next, as English's First Flight and Footprints without Feet set their
#: contents. Differs from TOC_CHAPTER_DOTTED only in whether the title shares the
#: number's line; tried after it so a book using the bare-number convention is never
#: mis-read by the looser one. A chapter is followed by its own poem/story titles with no
#: leading number of their own ('Dust of Snow\n14\n...'), which this pattern does not
#: match -- exactly the exclusion that keeps them from being read as further chapters.
TOC_CHAPTER_NUMBERED = re.compile(
    r"^\s*(\d{1,2})\.\s+([A-Z][^\n]{2,120})\n\s*\d{1,4}\s*$", re.M
)

#: 'Unit 1' then the title on the following line, then the page number, as the Workbook
#: prelims sets its contents -- its own word for a chapter is 'Unit', not 'Chapter'.
TOC_CHAPTER_UNIT = re.compile(
    r"^\s*Unit\s+(\d{1,2})\s*\n\s*([A-Z][^\n]{2,120})\n\s*\d{1,4}\s*$", re.M
)


def _toc_chapters_by_position(contents_pdf: str | Path) -> dict[int, str]:
    """Chapter numbers and titles, read by where the words sit on the page.

    The Economics prelims sets its 'Chapter N' labels and their titles as two separate
    blocks of a table -- reading order gives 'Chapter 1', 'Chapter 4', 'Chapter 2' ... in
    one run and every title in another, so line-by-line text matches a label to the wrong
    title, or to none. Word coordinates are what the table actually is, so a label is
    paired with whichever title sits in the row directly below it -- there is no title
    close enough that isn't its own -- rather than with whatever line the linear text
    happened to place next to it.
    """
    with pymupdf.open(contents_pdf) as doc:
        words: list[tuple[int, float, float, str]] = [
            (page_index, y0, x0, text)
            for page_index, page in enumerate(doc)
            for x0, y0, _x1, _y1, text, *_ in page.get_text("words")
        ]
    words.sort(key=lambda w: (w[0], w[1], w[2]))

    # Clustered by nearness to the row's own first word, not by rounding y to a fixed
    # grid: two words 1-2pt apart that straddle a rounded boundary are still one printed
    # line, and rounding split them into two, each too short to look like a title. y
    # jitters within a row too, so which word came first by y is not reading order --
    # each row's words are kept with their x and re-sorted left to right once it is done.
    clusters: list[tuple[int, float, list[tuple[float, str]]]] = []
    for page_index, y0, x0, text in words:
        if (
            clusters and clusters[-1][0] == page_index
            and abs(y0 - clusters[-1][1]) <= 3.5
        ):
            clusters[-1][2].append((x0, text))
        else:
            clusters.append((page_index, y0, [(x0, text)]))
    lines = [
        (page_index, y, [text for _x, text in sorted(row, key=lambda w: w[0])])
        for page_index, y, row in clusters
    ]

    labels = [
        (page_index, y, int(words[1]))
        for page_index, y, words in lines
        if len(words) == 2 and words[0] == "Chapter" and words[1].isdigit()
    ]
    titles = [
        (page_index, y, " ".join(words[:-1]))
        for page_index, y, words in lines
        if len(words) >= 2 and words[-1].isdigit() and words[0] != "Chapter"
    ]

    out: dict[int, str] = {}
    for page_index, y_label, number in labels:
        below = [t for t in titles if t[0] == page_index and t[1] > y_label]
        if not below:
            continue
        nearest = min(below, key=lambda t: t[1] - y_label)
        # A title more than two rows below its label is somebody else's -- Appendix and
        # Suggested Readings both end in a page number too, and sit far past the last
        # chapter label rather than one row under it.
        if nearest[1] - y_label < 40:
            out[number] = nearest[2].title()
    return out


#: The Tamil contents page (www.cbsetamil.com's own book) has no chapter LABEL at all --
#: no 'Chapter N', no leading number, not even on the வ.எண் (unit number) column, which is
#: set once per இயல் (unit) rather than once per chapter. All 36 chapters are numbered
#: purely by their position in a five-column table (unit no. / theme / chapter title /
#: page no. / month), so Economics' "Chapter" + digit label convention above finds nothing
#: here at all. Confirmed against the real contents page (two pages, read with
#: page.get_text("words")): the title and page-number columns sit in narrow, well-separated
#: x-bands regardless of what the unit-number/theme column to their left or the month
#: column to their right happen to be doing at that row's height, which is what makes
#: restricting to those two x-ranges (rather than reading the whole row) work at all -- a
#: naive per-row read glues the unit number, theme, first chapter title and page number of
#: an இயல்'s first row all onto one visual line.
_TAMIL_TITLE_X = (225.0, 440.0)
_TAMIL_PAGENUM_X = (440.0, 495.0)

#: The month column's left edge sits close enough to the page-number column's right edge
#: that a short month name is occasionally picked up by the x-range above too -- confirmed
#: on the real page, 'பாய்ச்சல் 102' with 'அக்டோபர்' glued on, and 'முத்தொள்ளாயிரம்* 129'
#: preceded by a stray solo 'அக்டோபர்' row. Both drop out once matched against this closed
#: set: the book covers June through December in whichever two-word split it prints an
#: english-lettered month name never appears at all, so this can never eat real title text.
_TAMIL_MONTH_NAMES = {
    "ஜூன்", "ஜூலை", "ஆகஸ்டு", "ஆகஸ்ட்", "செப்டம்பர்",
    "அக்டோபர்", "நவம்பர்", "டிசம்பர்",
}


def _tamil_toc_chapters_by_position(contents_pdf: str | Path) -> dict[int, str]:
    """Chapter titles from the Tamil contents page's own column geometry -- see
    _TAMIL_TITLE_X above for why nothing regex-shaped can read this table at all.

    Numbered purely by row order (top to bottom, page 1 then page 2): nothing on the page
    itself labels a chapter '1' through '36', so position is the only oracle there is.
    """
    with pymupdf.open(contents_pdf) as doc:
        words = [
            (page_index, y0, x0, text)
            for page_index, page in enumerate(doc)
            for x0, y0, _x1, _y1, text, *_ in page.get_text("words")
            if _TAMIL_TITLE_X[0] <= x0 < _TAMIL_TITLE_X[1]
            or _TAMIL_PAGENUM_X[0] <= x0 < _TAMIL_PAGENUM_X[1]
        ]
    words.sort(key=lambda w: (w[0], w[1], w[2]))

    clusters: list[tuple[int, float, list[tuple[float, str]]]] = []
    for page_index, y0, x0, text in words:
        if (
            clusters and clusters[-1][0] == page_index
            and abs(y0 - clusters[-1][1]) <= 3.5
        ):
            clusters[-1][2].append((x0, text))
        else:
            clusters.append((page_index, y0, [(x0, text)]))

    out: dict[int, str] = {}
    number = 0
    for _page_index, _y, row in clusters:
        # Each token carries the same font-level glyph-repeat corruption
        # app.ingest.tamil_text exists for -- cleaned before the month check, not after,
        # because the raw token ('அக்டோ�ோபர்') does not exact-match the clean name in
        # _TAMIL_MONTH_NAMES at all. Missing that silently dropped an entire real title
        # row ('பாய்ச்சல் 102') the first time this was tried: an uncleaned month token
        # survives as the row's last token, fails the isdigit check below, and the whole
        # row reads as "not a title" instead of just losing the one stray word.
        tokens = [
            clean_tamil_text(t) for _x, t in sorted(row, key=lambda w: w[0])
            if clean_tamil_text(t) not in _TAMIL_MONTH_NAMES
        ]
        # A real title row always ends with its page number -- a header ('பாடத்தலைப்புகள்
        # ப. எண்'), a page footer (a bare roman numeral), or a stray month row left after
        # the filter above never does.
        if not tokens or not tokens[-1].isdigit():
            continue
        title = " ".join(tokens[:-1]).strip()
        if not title:
            continue
        number += 1
        out[number] = title
    return out


#: '2. साना-साना हाथ जोडि... 40' -- number, dot, Devanagari title, then the page number on
#: the SAME line (unlike TOC_CHAPTER_NUMBERED's English books, which put it on the next).
#: '[ऀ-ॿ]' rather than '[A-Z]', which every other TOC_CHAPTER* pattern anchors on and which
#: cannot match Devanagari at all. Confirmed against the real Kritika prelims, OCR'd with
#: Tesseract at PSM 6 (see app.ingest.hindi_ocr) -- the trailing page number is optional
#: (not just '\d{1,4}') because Tesseract's own reading of it is not reliable enough to
#: require: the real chapter 1 entry OCR'd its page number as a stray '।' (a Devanagari
#: danda, not a digit) even once its own leading '1.' was recovered (see
#: _recover_hindi_first_chapter_number below).
TOC_CHAPTER_DEVANAGARI = re.compile(
    r"^\s*(\d{1,2})\.\s*([ऀ-ॿ][^\n]{1,120}?)\s*[.\-–—\s]*(?:\d{1,4})?\s*$",
    re.M,
)

#: Tesseract, even at PSM 6, dropped the leading digit of a contents page's FIRST chapter
#: entry specifically -- its own '.' survived, the '1' in front of it did not -- while
#: every later entry kept its number intact. Confirmed on the real Kritika prelims: '2.'
#: and '3.' both OCR'd correctly, only '1.' came back as a bare '.'. Recovered here, not
#: guessed: fires only when a bare '.' line is followed somewhere after it by a line that
#: does start '2.' -- specific enough that an unrelated bare-dot bullet elsewhere on the
#: page, with no numbered list around it at all, is never touched. `count=1` because only
#: the FIRST such line is ever the missing chapter 1 -- a book that happens to have a
#: second bare-dot line later is not this bug repeating.
_HINDI_MISSING_FIRST_CHAPTER_NUMBER = re.compile(r"^\.([ \t])", re.M)


def _recover_hindi_first_chapter_number(text: str) -> str:
    if not re.search(r"^2\.[ \t]", text, re.M):
        return text
    return _HINDI_MISSING_FIRST_CHAPTER_NUMBER.sub(r"1.\1", text, count=1)


def parse_toc_chapters(contents_pdf: str | Path, *, text: str | None = None) -> dict[int, str]:
    """Chapter numbers and titles from the contents page.

    Present in most books, and the only thing the Science contents page offers. It still
    verifies something worth verifying: that the file uploaded as chapter 9 is the chapter
    the book calls 9. Tried in the order a book is most likely to use: the word 'Chapter',
    then a bare number before the title (Geography), then a Roman numeral (History, which
    never says 'Chapter'), then position on the page for a table linear text cannot read
    in order (Economics). Each is tried only once the one before it finds nothing, so a
    book that genuinely mixes conventions never has an earlier one swallow a later one's
    numbering.

    ``text``, when given, is used in place of reading ``contents_pdf``'s own text layer --
    a Hindi book's caller has already had that read by app.ingest.gemini_ocr.
    """
    text = text if text is not None else read_text(contents_pdf)
    for pattern, to_number in (
        (TOC_CHAPTER, int),
        (TOC_CHAPTER_DOTTED, int),
        (TOC_CHAPTER_NUMBERED, int),
        (TOC_CHAPTER_UNIT, int),
        (TOC_CHAPTER_DEVANAGARI, int),
        (TOC_CHAPTER_ROMAN, _roman_to_int),
    ):
        haystack = (
            _recover_hindi_first_chapter_number(text) if pattern is TOC_CHAPTER_DEVANAGARI else text
        )
        found = {to_number(n): title.strip() for n, title in pattern.findall(haystack)}
        # A real contents page numbers its chapters 1..N with no gaps. A pattern that
        # matched something -- a stray 'Chapter 5' paired with the word 'Appendix' two
        # lines below it in a table it cannot otherwise read -- but not a complete,
        # contiguous run is a false positive, not a partial answer: better to fall
        # through to the next convention than to record one right chapter and silence
        # the rest.
        if found and set(found) == set(range(1, len(found) + 1)):
            return found
    found = _toc_chapters_by_position(contents_pdf)
    if found:
        return found
    # Tamil's own table has no label at all (see _tamil_toc_chapters_by_position), so it
    # is tried last and only when the page is actually in Tamil script -- restricting it
    # this way means a coordinate band tuned to one specific book's page layout can never
    # silently misfire on an unrelated book that also happens to reach this fallback.
    if re.search(r"[஀-௿]", text):
        return _tamil_toc_chapters_by_position(contents_pdf)
    return found


#: A real NCERT chapter with genuine subheadings (not single_section) runs several
#: thousand characters. Below this, one section is plausibly the whole, short chapter;
#: above it, one section is far more likely a heading-detection failure than a book that
#: really has no internal divisions -- see verify_structure's own note on the real
#: Economics chapter this was measured against (several thousand characters, six real
#: headings, all beaten by a 24pt front-matter note).
SUSPICIOUS_SINGLE_SECTION_CHARS = 3000


def verify_structure(extract: ChapterExtract, *, exercises_required: bool = True) -> ChapterExtract:
    """The checks that survive when the book publishes no section list.

    Weaker than verify_against_toc and deliberately not dressed up as equivalent: nothing
    here can detect a section the extractor never saw at the *end* of a chapter, because
    there is nothing that says how many there should be. What it does catch is a gap in
    the middle -- 9.1, 9.2, 9.4 means 9.3 was missed -- a chapter that yielded no sections
    at all, and one that yielded no drilled content, each of which is a silent hole in the
    knowledge base rather than a visible failure.

    ``exercises_required=False`` (single_section subjects: Tamil, Hindi, English) makes
    the missing-exercises check a warning, not a rejection. Maths and Science number their
    drills consistently enough that "no EXERCISE/QUESTIONS marker found" reliably means
    the chapter has none. A literature chapter's drill heading is matched by a small set of
    fixed phrases confirmed against one real chapter file each (TAMIL_DRILL_LABEL,
    HINDI_DRILL_LABEL) -- a different, unconfirmed phrasing for a chapter that genuinely
    does have exercises is at least as likely as a chapter that truly has none, and
    discarding the chapter's real prose/poem content over that ambiguity is a worse
    outcome than keeping the content and flagging the gap for a person to check.
    """
    numbers = [s.number for s in extract.sections]
    if not numbers:
        extract.problems.append(
            f"chapter {extract.number}: no sections were found, so nothing can be placed "
            f"in it"
        )
        return extract

    # The gap check below assumes 'chapter.section' numbering, tied to this chapter's own
    # number -- true for Maths and Science, and false for a book like History that numbers
    # its own headings independent of the chapter (BOOK_NUMBERED_SECTION in extract_sections
    # picked those up, not chapter.section). Forcing that shape onto a numbering it was
    # never in would report gaps that are not real gaps, so the check is skipped rather
    # than guessed at -- 'at least one section' and 'at least one exercise', both below,
    # still run regardless of which convention produced the sections.
    if all(n.split(".", 1)[0] == str(extract.number) for n in numbers):
        indexes = sorted(int(n.split(".")[1]) for n in numbers if "." in n)
        if indexes and indexes[0] != 1:
            extract.problems.append(
                f"chapter {extract.number}: sections start at "
                f"{extract.number}.{indexes[0]}, so {extract.number}.1 was missed"
            )
        for lower, upper in zip(indexes, indexes[1:], strict=False):
            if upper != lower + 1:
                missing = ", ".join(
                    f"{extract.number}.{n}" for n in range(lower + 1, upper)
                )
                extract.problems.append(
                    f"chapter {extract.number}: missing section {missing}"
                )

    if not any(c.bucket == "E" for c in extract.chunks):
        target = extract.problems if exercises_required else extract.warnings
        target.append(
            f"chapter {extract.number}: no exercises or questions were found, so no "
            f"question from it could ever be judged PRACTISED"
        )

    # One section covering a chapter this long is the exact shape of a real, silent
    # failure: a decorative element (a front-matter note, the chapter's own cover title,
    # an oversized drill label) outscored every real heading and became "the chapter's
    # largest bold text" on its own, so _sections_by_boldness returned it as the ONLY
    # section -- not a smaller heading list, one wearing a heading's shape. Confirmed on
    # a real Economics chapter: "NOTES FOR TEACHERS" at 24pt beat six real headings at
    # 14pt and the whole chapter, several thousand characters, came back as one section
    # named after the front matter. `exercises_required` gates this the same way it gates
    # the missing-exercise check above: single_section subjects (English, Hindi, Tamil)
    # are GENUINELY one continuous piece with no subheading of any kind, so one section
    # there is the true shape of the chapter, not a failure to find more of them.
    if exercises_required and len(numbers) == 1:
        span = extract.sections[0].end - extract.sections[0].start
        if span > SUSPICIOUS_SINGLE_SECTION_CHARS:
            extract.warnings.append(
                f"chapter {extract.number}: only one section was found "
                f"({extract.sections[0].title!r}) across {span} characters of text -- "
                f"this usually means a decorative or front-matter line outscored every "
                f"real heading, not that the chapter genuinely has only one. Check "
                f"GET /platform/books/{{subject}}/concept-families for "
                f"uncovered_sections after loading, and consider re-checking this "
                f"chapter's heading detection before trusting any family proposed from it."
            )
    return extract


#: History numbers its own headings independent of the chapter: a bare major number with
#: no decimal ('1  The Rise of Nationalism in Europe', two spaces, no dot) or a decimal
#: subsection under it ('2.1 The Aristocracy...', one space) -- '2' there is the second
#: heading IN THIS CHAPTER, not chapter 2. Title may start with a digit ('3.3 1848: The
#: Revolution of the Liberals'), which is why this is not anchored to [A-Z] the way the
#: chapter-numbered pattern is. It may also start with an opening quotation mark -- the
#: real "Print Culture and the Modern World" chapter titles its own section 4.1
#: '"Tremble, therefore, tyrants of the world!"' (NCERT's own translated quotation from a
#: French pamphlet), which a letter-or-digit-only start silently skipped entirely --
#: section 4.1 never appeared at all, only 4.2 onward, no truncation to even notice.
#:
#: Matched only against a line already known to be bold (see _sections_by_boldness), not
#: against the plain text of the whole chapter: Political Science's real headings use no
#: number at all, and a *plain* numbered list in its body prose ('1  Power is shared
#: among different organs of government...') matches this exact shape without being a
#: heading. Boldness is the only thing that told the two apart in the real files.
BOOK_NUMBERED_SECTION = re.compile(
    r"^(\d{1,2}(?:\.\d{1,2})?)[ \t]{1,2}([A-Z0-9'\"‘“][^\n]{2,120})$"
)


def _merge_wrapped_title(
    text: str, title: str, start: int, end: int,
    line_sizes: dict[str, float] | None, body_size: float,
) -> tuple[str, int]:
    """A heading's title sometimes continues onto the next physical line -- a plain word
    wrap ('...Extracting Metals towards the Top of the' / 'Activity Series'), or, when
    NCERT's PDF fakes bold by drawing the same heading several times at slightly shifted
    positions, a duplicate-offset copy of the tail ('...Importance of pH in Ever' /
    'tance of pH in Everyday Life', where the second line overlaps the end of the first).
    Confirmed on real chapters -- the single-line-only pattern in extract_sections used to
    silently drop the wrapped tail in both cases, truncating the stored title.

    A plain "short and unpunctuated" test of the next line looked like a safe way to spot
    a continuation, but Science's own narrow-column layout (body prose wrapped alongside
    a figure) breaks it: confirmed on the real "How do Organisms Reproduce?" chapter,
    where "7.2.4 Budding" is followed by five short, punctuation-free body lines
    ("Organisms such as Hydra" / "use regenerative cells for" / ...) that a text-only
    heuristic swallowed wholesale into the title. Body prose and a wrapped heading can
    read identically as plain text; they are never printed identically. Boldness itself
    turned out not to be the reliable signal either -- Science's own heading font
    ('TT5EBT00', an embedded extra-bold subset, the same shape of trick Economics uses)
    carries no bold flag at all, only a size (14.0pt here) visibly larger than the body
    text around it (10.5pt) -- so the test used is font SIZE: a candidate line is a
    continuation only if its size matches the exact size of the heading's own first line.
    Callers with no PDF to read sizes from (a synthetic string in a unit test, not a real
    file) pass ``line_sizes=None`` and nothing is ever merged.

    A test PDF built for an unrelated test sets its whole page -- number, title, body --
    in one uniform font and size, since nothing about that test cares about typography.
    Nothing in this book's real layout tells a genuine heading apart from that kind of
    page by looking at any ONE line, including the heading's own -- only ``body_size``
    (this chapter's own most common size, computed once from the whole document) can:
    confirmed on the real "Statistics" unit test, where matching the heading's own
    literal size against the next line's, with no floor, merged three of its own body
    sentences straight into a section title because the test PDF draws everything at the
    same size. A heading's own line must be visibly larger than that common size before
    its wrapped continuation is trusted at all.
    """
    if not line_sizes:
        return title, end
    # The matched span can itself cross a physical line ('10.4' then 'Summary' below it,
    # see extract_sections' own docstring on that) -- the number and title are then two
    # separate dict-extracted lines, so only the LAST physical line (the title's own) is
    # a real key into line_sizes; the whole span joined by its embedded '\n' never is.
    heading_line = text[start:end].strip().rsplit("\n", 1)[-1]
    reference_size = line_sizes.get(heading_line)
    if reference_size is None or reference_size <= body_size + 1.0:
        return title, end
    # m.end() (the position this is always called with) lands ON the heading line's own
    # trailing newline, not past it -- the $ anchor matches before \n without consuming it.
    pos = end + 1 if text[end:end + 1] == "\n" else end
    for _ in range(5):
        newline = text.find("\n", pos)
        if newline == -1:
            break
        line = text[pos:newline].strip()
        if not line or line_sizes.get(line) != reference_size:
            break
        if re.match(r"^\d+(?:\.\d+)*(?:\s*\([a-z]\))?\s+[A-Z]", line):
            break  # the next real heading, not a continuation
        if re.match(r"^(Activity|Example|Theorem|Exercise|Table|Fig(?:ure)?\.?)\s+\d", line):
            # NCERT sets an Activity/Table/Figure caption right under a heading in the
            # exact same larger size -- confirmed on the real "Acids, Bases and Salts"
            # chapter, where "2.1.1 Acids and Bases in the Laboratory" is immediately
            # followed by "Activity 2.1" at the identical size, which the merge above
            # would otherwise read as a continuation and glue onto the title.
            break
        overlap = 0
        for n in range(min(len(title), len(line)), 2, -1):
            if title[-n:] == line[:n]:
                overlap = n
                break
        title = (title[:-overlap] + line) if overlap else f"{title} {line}"
        pos = newline + 1
        if title[-1] in ".?!":
            break
    return title, pos


def extract_sections(
    text: str, chapter: int, path: str | Path | None = None
) -> list[Section]:
    """Headings for THIS chapter only, with the span each one covers.

    The scoping is the whole point: 'Example 5 : ... = 28.5 m\nTherefore, ...' produced a
    phantom section '28.5 Therefore,' when the pattern was chapter-agnostic.

    Matches up to TWO decimal levels ('1.2' and '1.2.3') -- Science numbers real
    subsections one level deeper than its own top-level sections (e.g. '1.1.1 Writing a
    Chemical Equation' under '1.1 Chemical Equations'), which a one-level-only pattern
    left entirely invisible: not a smaller heading list, an emptier one silently missing
    every real subsection a chapter has, confirmed on the real "Chemical Reactions and
    Equations" chapter (12 real numbered subheadings, only the 3 top-level ones found).

    A THIRD level under a two-decimal section switches from another digit to a
    parenthesised letter instead ('7.3.3 (a) Male Reproductive System', '7.3.3 (b)
    Female Reproductive System' -- four real headings under 'Reproduction in Human
    Beings' on the real "How do Organisms Reproduce?" chapter), matched as its own
    alternative rather than folded into the two-decimal case since it is a genuinely
    different convention, not a third digit.

    A title normally starts with a capital letter, except a real heading that legitimately
    starts with the chemistry symbol 'pH' ('2.4.2 pH of Salts') -- correct notation, not a
    typo, so it is its own explicit exception rather than forcing every book's convention
    to fit one heading. Maths has the same case for its own notation: '5.3 nth Term of an
    AP' on the real "Arithmetic Progressions" chapter -- 'nth' is standard mathematical
    shorthand, not a typo either.

    A number and its title are usually on one physical line, but not always -- pymupdf's
    real text layer for the "Circles" chapter splits '10.4 Summary' onto two lines ('10.4'
    then 'Summary' below it), which a same-line-only pattern would silently lose. '\s+'
    between them (allowing a single line break) recovers that real heading. But the same
    chapter ALSO splits 'EXERCISE 10.2' across two lines ('EXERCISE' then '10.2' alone),
    leaving a bare '10.2' immediately followed by the exercise's own instruction line ('In
    Q.1 to 3, choose the correct option and give justification.') -- '\s+' reads that as a
    heading too, and since the instruction sentence is longer than the real '10.2 Tangent
    to a Circle' heading found elsewhere in the chapter, the longest-wins dedup (see its
    own comment below) picked the fake one. The negative lookbehind excludes only that
    specific shape: a number whose immediately preceding line is the literal word
    'EXERCISE', the one place a bare number is never a section heading.
    """
    pattern = re.compile(
        rf"^\s*(?<!EXERCISE\n)({chapter}\.\d+\.\d+\s*\([a-z]\)|{chapter}\.\d+(?:\.\d+)?)"
        rf"\s+([A-Z][^\n]{{2,120}}|pH[^\n]{{2,120}}|nth[^\n]{{2,120}})$",
        re.M,
    )
    # A heading can be rendered as several overlapping, differently-truncated copies at
    # nearly the same position -- a faux-bold trick some PDF generators use, confirmed on
    # the real "2.3.1 Importance of pH in Everyday Life" heading, drawn as four truncated
    # "2.3.1 Impor" duplicates plus the one real, longer line. The FIRST copy in the text
    # stream must not win just because it came first -- keeping the LONGEST candidate for
    # a given number instead fixes that case and does no harm to the ordinary one (a
    # running header repeating the exact same short title on every page), since the
    # longest of several identical copies is still that same text.
    best: dict[str, tuple[str, int, int]] = {}
    for m in pattern.finditer(text):
        number = m.group(1)
        title = m.group(2).strip()
        # A PDF's text layer sometimes runs a subsection heading and its opening
        # sentence onto one physical line with no newline between them -- confirmed on
        # the real "Pair of Linear Equations" chapter, where "3.3.1 Substitution Method
        # : We shall explain the method..." is one line in the extracted text. NCERT's
        # own convention marks that boundary with " : ", the same separator it uses for
        # Theorem/Example labels, so truncating there recovers the real heading
        # ("Substitution Method") instead of swallowing the sentence after it.
        colon = title.find(" : ")
        if colon != -1:
            title = title[:colon].strip()
        current = best.get(number)
        if current is None or len(title) > len(current[0]):
            best[number] = (title, m.start(), m.end())
    found = sorted(
        ((number, title, start, end) for number, (title, start, end) in best.items()),
        key=lambda item: item[2],
    )

    line_sizes: dict[str, float] | None = None
    body_size = 0.0
    if path is not None and found:
        with pymupdf.open(path) as doc:
            line_sizes = {}
            size_chars: dict[float, int] = {}
            for page in doc:
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        spans = line.get("spans") or []
                        line_text = "".join(s["text"] for s in spans).strip()
                        if line_text and spans:
                            size = round(spans[0]["size"], 1)
                            line_sizes[line_text] = size
                            size_chars[size] = size_chars.get(size, 0) + len(line_text)
            # The size used everywhere for the most characters is this chapter's own body
            # text -- the same "most common size" reasoning _sections_by_boldness already
            # uses for Economics' own un-bold headings.
            if size_chars:
                body_size = max(size_chars, key=lambda s: size_chars[s])
    merged = []
    for number, title, start, end in found:
        title, end = _merge_wrapped_title(text, title, start, end, line_sizes, body_size)
        merged.append((number, title, start, end))
    found = merged

    # A real book's first subsection index is 1, 2, or 3 -- never a book with genuine
    # chapter.section numbering opens at .74. A table cell (a percentage in a language
    # table, in the book that first showed this) coincidentally starting with this
    # chapter's own digit, followed by the next row's capitalised entry, matches the
    # pattern above exactly as well as a real heading does. Discarded rather than kept
    # and reported as a gap: this book does not use chapter.section numbering at all, so
    # falling through to try the conventions that do not assume it is the honest answer.
    if found and min(int(n.split(".")[1]) for n, *_ in found) > 3:
        found = []

    sections: list[Section] = []
    for i, (number, title, _start, heading_end) in enumerate(found):
        end = found[i + 1][2] if i + 1 < len(found) else len(text)
        sections.append(Section(number, title, heading_end, end))
    return sections


#: below this a "body" slice is a page header or a stray caption, not taught content
MIN_BODY_CHARS = 200

#: Real production bug: X.HIN.KR's /embed 502'd with Jina's own "Input text exceeds the
#: model's maximum of 32768 tokens" -- a single_section Hindi chapter has no subheadings
#: to split its body on the way a numbered-section book's does, so the entire chapter
#: became one Chunk. Devanagari's conjunct clusters tokenize far denser than plain ASCII
#: (a BPE tokenizer often spends more than one token per visible character on it), so a
#: char-count budget has to assume the worst case rather than count on ~4 chars/token the
#: way an English estimate could. 6,000 characters keeps every split comfortably under the
#: 32,768-token ceiling even at close to 1 token/char, the same conservative-ratio choice
#: OCR_DPI and MIN_BODY_CHARS elsewhere in this module make for a real Tesseract quirk
#: rather than a theoretical one.
MAX_CHUNK_CHARS = 6000


def _split_oversized_body(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Break one body slice into pieces no bigger than ``max_chars``, without cutting a
    paragraph in half where that can be avoided -- a paragraph is the only unit this text
    reliably has once OCR has erased the book's own subheadings."""
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        if len(para) <= max_chars:
            current = para
        else:
            # a single paragraph bigger than the budget on its own -- hard-split it
            for i in range(0, len(para), max_chars):
                parts.append(para[i:i + max_chars])
    if current:
        parts.append(current)
    return parts


#: labels that are bold, and often the LARGEST bold text in the chapter -- bigger than
#: every real heading, not smaller -- but are never themselves a heading: an
#: end-of-chapter drill word, or a bare numbered-list marker like '2.'. Matched as a
#: whole line, allowing the word to repeat (EXERCISES is drawn sideways and reads back as
#: 'EXERCISES  EXERCISES  EXERCISES...', the same quirk BARE_DRILL_LABEL absorbs).
#: case-insensitive for the same reason BARE_DRILL_LABEL is: Political Science sets
#: 'Exercises' in title case, at a bold size (100pt in the real file) bigger than any of
#: its real headings -- an exact-caps-only match let it through as a candidate, and being
#: the only line at that size, it became the chapter's entire heading list.
#:
#: 'NOTES FOR (THE )?TEACHERS?' -- both forms appear, sometimes on the very same page
#: ('NOTES FOR TEACHERS' as a running strap, 'NOTES FOR THE TEACHER' as the block title
#: right under it) -- confirmed against Economics' own "Development" chapter, where the
#: front-matter note is drawn at 24pt against the chapter's real headings at 14pt: the
#: THE-less form used to slip through this pattern entirely, so 'largest bold text in the
#: chapter' picked the teacher's note over every real heading and returned it as the
#: chapter's ONLY section -- not a smaller list, an empty one wearing a section's shape.
#:
#: 'ACTIVITY \d+' / 'TABLE \d+(\.\d+)* ...' -- confirmed on the same chapter: a table
#: caption ('TABLE 1.3 PER CAPITA INCOME OF SELECT STATES') and a numbered activity
#: ('ACTIVITY 1') are drawn at the identical 14pt the chapter's real headings use, so once
#: the 24pt note above stopped winning outright, these numbered captions would have
#: entered the candidate list beside the real headings, at the same size, with nothing
#: left to tell them apart by size alone.
_NOT_A_HEADING = re.compile(
    r"^(EXERCISES|QUESTIONS|PROJECT|ACTIVITY|PROJECT/ACTIVITY|PROJECT WORK|DISCUSS|"
    r"MAP SKILLS|MAP WORK|WRITE IN BRIEF|SUGGESTED READINGS|ADDITIONAL PROJECTS\s*/\s*"
    r"ACTIVITIES|ADDITIONAL PROJECT\s*/\s*ACTIVITY|ADDITIONAL ACTIVITY\s*/\s*PROJECT|"
    r"BIBLIOGRAPHY|FURTHER READING|GLOSSARY|"
    r"LET.S WORK (?:THESE|THIS) OUT|LET.S RECALL|NOTES? FOR (?:THE )?TEACHERS?|"
    r"SOURCES FOR INFORMATION|EXAMPLE|WHAT DOES THIS SHOW\??)"
    r"(\s+\1)*(\s+\d{1,2}(?:\.\d{1,2}){0,2})?$"
    r"|^ACTIVITY\s+\d+$"
    r"|^TABLE\s+\d+(?:\.\d+)*\b.*$"
    r"|^GRAPH\s+\d+(?:\.\d+)*\s*[:.].*$"
    r"|^FIG(?:URE)?\.?\s+\d+(?:\.\d+)*\b.*$",
    re.I,
)


#: A cover page prints 'Chapter N' or 'Chapter I' in large type, and the chapter's own
#: title is often set even bigger than that -- Political Science draws 'Power-sharing' at
#: 65pt against 20pt real headings. Both would otherwise win "the chapter's largest bold
#: text" outright and become the entire heading list on their own.
#: 'Chapter 5' alone, or 'Chapter 5 : Consumer Rights' -- the cover repeating its own
#: title after a colon, on the same bold line as the chapter word.
_CHAPTER_COVER = re.compile(r"^Chapter\s+[\dIVXLCDM]+(\s*:.*)?$", re.I)


def _heading_styled_lines(
    doc: pymupdf.Document, require_bold: bool, body_size: float = 0.0
) -> list[tuple[int, float, float, str, int | None]]:
    """(page_index, y0, size, text, colour) for every line styled as a heading might be.

    ``require_bold`` is the normal case: bold, at whatever size, is what a real heading
    uses in every book tried except one. That one book (Economics) sets its real headings
    in a custom embedded subset font that carries no bold flag at all -- only a size
    visibly larger than the body -- so the looser test is a second attempt, tried only
    when the bold one below finds nothing usable, never blended into it: a book whose
    real headings genuinely are bold must never have this looser, noisier signal
    reconsidering them.

    A span's own bold FLAG is not the only real signal, though -- confirmed on the real
    "Resources and Development" chapter, whose own subheadings ("Classification of
    Soils", "Resource Planning in India") are set in 'Bookman-Demi', a genuine semi-bold
    weight, but PyMuPDF never sets the bold flag bit for it (only 'Bookman,Bold', a
    different named variant elsewhere in the SAME document, gets the flag). A font name
    containing 'Demi' -- a standard type-weight name, never used for a body font in any
    real book seen -- is treated as bold too, on this same signal-not-flag reasoning.
    """
    lines: list[tuple[int, float, float, str, int | None]] = []
    for page_index, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line.get("spans") or []
                if not spans:
                    continue
                line_text = "".join(s["text"] for s in spans).strip()
                if not line_text:
                    continue
                if require_bold:
                    if not all(s["flags"] & 16 or "demi" in s["font"].lower() for s in spans):
                        continue
                elif not all(round(s["size"], 1) > body_size + 1.0 for s in spans):
                    continue
                # Rounded: two headings set at the same visual 10.5pt size can carry
                # different exact floats (10.5 vs 10.500472068786621) depending on how
                # the PDF's font matrix scaled them, and comparing those unrounded left
                # only the one exact bit-pattern that happened to be the chapter's max.
                colour = spans[0].get("color") if len({s.get("color") for s in spans}) == 1 else None
                lines.append(
                    (page_index, line["bbox"][1], round(spans[0]["size"], 1), line_text, colour)
                )
    return lines


def _pick_sections(
    lines: list[tuple[int, float, float, str, int | None]],
    text: str,
    chapter_title: str,
    *,
    filter_by_cover_colour: bool,
    multi_size: bool = False,
    body_size: float = 0.0,
) -> list[Section]:
    """The shared second half of both heading-detection attempts: dedupe, exclude noise,
    prefer the book's own numbering if it has one, and otherwise take the largest
    remaining size.
    """
    if not lines:
        return []

    # Noise is filtered out FIRST, before the heading size is even decided: an end-of-
    # chapter drill word is often drawn bigger than every real heading, not smaller, and
    # picking "the largest bold text" before excluding it left either nothing (every
    # 12pt line was 'ACTIVITY') or the drill word itself ('PROJECT WORK') standing in for
    # every real heading in the chapter.
    # Two exact-repeat draws in a row, at the same spot, are one line read twice -- Economics
    # sets several things (page numbers, running headers, story captions) as five identical
    # overlapping draws, the same fake-bold trick Science uses on single headings, which
    # read_text's own collapsing (_collapse_bold) was built for but never runs on this
    # per-span view. Collapsed here to the same effect: keep the first, drop the repeats.
    #
    # A near-identical draw that EXTENDS the previous one rather than repeating it verbatim
    # ('HUMAN' x4, then 'HUMAN DEVELOPMENT' once, then 'REPOR' x4, then 'REPORT' once) is
    # the same fake-bold trick's other shape -- confirmed on the real Economics
    # "Development" chapter's own 'HUMAN DEVELOPMENT REPORT' banner. `_overlap` (already
    # used by `_collapse_bold` for exactly this) merges a draw onto the previous one when
    # it shares a suffix/prefix rather than repeating it outright, which the exact-match
    # rule above cannot catch on its own.
    deduped: list[tuple[int, float, float, str, int | None]] = []
    for entry in lines:
        page_index, y, size, line_text, colour = entry
        if deduped and deduped[-1][0] == page_index and abs(y - deduped[-1][1]) < 5:
            if deduped[-1][3] == line_text:
                continue
            shared = _overlap(deduped[-1][3], line_text)
            if shared and deduped[-1][2] == size:
                p, y0, s, acc, c = deduped[-1]
                deduped[-1] = (p, y0, s, acc + line_text[shared:], c)
                continue
        deduped.append(entry)
    # Tried sorting this list by (page, y) here, to fix a real page-order bug: a page's
    # blocks come back from PyMuPDF in the order they sit in the PDF's own content
    # stream, not necessarily top-to-bottom (confirmed on the real "Globalisation and the
    # Indian Economy" chapter, where a boxed example sits below its own section heading
    # visually but is returned first). Reverted: this function's other adjacency checks
    # (the fake-bold-overlap dedup above, the caption-exclusion inheritance and the
    # wrap-title merge below) all assume list-adjacent entries are also stream-adjacent,
    # and a y-sort breaks that whenever unrelated content's own y happens to fall between
    # two fragments of the same real heading -- confirmed on the real Development
    # chapter, where sorting put an excluded 'ACTIVITY 3' label between 'HUMAN
    # DEVELOPMENT' and 'REPORT' (two halves of one heading) purely by y-coordinate, which
    # then made 'REPORT' wrongly inherit 'ACTIVITY 3'-s own exclusion. The heading-order
    # bug this was meant to fix is real but not fixed here -- see _pick_sections' own
    # final numbering step, which locates each heading independently instead.
    lines = deduped

    # Only used on the size-based attempt: the cover repeats the chapter's own title in
    # the same ink used for its real headings, and that attempt's own noise (an oversized
    # story caption, a drill label) is not excludable by keyword the way EXERCISES or
    # PROJECT is. The bold attempt never reaches here with this on -- it doesn't need it,
    # and a book whose cover happens to share a colour with something else entirely
    # would otherwise lose real headings to a filter it never asked for.
    # NOT applied when ``multi_size``: this assumes every real heading in the chapter is
    # drawn in one uniform colour matching the cover's -- true for a chapter with one real
    # heading level, false the moment there is more than one. Confirmed on the real
    # "Money and Credit" chapter: its 12pt headings ("Currency", "Deposits with Banks")
    # happen to share the cover's own colour, but its 18pt case-study headings ("Cheque
    # Payments", "A House Loan", "Grameen Bank of Bangladesh") do not -- this filter alone
    # silently threw away that entire heading level, the same shape of loss as taking only
    # the largest size (see the multi_size branch below) but from the opposite direction.
    heading_colour = (
        next(
            (c for _p, _y, _s, t, c in lines if c is not None and _CHAPTER_COVER.match(t)),
            None,
        )
        if filter_by_cover_colour and not multi_size
        else None
    )

    # Substring, not equality, and one-directional: a title set across several bold lines
    # on the cover ('Gender,' / 'Religion and' / 'Caste' for a chapter titled 'Gender,
    # Religion and Caste') has no single line that equals the whole title, but every one of
    # its fragments IS a substring of it -- a real heading essentially never is. The other
    # direction ('does the line contain the title') is not checked: a real subheading
    # legitimately contains the chapter's own title word ('How is federalism practised?'
    # in a chapter called 'Federalism'), and a cover repeating the title after the chapter
    # number ('Chapter 5 : Consumer Rights') is caught by _CHAPTER_COVER already, not by
    # this.
    # A caption that wraps to a second line ('TABLE 1.2 COMPARISON OF TWO' / 'COUNTRIES')
    # is excluded by _NOT_A_HEADING on its first line only -- the wrapped continuation
    # carries none of the words that matched. Confirmed on Economics' own "Development"
    # chapter: 'CATEGORIES OF PERSONS', 'COUNTRIES' and 'HARYANA, KERALA AND BIHAR' each
    # rode in as their own bare candidate this way, once the caption's own first line
    # stopped winning outright. A line inherits the exclusion of the line right above it
    # on the same page, at the same size, close enough together to be the same visual
    # caption -- the identical adjacency test the merge step below uses to join a real
    # heading's own wrapped second line, applied here to keep an excluded line's tail out
    # rather than to join a kept one's.
    excluded_lines: set[int] = set()
    previous: tuple[int, float, float] | None = None
    for i, (page_index, y, size, line_text, _colour) in enumerate(lines):
        if _NOT_A_HEADING.match(line_text) or _CHAPTER_COVER.match(line_text):
            excluded_lines.add(i)
        elif (
            previous is not None and previous[0] == page_index
            and 0 < y - previous[1] < 20
            and (i - 1) in excluded_lines
        ):
            # No size match required here (unlike the wrap-title merge below): a
            # caption's own wrapped continuation is not always drawn at exactly the same
            # size as its first line -- confirmed on the real Economics "Development"
            # chapter, where 'TABLE ... PER CAPITA INCOME' sits at 14.0pt and its
            # continuation 'OF SELECT STATES' at 13.5pt. Requiring an exact match here
            # left that continuation eligible to survive as its own bare candidate once
            # more than one size cohort could produce a section (see ``multi_size``).
            excluded_lines.add(i)
        previous = (page_index, y, size)

    # A running header/footer repeating the chapter's own name on every page -- confirmed
    # on the real "Political Parties" chapter, where 'De moc ra tic Polit ics' (the book's
    # own title, its letters spaced out by the page design) and 'Po lit ica l Pa r tie s'
    # (the chapter's own name, same treatment) each appear 8-9 times, once per page, at a
    # size that clears the body-size floor. A real heading appears once; only page
    # furniture repeats itself verbatim across many different pages. Only matters once
    # ``multi_size`` lets more than one size cohort through -- a single wrong cohort could
    # already dominate "the largest size" on its own before, but never diluted a
    # genuinely correct cohort the way it can now that several are combined.
    repeat_counts: dict[str, int] = {}
    if multi_size:
        for _p, _y, _s, t, _c in lines:
            repeat_counts[t] = repeat_counts.get(t, 0) + 1

    title_key_ = title_key(chapter_title) if chapter_title else None
    candidates = [
        (page_index, y, size, line_text)
        for i, (page_index, y, size, line_text, colour) in enumerate(lines)
        if not re.fullmatch(r"\d{1,3}\.?", line_text)
        and re.search(r"[A-Za-z]", line_text)   # a decorative glyph ('+') has no letters
        # A running corner mark -- confirmed on a real Economics chapter, a single bold
        # letter ('E', 'D', 'C', ...) repeated on every page, the book's own department
        # watermark spelled one character per page. No real heading is one or two
        # characters long, so nothing here excludes a genuine short one.
        and len(line_text.strip()) >= 3
        and repeat_counts.get(line_text, 0) < 3
        and i not in excluded_lines
        and (heading_colour is None or colour == heading_colour)
        and (title_key_ is None or title_key(line_text) not in title_key_)
    ]
    if not candidates:
        return []

    # A book like History numbers its own headings ('1  The Rise of...', '2.1 The
    # Aristocracy...'); a book like Geography or Political Science numbers none of them.
    # Tried first -- a *plain* numbered list in body prose matches the same shape without
    # being a heading, which is exactly what happened before boldness (or the size test
    # above) was required to even become a candidate. Two or more real matches is treated
    # as "this book numbers its headings"; one is treated as coincidence (a single
    # numbered exhibit or footnote happening to be styled the same way), so the
    # largest-size convention gets a chance instead of taking a lone false positive as
    # the whole answer.
    # A numbered heading that wraps to a second line ('4.1 Post-war Settlement and the' /
    # 'Bretton Woods Institutions') keeps only its first line's text here -- unlike the
    # size-based path below, which merges a wrapped continuation back in. Tried and
    # reverted: the same real chapter that has wrapped numbered headings also has bold
    # map-legend labels stacked as several separate close-together lines (BRITISH,
    # FRENCH, GERMAN, ...) and multi-line photo captions at the same size, indistinguish-
    # able by position alone from a genuine wrapped title -- merging on proximity glued
    # entire legends and captions onto the nearest heading's title and corrupted the text
    # search that locates it (`text.find` on a title that was never contiguous prose),
    # which silently dropped OTHER real headings entirely rather than just truncating one
    # title. A truncated display title is a cosmetic loss; a dropped section is not.
    numbered = [
        (page_index, y, m.group(1), m.group(2).strip())
        for page_index, y, _size, line_text in candidates
        if (m := BOOK_NUMBERED_SECTION.match(line_text))
    ]
    if len(numbered) >= 2:
        # Keyed by number -> the FIRST title seen under it, which is what tells a running
        # header repeating the same heading apart from the book itself genuinely reusing a
        # number for a second, different heading -- confirmed on the real History chapter
        # "The Making of a Global World": '2.4' is printed twice, once for 'Rinderpest, or
        # the Cattle Plague' and again, later, for 'Indentured Labour Migration from
        # India' -- two real, different headings in the book's own text, not a
        # transcription slip. The OLD dedup here (a bare `set` of numbers already seen)
        # could not tell that apart from a running header and silently dropped the second
        # heading entirely, folding its real content into the first's span.
        seen_titles: dict[str, str] = {}
        found: list[tuple[str, str, int]] = []
        cursor = 0
        for _page_index, _y, number, title in numbered:
            if seen_titles.get(number) == title:
                continue          # the same heading's own running-header repeat
            pos = text.find(title, cursor)
            if pos == -1:
                continue
            # A running page-top banner repeating the CURRENT section's own number and
            # title, printed once at the start of that section's first new page --
            # confirmed on the same real chapter: "2 The Nineteenth Century (1815-1914)"
            # appears in the extracted text exactly once, mid-paragraph, immediately
            # followed by "Reprint 2026-27" and the book title -- the page's own running
            # furniture, not a second real heading. Taking it as one invented a phantom
            # "2" section that stole the back half of "2.1"'s real content (the food-price
            # discussion right after it plainly continues 2.1's own topic, not a new
            # one), and its own out-of-place position -- AFTER "2.1" has already started
            # -- is only possible for furniture glued to a page break, never a genuine
            # heading a book would print out of numeric order.
            if text[pos + len(title):pos + len(title) + 20].lstrip().startswith("Reprint"):
                continue
            # A number already used for a DIFFERENT title is the book reusing it for a
            # second real heading, not a repeat of the first -- disambiguated so both
            # keep their own content and their own dict key downstream
            # (verify_against_toc keys sections by number; two sections sharing one would
            # silently collide, the second overwriting the first). The disambiguated form
            # is reported as a real problem by verify_structure/verify_against_toc rather
            # than hidden, since it is not what a hand-typed oracle would ever expect.
            if number in seen_titles:
                suffix = 2
                while f"{number}-{suffix}" in seen_titles:
                    suffix += 1
                number = f"{number}-{suffix}"
            seen_titles[number] = title
            found.append((number, title, pos))
            cursor = pos + len(title)
        sections = []
        for i, (number, title, start) in enumerate(found):
            end = found[i + 1][2] if i + 1 < len(found) else len(text)
            sections.append(Section(number, title, start, end))
        return sections

    if multi_size:
        # Every remaining candidate is a real heading, not only the single largest size --
        # ``multi_size`` only, i.e. only for the size-based (non-bold) pass. Confirmed
        # wrong on a real Economics chapter ("Money and Credit"): its real headings print
        # at THREE different sizes, not one -- 18pt for a named illustrative case
        # ("Cheque Payments", "A House Loan", "Grameen Bank of Bangladesh"), 14pt for the
        # chapter's own major divisions ("Loan Activities of Banks", "Formal Sector
        # Credit in India"), and 12pt for a third, finer level ("Currency", "Deposits
        # with Banks"). Taking only the max (18pt) kept the case studies and discarded
        # the other two-thirds of the chapter's real structure -- not a smaller,
        # incomplete list, but a differently-shaped wrong one, since 18pt alone reads as
        # "this chapter's only headings" with nothing left to contradict it. Safe for a
        # chapter with just one real heading size (Development, ...): there is only one
        # cohort to take, so this is a no-op for them.
        #
        # NOT extended to the bold pass in the same unconditional way: bold text there is
        # used far more loosely, for diagram labels and table captions at all sorts of
        # small sizes ('DEPOSITORS', 'BORROWERS', 10pt bold labels beside a bank diagram,
        # confirmed on the same real chapter) that the size-based pass's own
        # `size > body_size + 1.0` floor already excludes on its own -- the bold pass has
        # no such floor, so doing this there pulled in every bold caption in the chapter
        # as if it were a heading. The bold pass gets its OWN, narrower second-level
        # attempt below instead, gated on a real-content check a bare caption or table
        # header cannot pass.
        headings = [
            (page_index, y, size, line_text)
            for page_index, y, size, line_text in candidates
        ]
        level_sizes: list[float] | None = None
    else:
        # A book's own bold headings can carry two real levels too -- a major, all-caps
        # division and smaller mixed-case subheadings under it, both genuinely bold, not
        # a diagram label or table caption at some arbitrary small size. Confirmed on the
        # real "Resources and Development" chapter: 7 major headings ("LAND RESOURCES")
        # found correctly, but real subheadings with substantial content of their own
        # ("Sustainable development", "Classification of Soils", ...) were silently
        # entirely absent, not truncated, because only the single largest bold size was
        # ever kept.
        #
        # The floor here is `size >= body_size`, not the size-based pass's own
        # `body_size + 1.0`: a real subheading can be bold at exactly the body's own
        # size, with nothing to visually separate it but the bold weight itself --
        # confirmed on the same chapter, where "Sustainable development" prints at
        # 10.5pt, identical to the surrounding body text (also 10.5pt, just not bold). A
        # genuine diagram label still sits BELOW that floor even bold -- confirmed on the
        # same chapter's own soil-profile diagram ("Subsoil weathered", "rocks sand and",
        # ... all 9.5pt).
        #
        # This alone still let through a real false positive: a bold TABLE COLUMN HEADER
        # ("Language", "Proportion of speakers (%)") at the same qualifying size,
        # confirmed on the real "Federalism" chapter -- excluded below, after locating
        # each heading in the text, by requiring genuine prose to follow it, which a bare
        # table header never has.
        sizes_above_floor = sorted(
            {size for _p, _y, size, _t in candidates if size >= body_size}, reverse=True,
        )
        if len(sizes_above_floor) >= 2:
            headings = [
                (page_index, y, size, line_text)
                for page_index, y, size, line_text in candidates
                if size in sizes_above_floor
            ]
            level_sizes = sizes_above_floor
        else:
            heading_size = max(size for _p, _y, size, _t in candidates)
            headings = [
                (page_index, y, heading_size, line_text)
                for page_index, y, size, line_text in candidates
                if size == heading_size
            ]
            level_sizes = None

    # A title that wraps to a second line is still one heading: merge it into the line
    # above when the two are close together on the same page AT THE SAME SIZE, but keep
    # the FIRST line's own text for locating the heading in `text` -- the join here is
    # cosmetic only, and searching for a two-line title as one string would depend on
    # exactly how read_text rejoins lines, which this function has no reason to assume.
    # The size check matters now that headings spans multiple real size cohorts (see
    # above): two DIFFERENT headings at different sizes sitting close together on the
    # page (a 12pt heading's last line just above an unrelated 18pt heading's first)
    # would otherwise glue into one nonsense title instead of staying two real ones.
    #
    # The gap allowed between the two lines scales with the heading's own size rather
    # than a flat 20pt: confirmed on the real "Power-sharing" chapter, whose own 24pt
    # illustration title ("Khalil's" / "dilemma") wraps with a 24.6pt gap between lines,
    # narrowly over the old flat threshold, because a bigger font naturally sets a bigger
    # line height. A fixed threshold split it into two fragments instead of the one real
    # heading it is.
    merged: list[tuple[str, str, float]] = []   # (locate_by, display_title, size)
    previous: tuple[int, float, float] | None = None
    for page_index, y, size, line_text in headings:
        if (
            previous is not None and previous[0] == page_index
            and previous[2] == size and 0 < y - previous[1] < max(20.0, size * 1.2)
        ):
            locate_by, title, msize = merged[-1]
            merged[-1] = (locate_by, f"{title} {line_text}", msize)
        else:
            merged.append((line_text, line_text, size))
        previous = (page_index, y, size)

    # A noise phrase split across the wrap itself ('LET'S WORK THESE' / 'OUT', two
    # separate lines) matches no exclusion pattern until they are joined -- checked again
    # here, after merging, not only on each raw line before it, for exactly that gap.
    merged = [
        (locate_by, title, size)
        for locate_by, title, size in merged
        if not _NOT_A_HEADING.match(title)
    ]

    # A single shared cursor, advanced monotonically as ``merged`` is walked in ITS OWN
    # order, assumes that order already matches where each title actually sits in
    # ``text``. Usually true (``text`` comes from read_text's plain ``get_text()``, whose
    # own block order usually agrees with this function's own heading order), but not
    # always -- confirmed on the real "Globalisation and the Indian Economy" chapter,
    # where a boxed example ('Spreading of Production by an MNC') is laid out by
    # ``get_text()`` AHEAD of its own section heading ('PRODUCTION ACROSS COUNTRIES'),
    # which sits above it on the page. Once the shared cursor got ahead of where that
    # later heading's real position was, every real heading still to come silently
    # vanished (``pos == -1``), not just the one out of order -- 23 real headings
    # collapsed to 9.
    #
    # Recovered on failure by searching from the very start instead, but ONLY on
    # failure, and WITHOUT moving the shared cursor for every other heading still to
    # come: searching from 0 unconditionally for every title reintroduced a different
    # real bug, confirmed on the real "Sectors of the Indian Economy" chapter -- its own
    # "Kanta" is a name mentioned once in ordinary prose ("What are\nKanta works in the
    # organised sector...") BEFORE her own heading of the same one word, and searching
    # unconditionally from 0 matched that earlier prose mention instead of the real
    # heading every time, silently mispositioning a section that the plain monotonic
    # cursor already located correctly. Falling back to an unrestricted search only for
    # the rare heading the cursor genuinely could not find keeps the common case (cursor
    # order already correct) untouched, and only ever reorders the rare recovered one.
    cursor = 0
    found: list[tuple[str, int, float]] = []
    for locate_by, title, size in merged:
        pos = text.find(locate_by, cursor)
        if pos == -1:
            pos = text.find(locate_by, 0)
            if pos == -1:      # read_text folded whitespace this function did not predict
                continue
            found.append((title, pos, size))
            continue
        found.append((title, pos, size))
        cursor = pos + len(locate_by)
    found.sort(key=lambda triple: triple[1])

    if level_sizes is not None:
        # A bare table column header ("Language", "Proportion of speakers (%)") clears
        # every filter above -- genuinely bold, at a genuine second-level size -- but it
        # is never followed by real prose the way a true subheading is, only by the
        # table's own data rows or the next real heading immediately. Confirmed on the
        # real "Federalism" chapter. Required only of a MINOR heading: a major one is
        # already reliable enough (the single-size path above has never needed this),
        # and a short-but-real major section should not be second-guessed by a length
        # floor invented for a different problem.
        filtered = []
        for i, (title, start, size) in enumerate(found):
            if size != level_sizes[0]:
                span_end = found[i + 1][1] if i + 1 < len(found) else len(text)
                if len(text[start:span_end].strip()) < MIN_BODY_CHARS:
                    continue
            filtered.append((title, start, size))
        found = filtered

        # Nested numbering the book itself never prints: level_sizes[0] (the largest) is
        # a major division, any smaller size still above the floor is a subheading under
        # whichever major heading precedes it. A minor heading found before any major one
        # has appeared at all (rare -- an opening illustration or case study ahead of the
        # chapter's own first division) falls back to flat numbering rather than a
        # nonsensical "0.1".
        sections = []
        major = 0
        minor = 0
        for i, (title, start, size) in enumerate(found):
            if size == level_sizes[0]:
                major += 1
                minor = 0
                number = str(major)
            elif major:
                minor += 1
                number = f"{major}.{minor}"
            else:
                number = str(i + 1)
            end = found[i + 1][1] if i + 1 < len(found) else len(text)
            sections.append(Section(number, title, start, end))
        return sections

    sections: list[Section] = []
    for i, (title, start, _size) in enumerate(found):
        end = found[i + 1][1] if i + 1 < len(found) else len(text)
        sections.append(Section(str(i + 1), title, start, end))
    return sections


def _sections_by_boldness(path: str | Path, text: str, chapter_title: str = "") -> list[Section]:
    """Headings for a book that numbers nothing at all -- Geography publishes no section
    list on its contents page and its subheadings carry no number of their own, bare or
    decimal. What marks a real heading is typography: bold, and at the largest bold size
    used anywhere in the chapter, tried first since it is what every book but one uses.
    Economics sets its real headings in a custom embedded subset font that carries no
    bold flag at all -- only a size visibly larger than the body -- so a second attempt
    on that looser signal used to run only when the bold one found nothing usable at all.

    That "nothing at all" test was too easy to satisfy. Confirmed on the real "Money and
    Credit" chapter: exactly two of its real headings ("Loan Activities of Banks", "Formal
    Sector Credit in India") happen to be drawn bold, and the other dozen -- "Currency",
    "Terms of Credit", "Variety of Credit Arrangements", "Self-Help Groups for the Poor",
    all real, all present as plain (non-bold) text at larger-than-body sizes -- are not.
    The bold pass returned a non-empty, plausible-looking two-section list, which used to
    end the search right there: not the silent single-section collapse the note above
    describes, but the same failure in miniature, spread across the whole chapter instead
    of concentrated at its start. Now, whenever the bold pass looks sparse for how long the
    chapter actually is (average span per section over the same threshold a lone section
    is judged suspicious by), the looser size-based pass is tried too, and whichever finds
    more real headings wins -- checked against Political Parties, whose correctly-bold
    six-section chapter also clears that span threshold: the size-based pass there finds
    only one ('Overview'), so the comparison still keeps the right answer.

    Section 'numbers' are just 1, 2, 3... in reading order: the book gives none, so
    inventing a false one there would be worse than admitting there isn't one. Found by
    font, but *located* by searching the plain text for it, so the character offsets this
    returns line up with the same ``text`` extract_chunks slices -- a PDF-native offset
    would not.
    """
    with pymupdf.open(path) as doc:
        # Computed up front, not only on the size-based fallback: the bold pass now also
        # uses this as its own floor for a genuine second heading level (see
        # _pick_sections' own note on the real "Resources and Development" chapter).
        body_chars: dict[float, int] = {}
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for s in line.get("spans") or []:
                        size = round(s["size"], 1)
                        body_chars[size] = body_chars.get(size, 0) + len(s["text"])
        body_size = max(body_chars, key=lambda s: body_chars[s]) if body_chars else 0.0

        bold_lines = _heading_styled_lines(doc, require_bold=True)
        by_bold = _pick_sections(
            bold_lines, text, chapter_title, filter_by_cover_colour=False, body_size=body_size,
        )
        # Sparseness is judged on MAJOR headings only ("." in a number means a nested
        # minor one), not the enriched count _pick_sections may now return: a chapter
        # whose real major-level detection was already too thin to trust must still fall
        # through to the size-based path below exactly as it did before minor headings
        # existed, whatever minor enrichment happened to find along the way. Confirmed on
        # the real "Federalism" chapter -- only 4 real major headings are genuinely bold,
        # which used to (and must still) read as sparse and fall through to the size pass
        # that finds "Overview" (itself never bold at all, so the bold pass, enriched or
        # not, can never contain it on its own).
        major_count = len([s for s in by_bold if "." not in s.number])
        sparse = (
            not major_count
            or len(text) / major_count > SUSPICIOUS_SINGLE_SECTION_CHARS
        )
        if by_bold and not sparse:
            return by_bold

        sized_lines = _heading_styled_lines(doc, require_bold=False, body_size=body_size)
        by_size = _pick_sections(
            sized_lines, text, chapter_title, filter_by_cover_colour=True, multi_size=True,
        )
        # Compared against major_count, not len(by_bold): the enriched minor headings
        # _pick_sections may have added make by_bold's raw count no longer a fair stand-
        # in for how many real headings its MAJOR-level detection alone found, which is
        # the actual question this comparison answers ("did the size-based pass do
        # better than the bold pass's own real division count?"). Confirmed on the real
        # "Federalism" chapter: an enriched-but-still-sparse by_bold (10, nested) used to
        # out-count a correct, flat by_size (also 10, "Overview" included) on a false
        # tie, keeping the wrong list purely because nothing was left to break the tie.
        return by_size if len(by_size) > major_count else by_bold


def extract_chunks(
    text: str, chapter: int, sections: list[Section] | None = None, body_bucket: str = "T",
    bare_numbered_questions: bool = False,
) -> list[Chunk]:
    """Split a chapter into familiarity chunks, section by section.

    Marker-only chunking captured 72% of the book. The missing 28% was the expository
    body -- definitions, derivations, the prose that introduces a method -- because it
    carries no "Theorem"/"Example" label. That text is taught content as much as a worked
    example is, so a question drawn from it found no match and was judged NOVEL when it
    was T_VERBATIM: a wrong tier, arrived at silently.

    So each section contributes its labelled markers *and* the prose between them.
    """
    optional: dict[int, bool] = {}
    markers: list[tuple[int, str, str, str]] = []
    for m in THEOREM.finditer(text):
        markers.append((m.start(), "theorem", "T", f"Theorem {m.group(1)}"))
        optional[m.start()] = bool(m.group(2))
    for m in ACTIVITY.finditer(text):
        markers.append((m.start(), "activity", "T", f"Activity {m.group(1)}"))
        optional[m.start()] = bool(m.group(2))
    for m in EXAMPLE.finditer(text):
        markers.append((m.start(), "example", "T", f"Example {m.group(1)}"))
        optional[m.start()] = bool(m.group(2))
    for m in EXERCISE.finditer(text):
        markers.append((m.start(), "exercise", "E", f"EXERCISE {m.group(1)}"))
        optional[m.start()] = bool(m.group(2))
    # A bare label like QUESTIONS or Discuss repeats several times in a chapter, so the
    # occurrence is numbered to keep the reference unique -- an identical reference is
    # dropped below as a back-reference, which would have thrown away every block but the
    # first and emptied the drilled bucket for the subject.
    for n, m in enumerate(BARE_DRILL_LABEL.finditer(text), start=1):
        label = m.group(1).title()
        markers.append((m.start(), "exercise", "E", f"{label} {chapter}.{n}"))
    # HINDI_DRILL_LABEL is Devanagari-only text, so it can never match another book's
    # English/numbered markers -- run unconditionally rather than gating it behind a flag
    # only Hindi's caller would ever set.
    for n, m in enumerate(HINDI_DRILL_LABEL.finditer(text), start=1):
        markers.append((m.start(), "exercise", "E", f"अभ्यास {chapter}.{n}"))
    # Same reasoning as HINDI_DRILL_LABEL: Tamil-script-only, so it can never match
    # another book's markers -- run unconditionally rather than gating on a flag.
    for n, m in enumerate(TAMIL_DRILL_LABEL.finditer(text), start=1):
        markers.append((m.start(), "exercise", "E", f"கற்பவை கற்றபின் {chapter}.{n}"))
    if bare_numbered_questions:
        for n, m in enumerate(ENGLISH_NUMBERED_QUESTION.finditer(text), start=1):
            lookback = text[max(0, m.start() - 40):m.start()].rstrip()
            if lookback.endswith(_TEACHER_INSTRUCTION_LABEL):
                continue
            markers.append((m.start(), "exercise", "E", f"Question {chapter}.{n}"))
        for n, m in enumerate(HINDI_NUMBERED_QUESTION.finditer(text), start=1):
            markers.append((m.start(), "exercise", "E", f"प्रश्न {chapter}.{n}"))
        for n, m in enumerate(TAMIL_NUMBERED_QUESTION.finditer(text), start=1):
            markers.append((m.start(), "exercise", "E", f"வினா {chapter}.{n}"))

    markers.sort()
    # A reference appearing twice is a back-reference in body text, not a restatement:
    # "Theorem 6.1: Fig. 6.11" is a figure caption. The statement always comes first.
    seen: set[str] = set()
    markers = [m for m in markers if not (m[3] in seen or seen.add(m[3]))]

    def _append(bucket: str, kind: str, reference: str, piece: str, section: str,
                examinable: bool = True) -> None:
        parts = _split_oversized_body(piece)
        for i, part in enumerate(parts, start=1):
            part_reference = reference if len(parts) == 1 else f"{reference} (part {i})"
            chunks.append(
                Chunk(bucket, kind, part_reference, part, stem_hash(part),
                      section=section, examinable=examinable)
            )

    chunks: list[Chunk] = []
    for section in sections if sections is not None else extract_sections(text, chapter):
        inside = [m for m in markers if section.start <= m[0] < section.end]
        boundaries = [m[0] for m in inside] + [section.end]

        body = text[section.start:boundaries[0]].strip()
        if len(body) >= MIN_BODY_CHARS:
            _append(body_bucket, "body" if body_bucket == "T" else "exercise",
                    f"Section {section.number}", body, section.number)

        for i, (start, kind, bucket, reference) in enumerate(inside):
            stop = boundaries[i + 1]
            piece = text[start:stop].strip()
            _append(bucket, kind, reference, piece, section.number,
                    examinable=not optional.get(start, False))

    return chunks


def _locate_known_sections(
    path: str | Path, text: str, titles: list[str],
) -> tuple[list[Section], list[str]]:
    """Locate a chapter's own real headings by STRING, not by typography -- for a book
    where boldness, size and colour genuinely cannot tell a real heading apart from
    everything else on the page.

    Confirmed necessary on the real "Resources and Development" chapter: its headings
    span three bold sizes, several are plain (non-bold) text at exactly the chapter's own
    body size, one ("Conservation of Resources") is an inline lead-in glued to its own
    paragraph on the same line rather than a standalone line at all, and a soil-profile
    diagram draws its own layer labels bold at a real heading's own size. No combination
    of the typographic signals _sections_by_boldness has tried told these apart safely
    (see its own docstring's note on the multi_size-bold and colour-only attempts tried
    and reverted here) -- but the book's own real headings are already known, typed from
    the contents page and checked chapter by chapter, the same oracle History and
    Economics verify their OWN independently-detected sections against.

    Used only where that oracle exists and only on request (a caller opts in), never as a
    silent replacement for the typographic passes: those stay the default because they
    catch a REAL extraction bug when a chapter's own detected structure disagrees with
    the oracle (verify_against_toc). Locating by the oracle's own strings instead removes
    that independent check entirely for the chapter it runs on, so it is only worth doing
    where the typographic passes have already been tried and proven not to work.

    A known title is matched against the page's own text spans, not searched for blindly
    in ``text``: a short, common title ("Land Resources") searched for directly matched
    an EARLIER, incidental mention buried in an unrelated paragraph ("Land resources are
    used for...") rather than the real heading further down, on the real file -- the same
    class of false match ``_pick_sections``' own per-title cursor exists to avoid for a
    genuinely repeated heading. Matching against the page's own STYLED spans first (any
    style, since none can be trusted alone here) and only then locating that specific
    span's text in ``text`` avoids it: incidental prose is one span among a paragraph's
    many, essentially never identical to or beginning with the heading's own short title.

    Returns ``(sections, missing)`` -- ``missing`` names every title this could not find
    at all, the loud, specific failure this whole approach exists to produce instead of a
    section that silently never happened.
    """
    with pymupdf.open(path) as doc:
        raw_lines: list[tuple[int, float, float, str]] = []
        for page_index, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    spans = line.get("spans") or []
                    if not spans:
                        continue
                    line_text = "".join(s["text"] for s in spans).strip()
                    if not line_text:
                        continue
                    raw_lines.append((page_index, line["bbox"][1], spans[0]["size"], line_text))

    # A heading can be drawn as several overlapping draws at nearly the same position, a
    # faux-bold trick -- the same one _pick_sections' own dedup step collapses before its
    # wrap-merge runs. Applied here too, and for the same reason: confirmed necessary on
    # the real "Development" chapter's own 'HUMAN DEVELOPMENT REPORT' banner, drawn as
    # 'HUMAN' x4, then 'HUMAN DEVELOPMENT' once, then 'REPOR' x4, then 'REPORT' once --
    # eight lines of noise sit between 'HUMAN DEVELOPMENT' and 'REPORT', far outside the
    # 3-line lookahead the wrap-merge below uses, so without this collapse first, no
    # candidate ever reads the banner's true, full text and a known title naming it is
    # never found at all.
    deduped: list[tuple[int, float, float, str]] = []
    for page_index, y, size, line_text in raw_lines:
        if deduped and deduped[-1][0] == page_index and abs(y - deduped[-1][1]) < 5:
            if deduped[-1][3] == line_text:
                continue
            shared = _overlap(deduped[-1][3], line_text)
            if shared and deduped[-1][2] == size:
                p, y0, s, acc = deduped[-1]
                deduped[-1] = (p, y0, s, acc + line_text[shared:])
                continue
        deduped.append((page_index, y, size, line_text))
    raw_lines = deduped

    # A title that wraps to two, or more, physical lines on the page ("LAND DEGRADATION
    # AND CONSERVATION" / "MEASURES") needs all of them joined into one candidate to match
    # at all -- the same adjacency test _pick_sections' own wrap-merge uses, applied here
    # to build candidates rather than to merge an already-chosen heading's continuation.
    # Confirmed necessary on the real "Gender, Religion and Caste" chapter's own cover
    # title, which wraps to THREE lines ("Gender," / "Religion and" / "Caste"), not just
    # two -- a fixed two-line join left it unmatchable by any candidate. Chained up to 4
    # lines, matching how many a real chapter title has been seen to wrap to plus one.
    # The allowed gap scales with the line's own size, the same fix and reasoning
    # _pick_sections' own wrap-merge uses: that same cover title draws each line 60pt
    # apart at 65pt type, comfortably beyond a flat 20pt gap but well inside a font that
    # size's own natural line height.
    candidates: list[tuple[str, str]] = []   # (span_text, locate_by)
    for i, (page_index, y, size, line_text) in enumerate(raw_lines):
        candidates.append((line_text, line_text))
        joined = line_text
        prev_y = y
        for j in range(i + 1, min(i + 4, len(raw_lines))):
            next_page, next_y, next_size, next_text = raw_lines[j]
            if next_page != page_index or not (0 < next_y - prev_y < max(20.0, size * 1.2)):
                break
            joined = f"{joined} {next_text}"
            candidates.append((joined, line_text))
            prev_y = next_y

    def key(s: str) -> str:
        # A leading bullet ('• Golden Quadrilateral Super Highways:') is real formatting
        # on a real heading, not a different string -- confirmed on the real "Lifelines
        # of National Economy" chapter, whose own sub-headings are all bulleted list
        # items. Dash variants get the same _DASHES fold title_key already uses
        # elsewhere, confirmed necessary on the real "Agriculture" chapter's own
        # 'Bhoodan – Gramdan' (an en dash), typed here with a plain hyphen.
        s = re.sub(r"^[•\-*]\s*", "", s.strip())
        folded = _APOSTROPHES.sub("'", normalise(s))
        return _DASHES.sub(" - ", folded).casefold()

    cursor = 0
    found: list[tuple[str, str, int]] = []   # (title, locate_by, position)
    missing: list[str] = []
    for wanted_title in titles:
        wanted_key = key(wanted_title)
        exact = [c for c in candidates if key(c[0]) == wanted_key]
        starting = exact or sorted(
            (c for c in candidates if key(c[0]).startswith(wanted_key)),
            key=lambda c: len(c[0]),
        )
        if not starting:
            missing.append(wanted_title)
            continue
        locate_by = starting[0][1]
        pos = text.find(locate_by, cursor)
        if pos == -1:
            pos = text.find(locate_by, 0)
        if pos == -1:
            missing.append(wanted_title)
            continue
        cursor = pos + len(locate_by)
        found.append((wanted_title, locate_by, pos))
    found.sort(key=lambda item: item[2])

    sections: list[Section] = []
    for i, (title, _locate_by, start) in enumerate(found):
        end = found[i + 1][2] if i + 1 < len(found) else len(text)
        sections.append(Section(str(i + 1), title, start, end))
    return sections, missing


def extract_chapter(
    path: str | Path, *, number: int | None = None, name: str = "", title: str = "",
    single_section: bool = False, bare_headings: bool = False, body_bucket: str = "T",
    text_override: str | None = None, known_section_titles: list[str] | None = None,
) -> ChapterExtract:
    """``title`` should come from the contents page where available: matching an existing
    chapter node depends on using the book's own words, not a slug turned back into prose.

    ``number`` and ``name`` exist for callers whose file is not on disk under its real
    name -- an upload written to a temp file, for instance. Deriving them from the path
    would then read a random string and reject a perfectly good chapter.

    ``single_section`` is for a book that genuinely has no subsections at all -- English's
    First Flight and Footprints without Feet are a continuous story or poem, broken only
    by fixed-name checkpoints (BARE_DRILL_LABEL), never by a heading of any kind, numbered
    or bold. Every other book tried has real subheadings somewhere, so the two detection
    passes above stay the default; forcing this on for one of them would hide a real
    extraction failure behind "one section," which is exactly the silent-hole failure mode
    `verify_structure` exists to catch. Scoped by the caller from the subject, not guessed
    here from what the passes happen to find.

    ``body_bucket`` is "E" for the Workbook: a unit there is not expository text a student
    is taught and later drilled on -- the unit's entire body IS the exercise (fill-in-the-
    blank, rearrange-the-jumbled-sentences), so treating it as bucket T would mark the
    subject's only content as un-practised.

    ``text_override`` is for a Hindi book: its own text layer decodes as mojibake (see
    app.ingest.hindi_ocr), so the caller has already had the real text read by OCR or
    Gemini and hands it in here rather than letting this call read_text(path) and get the
    PDF's own broken layer back. ``path`` is still the real file -- used for its sha256 and
    as the ChapterExtract's provenance -- just not for its text.

    ``bare_headings`` is for History: its headings are numbered independently of the
    chapter they are in (BOOK_NUMBERED_SECTION's own docstring -- a bare '1', or a decimal
    subsection under it like '2.1', neither tied to the file's own chapter number), found
    only through boldness. `extract_sections`'s pattern is `{chapter}\.\d+` -- scoped to
    THIS chapter's own number -- and a book that numbers its OWN headings from 1 can
    coincidentally contain a heading numbered the same as the file's chapter: chapter 4's
    real heading '4.1 The Early Entrepreneurs' is heading 4's own first subsection, nothing
    to do with being chapter 4, but it satisfies `{4}\.\d+` all the same. Confirmed on that
    exact real file: extract_sections(text, 4) silently returned two sections ('4.1', '4.2')
    that look like a legitimate, if short, chapter -- not empty, so the boldness fallback
    below never ran -- while the chapter's other five real headings (bare '1', '2', '3',
    '5', '6', all its genuine top-level ones) went missing entirely, and their content was
    never split into a section at all. A wrong non-empty answer defeats the fallback that
    exists precisely for "found nothing" -- so History skips `extract_sections` outright
    rather than risk it succeeding for the wrong reason.
    """
    display = name or Path(path).name
    number = number if number is not None else chapter_number(display)
    if number is None:
        raise ValueError(f"{display!r} is not a chapter file")

    stem = Path(display).stem
    # an NCERT code (jemh101) has no slug to read a title from; the caller supplies one
    derived = stem.split("-", 1)[1].replace("-", " ").title() if "-" in stem else stem
    resolved_title = title or derived

    text = text_override if text_override is not None else read_text(path)
    problems: list[str] = []
    if known_section_titles is not None:
        # Opt-in only -- see _locate_known_sections' own docstring for why this is never
        # the silent default. Missing titles go straight into ``problems``, the same
        # field verify_against_toc populates, so a chapter whose real headings could not
        # all be found is refused exactly the way a TOC disagreement already is, not
        # loaded with some of its real sections quietly absent.
        sections, missing = _locate_known_sections(path, text, known_section_titles)
        if missing:
            problems.append(
                f"{len(missing)} known section(s) could not be found in the chapter's "
                f"own text: {missing!r}"
            )
    elif single_section:
        sections = [Section("1", resolved_title, 0, len(text))]
    elif bare_headings:
        sections = _sections_by_boldness(path, text, resolved_title)
    else:
        sections = extract_sections(text, number, path=path)
        if not sections:
            # Neither convention that reads a number off the page found one -- Geography
            # publishes no section numbers at all, bare or decimal. What is left is
            # typography: the chapter's own largest bold text.
            sections = _sections_by_boldness(path, text, resolved_title)
    return ChapterExtract(
        number=number,
        title=resolved_title,
        source_path=str(path),
        sha256=file_sha256(path),
        sections=sections,
        problems=problems,
        chunks=extract_chunks(
            text, number, sections=sections, body_bucket=body_bucket,
            bare_numbered_questions=single_section,
        ),
    )


def verify_against_toc(extract: ChapterExtract, toc: dict[int, list[Section]]) -> ChapterExtract:
    """Compare with the book's own contents page and record every disagreement.

    A chapter that fails here must not be loaded. A missing or invented section is silent
    once it is in the database: every downstream number is computed against a tree nothing
    contradicts.
    """
    expected = toc.get(extract.number)
    if not expected:
        extract.problems.append(
            f"chapter {extract.number} does not appear in the contents page"
        )
        return extract

    found = {s.number: s.title for s in extract.sections}
    want = {s.number: s.title for s in expected}

    for number, title in want.items():
        if number not in found:
            extract.problems.append(f"missing section {number} {title!r}")
        elif normalise(found[number]).casefold() != normalise(title).casefold():
            extract.problems.append(
                f"section {number} reads {found[number]!r}, contents page says {title!r}"
            )
    for number in found:
        if number not in want:
            extract.problems.append(f"section {number} is not in the contents page")

    if not extract.chunks:
        extract.problems.append("no theorems, examples or exercises found -- check the profile")

    return extract
