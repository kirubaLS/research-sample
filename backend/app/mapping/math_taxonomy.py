"""The Class X Mathematics topic list, for the OCR mapper.

The list, its IDs and every topic's key terms are read from the prompt itself,
``reference/book_map_math/ocr_prompt.md`` (the "TAXONOMY" section): one file is the source of
truth, so the prompt the model reads and the list the answers are checked against cannot drift
apart. Edit the prompt file to change either.

There is no audited textbook text in the repository for Mathematics (Science and Social Science
have one), so the candidate-section search matches a question against each topic's key terms plus
the extra wording in ``topic_terms.json``.

Read only; nothing imports it except the OCR mapper.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from app.curriculum.book_map import REFERENCE
from app.mapping import prompt_taxonomy as pt

DIR = REFERENCE / "book_map_math"
PROMPT_FILE = DIR / "ocr_prompt.md"
SUBJECT = "X.MATH"

_LINE = re.compile(
    r"^(?P<indent> *)(?P<id>M\d+(?:\.\d+)*)\s*\|\s*(?P<title>.+?)(?:\s*\[(?P<terms>.*)\])?\s*$")


def prompt_text() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _taxonomy_lines(text: str) -> list[str]:
    """The lines of the prompt's TAXONOMY section."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "TAXONOMY") + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("## "))
    return lines[start:end]


def _chapter(c: tuple[str, str, list[pt.Topic]]) -> pt.Chapter:
    return pt.Chapter(c[0], f"{SUBJECT}.{c[0]}", c[1], SUBJECT, tuple(c[2]))


@lru_cache(maxsize=1)
def _built() -> tuple[pt.Taxonomy, dict[str, tuple[str, str]]]:
    extra = json.loads((DIR / "topic_terms.json").read_text(encoding="utf-8"))
    chapters: list[pt.Chapter] = []
    docs: dict[str, tuple[str, str]] = {}
    current: tuple[str, str, list[pt.Topic]] | None = None
    for raw in _taxonomy_lines(prompt_text()):
        if not raw.strip():
            continue
        m = _LINE.match(raw.rstrip())
        if not m:
            raise ValueError(f"cannot read the Mathematics taxonomy line: {raw!r}")
        tid, title = m.group("id"), m.group("title").strip()
        terms = tuple(t.strip() for t in (m.group("terms") or "").split(";") if t.strip())
        if "." not in tid:                        # a chapter line
            if current:
                chapters.append(_chapter(current))
            current = (tid, title, [])
            continue
        assert current is not None and tid.split(".")[0] == current[0], f"{tid} is outside its chapter"
        number = tid[len(current[0]) + 1:]
        current[2].append(pt.Topic(
            id=tid, number=number, title=title, depth=number.count(".") + 1, chapter_id=current[0],
            keywords=terms,
        ))
        parts = [title] * 3 + ["; ".join(terms), (extra.get(tid) or {}).get("text", "")]
        docs[tid] = (SUBJECT, " ".join(parts))
    if current:
        chapters.append(_chapter(current))
    return pt.Taxonomy(chapters), docs


def build() -> pt.Taxonomy:
    return _built()[0]


def docs() -> dict[str, tuple[str, str]]:
    return _built()[1]
