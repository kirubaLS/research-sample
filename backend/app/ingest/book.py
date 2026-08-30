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


@dataclass(frozen=True)
class Chunk:
    bucket: str          # 'T' | 'E'
    kind: str            # 'theorem' | 'example' | 'exercise'
    reference: str       # 'Theorem 1.3', 'Example 4', 'EXERCISE 12.1'
    text: str
    stem_hash: str
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
        out = {"sections": len(self.sections), "theorem": 0, "example": 0, "exercise": 0}
        for c in self.chunks:
            out[c.kind] += 1
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


def chapter_number(path: str | Path) -> int | None:
    """From '12-surface-areas-and-volumes.pdf'. None for contents, answers, appendices."""
    m = re.match(r"^(\d{2})-", Path(path).name)
    return int(m.group(1)) if m else None


def parse_toc(contents_pdf: str | Path) -> dict[int, list[Section]]:
    """The expected tree, from the prelims file. This is what makes verification possible."""
    text = read_text(contents_pdf)
    out: dict[int, list[Section]] = {}
    for number, title in re.findall(r"^\s*(\d+\.\d+)\s+([A-Z][^\n]{2,60})$", text, re.M):
        chapter = int(number.split(".")[0])
        out.setdefault(chapter, []).append(Section(number, title.strip()))
    return out


def extract_sections(text: str, chapter: int) -> list[Section]:
    """Headings for THIS chapter only.

    The scoping is the whole point: 'Example 5 : ... = 28.5 m\\nTherefore, ...' produced a
    phantom section '28.5 Therefore,' when the pattern was chapter-agnostic.
    """
    pattern = re.compile(rf"^\s*({chapter}\.\d+)\s+([A-Z][^\n]{{2,60}})$", re.M)
    seen: set[str] = set()
    sections: list[Section] = []
    for number, title in pattern.findall(text):
        if number in seen:          # a running header repeats the section on every page
            continue
        seen.add(number)
        sections.append(Section(number, title.strip()))
    return sections


def extract_chunks(text: str) -> list[Chunk]:
    """Split into the two familiarity buckets, using the book's own labels.

    Every marker is sorted into ONE ordered list before slicing. Slicing each kind
    separately made a chunk run to the next marker *of its own kind*: Theorem 1.1 ran all
    the way to Theorem 1.2 and swallowed Examples 1 to 4 along the way, so bucket T
    chunks overlapped each other and carried text belonging to other procedures.
    """
    markers: list[tuple[int, str, str, str]] = []   # (position, kind, bucket, reference)
    optional: dict[int, bool] = {}
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
    # "Theorem 6.1: Fig. 6.11" is a figure caption. The real statement always comes first,
    # so later occurrences are dropped and their text stays with the surrounding chunk.
    seen: set[str] = set()
    markers = [m for m in markers if not (m[3] in seen or seen.add(m[3]))]

    chunks: list[Chunk] = []
    for i, (start, kind, bucket, reference) in enumerate(markers):
        stop = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        body = text[start:stop].strip()
        chunks.append(
            Chunk(
                bucket, kind, reference, body, stem_hash(body),
                examinable=not optional.get(start, False),
            )
        )
    return chunks


def extract_chapter(path: str | Path, *, title: str = "") -> ChapterExtract:
    """``title`` should come from the contents page where available: matching an existing
    chapter node depends on using the book's own words, not a slug turned back into prose.
    """
    number = chapter_number(path)
    if number is None:
        raise ValueError(f"{Path(path).name!r} is not a numbered chapter file")

    text = read_text(path)
    return ChapterExtract(
        number=number,
        title=title or Path(path).stem.split("-", 1)[1].replace("-", " ").title(),
        source_path=str(path),
        sha256=file_sha256(path),
        sections=extract_sections(text, number),
        chunks=extract_chunks(text),
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
