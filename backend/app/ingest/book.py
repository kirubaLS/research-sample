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
#: bucket E for Science, which numbers nothing. Questions appear mid-chapter after each
#: teaching block and EXERCISES closes the chapter; both are drilled, so a question
#: resembling one is PRACTISED. Matched only after the vertical-heading collapse in
#: read_text -- the book sets these one character per line.
SCIENCE_DRILL = re.compile(r"^\s*(QUESTIONS|EXERCISES)\s*$", re.M)


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


#: 'Chapter 9' then the title on the following line, as the Science prelims sets it
TOC_CHAPTER = re.compile(r"^\s*Chapter\s+(\d{1,2})\s*$\n^\s*(\S[^\n]{2,80})$", re.M)


def parse_toc_chapters(contents_pdf: str | Path) -> dict[int, str]:
    """Chapter numbers and titles from the contents page.

    Present in both books, and the only thing the Science contents page offers. It still
    verifies something worth verifying: that the file uploaded as chapter 9 is the chapter
    the book calls 9.
    """
    text = read_text(contents_pdf)
    return {int(n): title.strip() for n, title in TOC_CHAPTER.findall(text)}


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

    indexes = sorted(int(n.split(".")[1]) for n in numbers)
    if indexes[0] != 1:
        extract.problems.append(
            f"chapter {extract.number}: sections start at {extract.number}.{indexes[0]}, "
            f"so {extract.number}.1 was missed"
        )
    for lower, upper in zip(indexes, indexes[1:], strict=False):
        if upper != lower + 1:
            missing = ", ".join(
                f"{extract.number}.{n}" for n in range(lower + 1, upper)
            )
            extract.problems.append(f"chapter {extract.number}: missing section {missing}")

    if not any(c.bucket == "E" for c in extract.chunks):
        extract.problems.append(
            f"chapter {extract.number}: no exercises or questions were found, so no "
            f"question from it could ever be judged PRACTISED"
        )
    return extract


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

    sections: list[Section] = []
    for i, (number, title, _start, heading_end) in enumerate(found):
        end = found[i + 1][2] if i + 1 < len(found) else len(text)
        sections.append(Section(number, title, heading_end, end))
    return sections


#: below this a "body" slice is a page header or a stray caption, not taught content
MIN_BODY_CHARS = 200


def extract_chunks(text: str, chapter: int) -> list[Chunk]:
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
    # Science repeats the bare word QUESTIONS several times in a chapter, so the
    # occurrence is numbered to keep the reference unique -- an identical reference is
    # dropped below as a back-reference, which would have thrown away every block but the
    # first and emptied the drilled bucket for the subject.
    for n, m in enumerate(SCIENCE_DRILL.finditer(text), start=1):
        label = m.group(1).title()
        markers.append((m.start(), "exercise", "E", f"{label} {chapter}.{n}"))

    markers.sort()
    # A reference appearing twice is a back-reference in body text, not a restatement:
    # "Theorem 6.1: Fig. 6.11" is a figure caption. The statement always comes first.
    seen: set[str] = set()
    markers = [m for m in markers if not (m[3] in seen or seen.add(m[3]))]

    chunks: list[Chunk] = []
    for section in extract_sections(text, chapter):
        inside = [m for m in markers if section.start <= m[0] < section.end]
        boundaries = [m[0] for m in inside] + [section.end]

        body = text[section.start:boundaries[0]].strip()
        if len(body) >= MIN_BODY_CHARS:
            chunks.append(
                Chunk("T", "body", f"Section {section.number}", body, stem_hash(body),
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
    path: str | Path, *, number: int | None = None, name: str = "", title: str = ""
) -> ChapterExtract:
    """``title`` should come from the contents page where available: matching an existing
    chapter node depends on using the book's own words, not a slug turned back into prose.

    ``number`` and ``name`` exist for callers whose file is not on disk under its real
    name -- an upload written to a temp file, for instance. Deriving them from the path
    would then read a random string and reject a perfectly good chapter.
    """
    display = name or Path(path).name
    number = number if number is not None else chapter_number(display)
    if number is None:
        raise ValueError(f"{display!r} is not a chapter file")

    stem = Path(display).stem
    # an NCERT code (jemh101) has no slug to read a title from; the caller supplies one
    derived = stem.split("-", 1)[1].replace("-", " ").title() if "-" in stem else stem

    text = read_text(path)
    return ChapterExtract(
        number=number,
        title=title or derived,
        source_path=str(path),
        sha256=file_sha256(path),
        sections=extract_sections(text, number),
        chunks=extract_chunks(text, number),
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
