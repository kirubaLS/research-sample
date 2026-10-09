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
import math
import re
from collections import Counter
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
KEYWORDS_PER_TOPIC = 8
#: a topic with fewer terms than this gets its sub-topics' best terms added (a parent whose own text is short)
MIN_TERMS = 4


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


# --- hints derived from each section's own text -------------------------------------------------
# A hint is a name, a date, an acronym, a glossary term or a rare content word that the section
# uses and its neighbours do not: what a question about it is likely to contain. Ranked
# TF-IDF style across the book's sections, so "Vernacular Press Act" beats "India".

_CAP_WORD = r"[A-Z][A-Za-z'’\-]+"
_NAME = re.compile(rf"\b{_CAP_WORD}(?:\s+(?:of|the|and|de|von|in|for)\s+{_CAP_WORD}|\s+{_CAP_WORD}){{0,3}}")
_ACRONYM = re.compile(r"\b[A-Z]{2,6}s?\b")
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-4][0-9])\b")
_WORD = re.compile(r"[a-z][a-z\-]{4,}")
_STOP_NAMES = {
    "the", "this", "that", "these", "those", "there", "they", "their", "then", "when", "where", "what",
    "which", "who", "why", "how", "but", "and", "for", "from", "with", "while", "after", "before",
    "during", "also", "such", "some", "many", "most", "each", "other", "another", "figure", "source",
    "box", "activity", "discuss", "explain", "write", "describe", "look", "let", "india", "indian",
    "here", "enter", "entering", "top", "late", "early", "total", "table", "chapter",
    "indians", "world", "country", "people", "government", "class", "page", "see", "fig",
}
_STOP_WORDS = {
    "which", "their", "there", "these", "those", "about", "after", "again", "against", "because",
    "before", "being", "between", "could", "during", "every", "first", "other", "should", "since",
    "still", "through", "under", "until", "where", "while", "would", "country", "countries", "people",
    "years", "year", "century", "world", "government", "india", "indian", "number", "large", "small",
    "became", "become", "called", "known", "ideas", "different", "important", "example", "include",
    "including", "major", "several", "within", "without", "later", "early", "often", "around",
}


def _strings(node) -> list[str]:
    """Every piece of printed text under a unit's body: paragraphs, boxes, sources, captions."""
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            out += _strings(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in {"text", "title", "term", "definition", "boxes", "sources", "captions", "terms",
                       "body"}:
                out += _strings(value)
    return out


def _candidates(unit: dict) -> Counter:
    """term -> how strongly this unit's own text carries it."""
    blocks = [_clean(t) for t in _strings(unit.get("body") or [])]
    text = " ".join(b for b in blocks if b)
    found: Counter = Counter()
    # glossary terms and box titles are printed as the book's own key words
    for block in unit.get("body") or []:
        if isinstance(block, dict):
            for g in block.get("terms") or []:
                term = _clean((g or {}).get("term") or "")
                if term:
                    found[term] += 4
            for b in block.get("boxes") or []:
                title = _clean((b or {}).get("title") or "")
                if title:
                    found[title] += 3
    for m in _NAME.finditer(text):
        name = m.group().strip(" -'’")
        low = name.lower()
        if low in _STOP_NAMES or len(name) < 3:
            continue
        # a lone capitalised word right after a full stop is just a sentence start
        start = m.start()
        if " " not in name and (start == 0 or text[max(0, start - 2):start].strip() in {".", "?", "!", ""}):
            continue
        found[name] += 2
    for m in _ACRONYM.finditer(text):
        found[m.group().rstrip("s")] += 2
    for y in _YEAR.findall(text):
        found[y] += 1
    for w in _WORD.findall(text.lower()):
        if w not in _STOP_WORDS:
            found[w] += 1
    return found


def _derive_hints(units: list[dict]) -> dict[str, tuple[str, ...]]:
    """Section number -> the 4 to 8 most telling terms of that section's own text."""
    cands: dict[str, Counter] = {}
    for u in units:
        number = u.get("number")
        if not number or u.get("kind") in _NOT_TOPICS:
            continue
        cands[str(number)] = _candidates(u)
    # a box ("2.1" under section "2": a dam, a scheme) says what its section contains: its title
    # and its own words count towards the section it extends, though it is not a topic itself
    for u in units:
        if u.get("kind") != "box" or not u.get("number"):
            continue
        number = str(u["number"])
        owner = number.rsplit(".", 1)[0] if "." in number else ""
        if owner in cands:
            cands[owner].update(_candidates(u))
            title = _clean(u.get("title") or "")
            if title:
                cands[owner][title] += 6
    n = max(1, len(cands))
    df: Counter = Counter()
    for c in cands.values():
        df.update(set(c))
    ranked: dict[str, list[str]] = {}
    for number, c in cands.items():
        scored = []
        for term, tf in c.items():
            is_year = term.isdigit()
            is_word = term.islower()
            if is_word and (tf < 3 or len(term) < 6 or df[term] > 2):
                continue                    # a plain word must be frequent here and rare elsewhere
            idf = math.log(1 + n / df[term])
            weight = 0.6 if is_year else (0.7 if is_word else 1.0)
            scored.append((tf * idf * weight, term))
        scored.sort(key=lambda x: (-x[0], x[1]))
        picked: list[str] = []
        years = 0
        for _, term in scored:
            low = term.lower()
            if any(low in p.lower() or p.lower() in low for p in picked):
                continue
            if term.isdigit():
                if years >= 2:
                    continue
                years += 1
            if not _is_a_hint(term) and not term.islower() and not term.isdigit():
                continue
            picked.append(term[:40])
            if len(picked) >= KEYWORDS_PER_TOPIC:
                break
        ranked[number] = picked
    # a section too thin to describe itself borrows its sub-sections' best terms
    for number, terms in ranked.items():
        if len(terms) >= MIN_TERMS:
            continue
        for child, child_terms in ranked.items():
            if child.startswith(number + ".") and len(terms) < KEYWORDS_PER_TOPIC:
                for t in child_terms[:3]:
                    if t not in terms and len(terms) < KEYWORDS_PER_TOPIC:
                        terms.append(t)
    # a section with almost no text of its own (a heading and a line) borrows from its parent,
    # or failing that its first sub-section, so no topic is described by its title alone
    for number, terms in ranked.items():
        if terms:
            continue
        parent = number.rsplit(".", 1)[0] if "." in number else ""
        donors = [ranked.get(parent, [])] + [v for k, v in ranked.items() if k.startswith(number + ".")]
        order = list(ranked)
        after = [ranked[k] for k in order[order.index(number) + 1:order.index(number) + 3]]
        for donor in donors + after:
            if donor:
                terms.extend(donor[:3])
                break
    return {k: tuple(v) for k, v in ranked.items()}



def _merge_hints(derived: tuple[str, ...], card: tuple[str, ...]) -> tuple[str, ...]:
    """The text-derived terms first; the older card terms only fill a topic still short of
    MIN_TERMS, and never push it past KEYWORDS_PER_TOPIC."""
    out = list(derived)
    for t in card:
        if len(out) >= MIN_TERMS:
            break
        if t.lower() not in {o.lower() for o in out}:
            out.append(t)
    return tuple(out[:KEYWORDS_PER_TOPIC])


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
            derived = _derive_hints(units)
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
                    keywords=_merge_hints(
                        derived.get(number, ()), _keywords(ch["code"], number, boxes.get(number, []))),
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
