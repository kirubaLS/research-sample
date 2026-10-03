"""Printed text -> curriculum subjects and chapters, deterministically. No model is asked.

A question paper often says what it covers: a section header "SECTION B (Geography :
Minerals and Energy Resources)", a cover line "Syllabus: History Ch 1-2, Geography Ch 1,
3". This module turns that text into subject codes and chapter codes, so the scope a
question is placed in can come from what the paper itself prints.

Three kinds of evidence are read, and nothing else:

* **Subject words** -- History, Geography, Political Science / Civics / Democratic
  Politics, Economics, and their Hindi forms.
* **Chapter numbers** -- "Ch 3", "Chapter 1-2", "Ch. 1, 3", "Unit 2", "Lesson IV" --
  counted only when a subject word in the same stretch of text says which book they number,
  or when the caller says the paper is one book (``default_subject``).
* **Chapter titles** -- the curriculum's own chapter labels plus ``taxonomy_alias`` rows,
  matched on normalised tokens (case, punctuation and "&"/"and" ignored, near-spellings
  such as "Globalization" accepted) inside a short window of the text.

Below the threshold nothing is returned. A wrong scope is worse than none: it confines a
question to the wrong chapters, so an unclear title must leave the scope to the next
source rather than guess.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.curriculum import CURRICULA

#: A title match must cover at least this share of the title's content words.
TITLE_THRESHOLD = 0.8
#: Two spellings of one word ("globalisation", "globalization") count as the same word
#: at or above this similarity; shorter words must match exactly.
TOKEN_SIMILARITY = 0.85
_FUZZY_MIN_LEN = 5

#: Words printed for each book. Only subjects present in the caller's group are used, so
#: a word never reaches outside the paper's own subject.
SUBJECT_WORDS: dict[str, tuple[str, ...]] = {
    "X.HIST": ("history", "इतिहास"),
    "X.GEO": ("geography", "भूगोल"),
    "X.POL": (
        "political science", "pol science", "pol sci", "civics", "democratic politics",
        "राजनीति विज्ञान", "राजनीतिक विज्ञान", "नागरिक शास्त्र", "लोकतांत्रिक राजनीति",
    ),
    "X.ECO": ("economics", "अर्थशास्त्र"),
}

#: Words that carry no meaning in a chapter title.
_STOPWORDS = frozenset({"the", "and", "of", "in", "a", "an", "to", "its", "for", "on"})

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
          "ix": 9, "x": 10, "xi": 11, "xii": 12}
_NUMBER = r"(?:\d{1,2}|x{0,1}(?:ix|iv|v?i{0,3}))"
#: 'ch 3', 'ch. 1-2', 'chapter 1, 3 & 5', 'chapters 1 to 3', 'unit 2', 'lesson iv', 'l-3'
_CHAPTER_NUMBERS = re.compile(
    r"\b(?:ch(?:apter)?s?|units?|lessons?|l)\s*\.?\s*[-:#]?\s*"
    r"(" + _NUMBER + r"(?:\s*(?:,|and|to|-|–|—|/)\s*" + _NUMBER + r")*)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChapterMatch:
    chapter_code: str
    subject_code: str
    score: float
    #: "number" (Ch 3 under a subject word) or "title" (the chapter's name or an alias)
    via: str


@dataclass
class Resolution:
    #: subject code -> score, for every subject the text names (directly or by a chapter)
    subjects: dict[str, float] = field(default_factory=dict)
    #: chapter code -> its best match
    chapters: dict[str, ChapterMatch] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.subjects and not self.chapters

    def chapter_codes(self) -> set[str]:
        return set(self.chapters)

    def subject_codes(self) -> set[str]:
        return set(self.subjects)

    def _add_chapter(self, match: ChapterMatch) -> None:
        held = self.chapters.get(match.chapter_code)
        if held is None or match.score > held.score:
            self.chapters[match.chapter_code] = match
        self.subjects[match.subject_code] = max(
            self.subjects.get(match.subject_code, 0.0), match.score
        )


def normalise(text: str) -> str:
    """Lower case, '&' read as 'and', punctuation as space, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = text.replace("&", " and ")
    # keep letters (any script), combining marks and digits; everything else separates
    text = "".join(
        ch if (unicodedata.category(ch)[0] in "LMN") else " " for ch in text
    )
    return " ".join(text.split())


def _content_tokens(text: str) -> list[str]:
    return [t for t in normalise(text).split() if t not in _STOPWORDS]


def _same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < _FUZZY_MIN_LEN:
        return False
    return SequenceMatcher(None, a, b).ratio() >= TOKEN_SIMILARITY


def _title_score(title_tokens: list[str], text_tokens: list[str]) -> float:
    """Best share of the title's words found inside one short window of the text."""
    if not title_tokens or not text_tokens:
        return 0.0
    width = len(title_tokens) + 2
    best = 0.0
    for start, token in enumerate(text_tokens):
        if not any(_same_word(token, t) for t in title_tokens):
            continue
        window = text_tokens[start:start + width]
        found = sum(1 for t in title_tokens if any(_same_word(w, t) for w in window))
        best = max(best, found / len(title_tokens))
        if best == 1.0:
            break
    return best


def _parse_numbers(spec: str) -> list[int]:
    """'1-2' -> [1, 2]; '1, 3 and 5' -> [1, 3, 5]; 'ii to iv' -> [2, 3, 4]."""
    spec = spec.casefold()
    parts = re.split(r"\s*(,|and|/)\s*", spec)
    out: list[int] = []
    for part in parts:
        part = part.strip()
        if not part or part in {",", "and", "/"}:
            continue
        span = re.split(r"\s*(?:to|-|–|—)\s*", part)
        values = [_number(v) for v in span if v.strip()]
        values = [v for v in values if v is not None]
        if len(values) == 2 and values[0] <= values[1] and values[1] - values[0] <= 12:
            out.extend(range(values[0], values[1] + 1))
        elif len(values) == 1:
            out.append(values[0])
    return out


def _number(token: str) -> int | None:
    token = token.strip().casefold()
    if token.isdigit():
        return int(token)
    return _ROMAN.get(token)


def _light(text: str) -> str:
    """Case and '&' normalised, punctuation KEPT: '1-2' and '1, 3' must survive."""
    return unicodedata.normalize("NFKC", text or "").casefold().replace("&", " and ")


def _subject_spans(text: str, subject_codes: list[str]) -> list[tuple[int, int, str]]:
    """(start, end, subject) for every subject word in ``text`` (``_light`` form)."""
    spans: list[tuple[int, int, str]] = []
    for code in subject_codes:
        for word in SUBJECT_WORDS.get(code, ()):
            words = normalise(word).split()
            pattern = re.compile(
                r"(?<!\w)" + r"\W+".join(re.escape(w) for w in words) + r"(?!\w)"
            )
            for m in pattern.finditer(text):
                spans.append((m.start(), m.end(), code))
    spans.sort()
    # a longer phrase wins over a word inside it ('political science' over nothing shorter)
    kept: list[tuple[int, int, str]] = []
    for span in spans:
        if kept and span[0] < kept[-1][1]:
            if span[1] - span[0] > kept[-1][1] - kept[-1][0]:
                kept[-1] = span
            continue
        kept.append(span)
    return kept


def resolve_text(
    text: str,
    subject_codes: list[str],
    aliases: dict[str, list[str]] | None = None,
    *,
    default_subject: str | None = None,
    threshold: float = TITLE_THRESHOLD,
) -> Resolution:
    """Which of ``subject_codes``' books and chapters ``text`` names.

    ``aliases`` maps a chapter code to extra names for it (``taxonomy_alias`` rows; see
    ``load_chapter_aliases``). ``default_subject`` is the book that chapter numbers refer to
    when the text names no subject -- only meaningful for a one-book paper; for a group
    paper leave it None so a bare "Ch 3" resolves to nothing rather than to a guess.
    """
    out = Resolution()
    if not normalise(text):
        return out
    light = _light(text)
    subjects = [c for c in subject_codes if c in CURRICULA]

    # --- subject words --------------------------------------------------------------
    spans = _subject_spans(light, subjects)
    for _, _, code in spans:
        out.subjects[code] = 1.0

    # --- chapter numbers, read in the stretch after each subject word ----------------
    stretches: list[tuple[str, str]] = []
    for i, (_, end, code) in enumerate(spans):
        stop = spans[i + 1][0] if i + 1 < len(spans) else len(light)
        stretches.append((code, light[end:stop]))
    if not spans and default_subject in subjects:
        stretches.append((default_subject, light))
    for code, stretch in stretches:
        chapters = CURRICULA[code].chapters
        for m in _CHAPTER_NUMBERS.finditer(stretch):
            for n in _parse_numbers(m.group(1)):
                if 1 <= n <= len(chapters):
                    out._add_chapter(ChapterMatch(chapters[n - 1].code, code, 1.0, "number"))

    # --- chapter titles and aliases ----------------------------------------------------
    named = set(out.subjects) or set(subjects)
    text_tokens = _content_tokens(text)
    title_hits: list[tuple[ChapterMatch, frozenset[str]]] = []
    for code in subjects:
        if code not in named:
            # a subject word restricts titles to the books it names
            continue
        for chapter in CURRICULA[code].chapters:
            names = [chapter.label, *(aliases or {}).get(chapter.code, [])]
            best, best_tokens = 0.0, frozenset()
            for name in names:
                tokens = _content_tokens(name)
                score = _title_score(tokens, text_tokens)
                if score > best:
                    best, best_tokens = score, frozenset(tokens)
            if best >= threshold:
                title_hits.append(
                    (ChapterMatch(chapter.code, code, round(best, 3), "title"), best_tokens)
                )
    # A title whose words are all inside another matched title is that other title, not a
    # second chapter: 'Development' inside 'Resources and Development'.
    for match, tokens in title_hits:
        shadowed = any(
            other is not match and tokens < other_tokens
            for other, other_tokens in title_hits
        )
        if not shadowed:
            out._add_chapter(match)
    return out


def load_chapter_aliases(db, subject_codes: list[str]) -> dict[str, list[str]]:
    """``taxonomy_alias`` rows of the chapters of ``subject_codes``, by chapter code."""
    from sqlalchemy import select

    from app.models import TaxonomyAlias, TaxonomyNode

    prefixes = tuple(f"{c}." for c in subject_codes)
    rows = db.execute(
        select(TaxonomyNode.code, TaxonomyAlias.alias)
        .join(TaxonomyAlias, TaxonomyAlias.node_id == TaxonomyNode.id)
        .where(TaxonomyNode.kind == "chapter")
    ).all()
    out: dict[str, list[str]] = {}
    for code, alias in rows:
        if code.startswith(prefixes):
            out.setdefault(code, []).append(alias)
    return out
