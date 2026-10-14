"""The Class X English topic list, for the OCR mapper.

The list, its IDs and every topic's key terms are read from the prompt itself,
``reference/book_map_english/ocr_prompt.md`` (the "TAXONOMY" section): one file is the source of
truth, so the prompt the model reads and the list the answers are checked against cannot drift
apart. Edit the prompt file to change either.

A chapter the prompt allows as an answer also exists as a topic with the same ID, so
``taxonomy.topic("G1")`` finds it: G1 to G4 have no sub-topics ("topic_id = G1"), and the grammar
rule for a blank that covers a statement and a question says to use G5 as the parent.

There is no textbook text in the repository for English, so the candidate-section search (used
only by the second reader) matches a question against each topic's title and key terms.

Read only; nothing imports it except the OCR mapper.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.curriculum.book_map import REFERENCE
from app.mapping import prompt_taxonomy as pt

PROMPT_FILE = REFERENCE / "book_map_english" / "ocr_prompt.md"
SUBJECT = "X.ENG"
#: chapters that may be answered as a topic although they have sub-topics (mapping rule 9)
PARENT_ANSWERS = {"G5"}

# ``ID | Title [key term; key term]``: the bracket group runs from the first "[" to the last "]"
_LINE = re.compile(
    r"^(?P<indent> *)(?P<id>[A-Z]+\d+(?:\.\d+)*)\s*\|\s*(?P<title>.+?)(?:\s*\[(?P<terms>.*)\])?\s*$")


def prompt_text() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _taxonomy_lines(text: str) -> list[str]:
    """The lines of the prompt's TAXONOMY section."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "TAXONOMY") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("## "))
    return lines[start:end]


def parse_prompt(text: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """``(id, title, key terms)`` for every line of the taxonomy, in order."""
    out = []
    for raw in _taxonomy_lines(text):
        if not raw.strip():
            continue
        m = _LINE.match(raw.rstrip())
        if not m:
            raise ValueError(f"cannot read the English taxonomy line: {raw!r}")
        terms = tuple(t.strip() for t in (m.group("terms") or "").split(";") if t.strip())
        out.append((m.group("id"), m.group("title").strip(), terms))
    return out


@lru_cache(maxsize=1)
def _built() -> tuple[pt.Taxonomy, dict[str, tuple[str, str]]]:
    rows = parse_prompt(prompt_text())
    chapters: list[pt.Chapter] = []
    docs: dict[str, tuple[str, str]] = {}

    def doc(tid: str, title: str, terms: tuple[str, ...]) -> None:
        docs[tid] = (SUBJECT, " ".join([title] * 3 + ["; ".join(terms)]))

    index = [i for i, (tid, _t, _k) in enumerate(rows) if "." not in tid]
    for n, start in enumerate(index):
        cid, ctitle, cterms = rows[start]
        end = index[n + 1] if n + 1 < len(index) else len(rows)
        topics: list[pt.Topic] = []
        for tid, title, terms in rows[start + 1:end]:
            assert tid.startswith(cid + "."), f"{tid} is outside its chapter {cid}"
            number = tid[len(cid) + 1:]
            topics.append(pt.Topic(id=tid, number=number, title=title, depth=number.count(".") + 1,
                                   chapter_id=cid, keywords=terms))
            doc(tid, title, terms)
        if cterms and (not topics or cid in PARENT_ANSWERS):     # the chapter itself is an answer
            topics.insert(0, pt.Topic(id=cid, number="", title=ctitle, depth=0, chapter_id=cid,
                                      keywords=cterms))
            doc(cid, ctitle, cterms)
        chapters.append(pt.Chapter(cid, f"{SUBJECT}.{cid}", ctitle, SUBJECT, tuple(topics)))
    return pt.Taxonomy(chapters), docs


def build() -> pt.Taxonomy:
    return _built()[0]


def docs() -> dict[str, tuple[str, str]]:
    return _built()[1]
