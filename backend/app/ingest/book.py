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


def title_key(text: str) -> str:
    """Compare two spellings of the same chapter title.

    Kept apart from ``normalise`` deliberately: normalise feeds stem_hash, and folding
    characters there would change every hash already stored. This only ever compares
    titles, where the difference between an en dash and two hyphens is presentation and
    rejecting a correct chapter over it would be absurd.
    """
    return _DASHES.sub(" - ", normalise(text)).casefold()


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


def parse_toc(contents_pdf: str | Path) -> dict[int, list[Section]]:
    """The expected section tree, from the prelims file, where the book publishes one.

    Maths lists every section of every chapter here, which is what makes a Maths
    extraction checkable. Science does not -- its contents page stops at chapter titles --
    so this returns empty for Science and the caller must fall back to
    ``verify_structure``. Returning empty is the honest answer; inventing an expectation
    would make an unchecked load look checked.
    """
    text = read_text(contents_pdf)
    out: dict[int, list[Section]] = {}
    for number, title in re.findall(r"^\s*(\d+\.\d+)\s+([A-Z][^\n]{2,120})$", text, re.M):
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


def parse_toc_chapters(contents_pdf: str | Path) -> dict[int, str]:
    """Chapter numbers and titles from the contents page.

    Present in most books, and the only thing the Science contents page offers. It still
    verifies something worth verifying: that the file uploaded as chapter 9 is the chapter
    the book calls 9. Tried in the order a book is most likely to use: the word 'Chapter',
    then a bare number before the title (Geography), then a Roman numeral (History, which
    never says 'Chapter'), then position on the page for a table linear text cannot read
    in order (Economics). Each is tried only once the one before it finds nothing, so a
    book that genuinely mixes conventions never has an earlier one swallow a later one's
    numbering.
    """
    text = read_text(contents_pdf)
    for pattern, to_number in (
        (TOC_CHAPTER, int),
        (TOC_CHAPTER_DOTTED, int),
        (TOC_CHAPTER_NUMBERED, int),
        (TOC_CHAPTER_UNIT, int),
        (TOC_CHAPTER_ROMAN, _roman_to_int),
    ):
        found = {to_number(n): title.strip() for n, title in pattern.findall(text)}
        # A real contents page numbers its chapters 1..N with no gaps. A pattern that
        # matched something -- a stray 'Chapter 5' paired with the word 'Appendix' two
        # lines below it in a table it cannot otherwise read -- but not a complete,
        # contiguous run is a false positive, not a partial answer: better to fall
        # through to the next convention than to record one right chapter and silence
        # the rest.
        if found and set(found) == set(range(1, len(found) + 1)):
            return found
    return _toc_chapters_by_position(contents_pdf)


def verify_structure(extract: ChapterExtract) -> ChapterExtract:
    """The checks that survive when the book publishes no section list.

    Weaker than verify_against_toc and deliberately not dressed up as equivalent: nothing
    here can detect a section the extractor never saw at the *end* of a chapter, because
    there is nothing that says how many there should be. What it does catch is a gap in
    the middle -- 9.1, 9.2, 9.4 means 9.3 was missed -- a chapter that yielded no sections
    at all, and one that yielded no drilled content, each of which is a silent hole in the
    knowledge base rather than a visible failure.
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
        extract.problems.append(
            f"chapter {extract.number}: no exercises or questions were found, so no "
            f"question from it could ever be judged PRACTISED"
        )
    return extract


#: History numbers its own headings independent of the chapter: a bare major number with
#: no decimal ('1  The Rise of Nationalism in Europe', two spaces, no dot) or a decimal
#: subsection under it ('2.1 The Aristocracy...', one space) -- '2' there is the second
#: heading IN THIS CHAPTER, not chapter 2. Title may start with a digit ('3.3 1848: The
#: Revolution of the Liberals'), which is why this is not anchored to [A-Z] the way the
#: chapter-numbered pattern is.
#:
#: Matched only against a line already known to be bold (see _sections_by_boldness), not
#: against the plain text of the whole chapter: Political Science's real headings use no
#: number at all, and a *plain* numbered list in its body prose ('1  Power is shared
#: among different organs of government...') matches this exact shape without being a
#: heading. Boldness is the only thing that told the two apart in the real files.
BOOK_NUMBERED_SECTION = re.compile(
    r"^(\d{1,2}(?:\.\d{1,2})?)[ \t]{1,2}([A-Z0-9][^\n]{2,120})$"
)


def extract_sections(text: str, chapter: int) -> list[Section]:
    """Headings for THIS chapter only, with the span each one covers.

    The scoping is the whole point: 'Example 5 : ... = 28.5 m\nTherefore, ...' produced a
    phantom section '28.5 Therefore,' when the pattern was chapter-agnostic.
    """
    pattern = re.compile(rf"^\s*({chapter}\.\d+)\s+([A-Z][^\n]{{2,120}})$", re.M)
    seen: set[str] = set()
    found: list[tuple[str, str, int, int]] = []
    for m in pattern.finditer(text):
        if m.group(1) in seen:      # a running header repeats the section on every page
            continue
        seen.add(m.group(1))
        found.append((m.group(1), m.group(2).strip(), m.start(), m.end()))

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


#: labels that are bold, and often the LARGEST bold text in the chapter -- bigger than
#: every real heading, not smaller -- but are never themselves a heading: an
#: end-of-chapter drill word, or a bare numbered-list marker like '2.'. Matched as a
#: whole line, allowing the word to repeat (EXERCISES is drawn sideways and reads back as
#: 'EXERCISES  EXERCISES  EXERCISES...', the same quirk BARE_DRILL_LABEL absorbs).
#: case-insensitive for the same reason BARE_DRILL_LABEL is: Political Science sets
#: 'Exercises' in title case, at a bold size (100pt in the real file) bigger than any of
#: its real headings -- an exact-caps-only match let it through as a candidate, and being
#: the only line at that size, it became the chapter's entire heading list.
_NOT_A_HEADING = re.compile(
    r"^(EXERCISES|QUESTIONS|PROJECT|ACTIVITY|PROJECT/ACTIVITY|PROJECT WORK|DISCUSS|"
    r"MAP SKILLS|MAP WORK|WRITE IN BRIEF|SUGGESTED READINGS|ADDITIONAL PROJECTS\s*/\s*"
    r"ACTIVITIES|BIBLIOGRAPHY|FURTHER READING|GLOSSARY|LET.S WORK (?:THESE|THIS) OUT|"
    r"NOTES? FOR THE TEACHERS?)"
    r"(\s+\1)*$",
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
                    if not all(s["flags"] & 16 for s in spans):
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
    deduped: list[tuple[int, float, float, str, int | None]] = []
    for entry in lines:
        page_index, y, _size, line_text, _colour = entry
        if (
            deduped and deduped[-1][3] == line_text and deduped[-1][0] == page_index
            and abs(y - deduped[-1][1]) < 3
        ):
            continue
        deduped.append(entry)
    lines = deduped

    # Only used on the size-based attempt: the cover repeats the chapter's own title in
    # the same ink used for its real headings, and that attempt's own noise (an oversized
    # story caption, a drill label) is not excludable by keyword the way EXERCISES or
    # PROJECT is. The bold attempt never reaches here with this on -- it doesn't need it,
    # and a book whose cover happens to share a colour with something else entirely
    # would otherwise lose real headings to a filter it never asked for.
    heading_colour = (
        next(
            (c for _p, _y, _s, t, c in lines if c is not None and _CHAPTER_COVER.match(t)),
            None,
        )
        if filter_by_cover_colour
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
    title_key_ = title_key(chapter_title) if chapter_title else None
    candidates = [
        (page_index, y, size, line_text)
        for page_index, y, size, line_text, colour in lines
        if not re.fullmatch(r"\d{1,3}\.?", line_text)
        and re.search(r"[A-Za-z]", line_text)   # a decorative glyph ('+') has no letters
        and not _NOT_A_HEADING.match(line_text)
        and not _CHAPTER_COVER.match(line_text)
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
    numbered = [
        (page_index, y, m.group(1), m.group(2).strip())
        for page_index, y, _size, line_text in candidates
        if (m := BOOK_NUMBERED_SECTION.match(line_text))
    ]
    if len(numbered) >= 2:
        seen_numbers: set[str] = set()
        found: list[tuple[str, str, int]] = []
        cursor = 0
        for _page_index, _y, number, title in numbered:
            if number in seen_numbers:
                continue
            seen_numbers.add(number)
            pos = text.find(title, cursor)
            if pos == -1:
                continue
            found.append((number, title, pos))
            cursor = pos + len(title)
        sections = []
        for i, (number, title, start) in enumerate(found):
            end = found[i + 1][2] if i + 1 < len(found) else len(text)
            sections.append(Section(number, title, start, end))
        return sections

    heading_size = max(size for _p, _y, size, _t in candidates)
    headings = [
        (page_index, y, line_text)
        for page_index, y, size, line_text in candidates
        if size == heading_size
    ]

    # A title that wraps to a second line is still one heading: merge it into the line
    # above when the two are close together on the same page, but keep the FIRST line's
    # own text for locating the heading in `text` -- the join here is cosmetic only, and
    # searching for a two-line title as one string would depend on exactly how read_text
    # rejoins lines, which this function has no reason to assume.
    merged: list[tuple[str, str]] = []   # (locate_by, display_title)
    previous: tuple[int, float] | None = None
    for page_index, y, line_text in headings:
        if previous is not None and previous[0] == page_index and 0 < y - previous[1] < 20:
            locate_by, title = merged[-1]
            merged[-1] = (locate_by, f"{title} {line_text}")
        else:
            merged.append((line_text, line_text))
        previous = (page_index, y)

    sections: list[Section] = []
    cursor = 0
    found: list[tuple[str, str, int]] = []
    for locate_by, title in merged:
        pos = text.find(locate_by, cursor)
        if pos == -1:      # read_text folded whitespace this function did not predict
            continue
        found.append((str(len(found) + 1), title, pos))
        cursor = pos + len(locate_by)

    for i, (number, title, start) in enumerate(found):
        end = found[i + 1][2] if i + 1 < len(found) else len(text)
        sections.append(Section(number, title, start, end))
    return sections


def _sections_by_boldness(path: str | Path, text: str, chapter_title: str = "") -> list[Section]:
    """Headings for a book that numbers nothing at all -- Geography publishes no section
    list on its contents page and its subheadings carry no number of their own, bare or
    decimal. What marks a real heading is typography: bold, and at the largest bold size
    used anywhere in the chapter, tried first since it is what every book but one uses.
    Economics sets its real headings in a custom embedded subset font that carries no
    bold flag at all -- only a size visibly larger than the body -- so a second attempt
    on that looser signal runs only when the bold one finds nothing usable at all, never
    blended into it.

    Section 'numbers' are just 1, 2, 3... in reading order: the book gives none, so
    inventing a false one there would be worse than admitting there isn't one. Found by
    font, but *located* by searching the plain text for it, so the character offsets this
    returns line up with the same ``text`` extract_chunks slices -- a PDF-native offset
    would not.
    """
    with pymupdf.open(path) as doc:
        bold_lines = _heading_styled_lines(doc, require_bold=True)
        by_bold = _pick_sections(bold_lines, text, chapter_title, filter_by_cover_colour=False)
        if by_bold:
            return by_bold

        body_chars: dict[float, int] = {}
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for s in line.get("spans") or []:
                        size = round(s["size"], 1)
                        body_chars[size] = body_chars.get(size, 0) + len(s["text"])
        body_size = max(body_chars, key=lambda s: body_chars[s]) if body_chars else 0.0
        sized_lines = _heading_styled_lines(doc, require_bold=False, body_size=body_size)
        return _pick_sections(sized_lines, text, chapter_title, filter_by_cover_colour=True)


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
    if bare_numbered_questions:
        for n, m in enumerate(ENGLISH_NUMBERED_QUESTION.finditer(text), start=1):
            lookback = text[max(0, m.start() - 40):m.start()].rstrip()
            if lookback.endswith(_TEACHER_INSTRUCTION_LABEL):
                continue
            markers.append((m.start(), "exercise", "E", f"Question {chapter}.{n}"))

    markers.sort()
    # A reference appearing twice is a back-reference in body text, not a restatement:
    # "Theorem 6.1: Fig. 6.11" is a figure caption. The statement always comes first.
    seen: set[str] = set()
    markers = [m for m in markers if not (m[3] in seen or seen.add(m[3]))]

    chunks: list[Chunk] = []
    for section in sections if sections is not None else extract_sections(text, chapter):
        inside = [m for m in markers if section.start <= m[0] < section.end]
        boundaries = [m[0] for m in inside] + [section.end]

        body = text[section.start:boundaries[0]].strip()
        if len(body) >= MIN_BODY_CHARS:
            chunks.append(
                Chunk(body_bucket, "body" if body_bucket == "T" else "exercise",
                      f"Section {section.number}", body, stem_hash(body),
                      section=section.number)
            )

        for i, (start, kind, bucket, reference) in enumerate(inside):
            stop = boundaries[i + 1]
            piece = text[start:stop].strip()
            chunks.append(
                Chunk(bucket, kind, reference, piece, stem_hash(piece),
                      section=section.number, examinable=not optional.get(start, False))
            )

    return chunks


def extract_chapter(
    path: str | Path, *, number: int | None = None, name: str = "", title: str = "",
    single_section: bool = False, body_bucket: str = "T",
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
    """
    display = name or Path(path).name
    number = number if number is not None else chapter_number(display)
    if number is None:
        raise ValueError(f"{display!r} is not a chapter file")

    stem = Path(display).stem
    # an NCERT code (jemh101) has no slug to read a title from; the caller supplies one
    derived = stem.split("-", 1)[1].replace("-", " ").title() if "-" in stem else stem
    resolved_title = title or derived

    text = read_text(path)
    if single_section:
        sections = [Section("1", resolved_title, 0, len(text))]
    else:
        sections = extract_sections(text, number)
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
