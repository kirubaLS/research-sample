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


@dataclass(frozen=True)
class Section:
    number: str          # '12.2'
    title: str           # 'Volume of Combination of Solids'
    start: int = -1      # character offset of the heading, for body-text attribution
    end: int = -1


@dataclass(frozen=True)
class Chunk:
    bucket: str          # 'T' | 'E'
    kind: str            # 'body' | 'theorem' | 'example' | 'exercise'
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

    @property
    def ok(self) -> bool:
        return not self.problems

    def counts(self) -> dict[str, int]:
        out = {"sections": len(self.sections), "body": 0, "theorem": 0, "example": 0,
               "exercise": 0}
        for c in self.chunks:
            out[c.kind] = out.get(c.kind, 0) + 1
        return out


def normalise(text: str) -> str:
    """Fold presentation noise. Digits survive -- they are what make a stem specific."""
    return re.sub(r"\s+", " ", text).strip()


def stem_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def read_text(path: str | Path) -> str:
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


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
    """The expected tree, from the prelims file. This is what makes verification possible."""
    text = read_text(contents_pdf)
    out: dict[int, list[Section]] = {}
    for number, title in re.findall(r"^\s*(\d+\.\d+)\s+([A-Z][^\n]{2,60})$", text, re.M):
        chapter = int(number.split(".")[0])
        out.setdefault(chapter, []).append(Section(number, title.strip()))
    return out


def extract_sections(text: str, chapter: int) -> list[Section]:
    """Headings for THIS chapter only, with the span each one covers.

    The scoping is the whole point: 'Example 5 : ... = 28.5 m\nTherefore, ...' produced a
    phantom section '28.5 Therefore,' when the pattern was chapter-agnostic.
    """
    pattern = re.compile(rf"^\s*({chapter}\.\d+)\s+([A-Z][^\n]{{2,60}})$", re.M)
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
    for m in EXAMPLE.finditer(text):
        markers.append((m.start(), "example", "T", f"Example {m.group(1)}"))
        optional[m.start()] = bool(m.group(2))
    for m in EXERCISE.finditer(text):
        markers.append((m.start(), "exercise", "E", f"EXERCISE {m.group(1)}"))
        optional[m.start()] = bool(m.group(2))

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
