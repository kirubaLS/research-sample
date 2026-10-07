"""The Social Science taxonomy, written out for a prompt, from the audited book map.

A prompt mapper is only as good as the list of topics it may choose from, and a list typed
by hand drifts from the books: topics go missing (every individual crop, the soil types, the
consumer-court section), and topics get added that the book does not have. This builds the
list from the same reference files the rest of the system reads, so every section and
sub-section the book has is a choice, nothing the book lacks is, and a new edition is a data
change, not a prompt edit.

Read only: it never touches the database and never writes. New module; nothing existing
calls it.

IDs are short and readable -- ``H5`` for the fifth History chapter, ``H5.3.2`` for its section
3.2 -- and are translated back to the real chapter code and printed section number
(``X.HIST.PRINTCULTURE``, ``3.2``) for every answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.curriculum.book_map import REFERENCE, UNIT_FILES, major_of

#: subject code -> chapter id prefix, and the order they are listed in
SUBJECTS = (("X.HIST", "H"), ("X.GEO", "G"), ("X.POL", "P"), ("X.ECO", "E"))
#: the paper-section letter that fixes the subject of a Social Science question
SECTION_SUBJECT = {"A": "X.HIST", "B": "X.GEO", "C": "X.POL", "D": "X.ECO"}
#: units that are never a topic of their own: their words belong to their parent
_NOT_TOPICS = {"box", "intro", "summary"}
#: terms kept per topic as hints; enough to tell neighbours apart, few enough to stay cheap
KEYWORDS_PER_TOPIC = 10


@dataclass(frozen=True)
class Topic:
    id: str                    # "H5.3.2"
    number: str                # "3.2", as the book prints it
    title: str
    depth: int
    chapter_id: str
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chapter:
    id: str                    # "H5"
    code: str                  # "X.HIST.PRINTCULTURE"
    title: str
    subject: str               # "X.HIST"
    topics: tuple[Topic, ...] = ()


@dataclass
class Taxonomy:
    chapters: list[Chapter] = field(default_factory=list)

    def chapter(self, chapter_id: str | None) -> Chapter | None:
        return next((c for c in self.chapters if c.id == chapter_id), None)

    def topic(self, topic_id: str | None) -> Topic | None:
        if not topic_id:
            return None
        for c in self.chapters:
            for t in c.topics:
                if t.id == topic_id:
                    return t
        return None

    @property
    def topic_count(self) -> int:
        return sum(len(c.topics) for c in self.chapters)

    def of_subject(self, subject: str | None) -> list[Chapter]:
        return [c for c in self.chapters if subject is None or c.subject == subject]


def _clean(text: str) -> str:
    return " ".join((text or "").replace("’", "'").replace("‘", "'").split())


def _title(raw: str) -> str:
    """Section titles are sometimes printed in capitals (Economics); read them as titles."""
    raw = _clean(raw)
    return raw.capitalize() if raw.isupper() else raw


_KEY = re.compile(r"\bKey:\s*(.*)$", re.S)


@lru_cache(maxsize=1)
def _cards() -> dict[str, dict[str, str]]:
    """chapter code -> section number -> its card text (which ends in ``Key: term; term``)."""
    path = REFERENCE / "book_map" / "section_cards.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        code: {str(num): text for num, text in (info.get("cards") or {}).items()}
        for code, info in data.items()
    }


def _keywords(chapter_code: str, number: str, extra: list[str]) -> tuple[str, ...]:
    """Terms that say what is in a section: its card's key terms, then the titles of any
    boxes under it (a dam, a scheme), which a question can name without the section's own
    title appearing anywhere."""
    out: list[str] = []
    card = _cards().get(chapter_code, {}).get(number, "")
    match = _KEY.search(card)
    if match:
        out += [_clean(t) for t in match.group(1).split(";")]
    out += [_clean(t) for t in extra]
    seen: set[str] = set()
    kept = []
    for term in out:
        low = term.lower()
        if _is_a_hint(term) and low not in seen:
            seen.add(low)
            kept.append(term[:40])
    return tuple(kept[:KEYWORDS_PER_TOPIC])


#: a card's key terms include ordinary words ("clear", "introduced") that say nothing about
#: where a topic is. A hint must be a name, a date, a figure or a short named phrase, and must
#: not be the start of a sentence that was cut off.
_SENTENCE_STARTERS = {
    "but", "so", "in", "on", "at", "it", "its", "this", "that", "these", "those", "there",
    "discuss", "since", "born", "professor", "as", "when", "while", "after", "before",
    "during", "some", "many", "most", "all", "each", "if", "then", "thus", "how", "why", "what",
    "today", "you", "we", "they", "he", "she", "his", "her", "their", "our", "for", "with",
}


def _is_a_hint(term: str) -> bool:
    if len(term) < 3 or len(term.split()) > 5:
        return False
    first = term.split()[0].lower().strip(",.")
    if first in _SENTENCE_STARTERS:
        return False
    if term.isupper() and len(term.split()) > 2:      # a shouted caption, not a name
        return False
    return term[0].isupper() or any(c.isdigit() for c in term)


@lru_cache(maxsize=1)
def build() -> Taxonomy:
    """Every chapter of the four Social Science books, with every section and sub-section."""
    chapters: list[Chapter] = []
    for subject, prefix in SUBJECTS:
        path = REFERENCE / UNIT_FILES[subject]
        data = json.loads(path.read_text(encoding="utf-8"))
        for index, ch in enumerate(data, start=1):
            chapter_id = f"{prefix}{index}"
            units = ch.get("units", [])
            boxes: dict[str, list[str]] = {}
            for u in units:
                if u.get("kind") != "box":
                    continue
                # a box sits under the section whose number it extends ("2.1" under "2")
                number = str(u.get("number") or "")
                owner = number.rsplit(".", 1)[0] if "." in number else ""
                if owner:
                    boxes.setdefault(owner, []).append(u.get("title") or "")
            topics = []
            for u in units:
                number = u.get("number")
                if not number or u.get("kind") in _NOT_TOPICS:
                    continue
                number = str(number)
                topics.append(Topic(
                    id=f"{chapter_id}.{number}", number=number, title=_title(u.get("title") or ""),
                    depth=number.count(".") + 1, chapter_id=chapter_id,
                    keywords=_keywords(ch["code"], number, boxes.get(number, [])),
                ))
            chapters.append(Chapter(chapter_id, ch["code"], _title(ch["title"]), subject, tuple(topics)))
    return Taxonomy(chapters)


def render(taxonomy: Taxonomy | None = None, subjects: set[str] | None = None) -> str:
    """The taxonomy as the prompt shows it: indented by depth, one line per topic, hints after."""
    taxonomy = taxonomy or build()
    lines: list[str] = []
    for ch in taxonomy.chapters:
        if subjects is not None and ch.subject not in subjects:
            continue
        lines.append(f"{ch.id} | {ch.title}")
        for t in ch.topics:
            hint = f"  [{'; '.join(t.keywords)}]" if t.keywords else ""
            lines.append(f"{'  ' * t.depth}{t.id} | {t.title}{hint}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def major_topic(chapter: Chapter, topic: Topic | None, depth: int = 2) -> str | None:
    """The two-level topic the reports and gold keys use for this topic."""
    if topic is None:
        return None
    return major_of(chapter.code, topic.number, depth)
