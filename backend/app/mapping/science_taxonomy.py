"""The Class X Science topic list, for the OCR mapper.

The list, its IDs and every topic's key terms are read from the prompt itself,
``reference/book_map_science/ocr_prompt.md`` (its "TAXONOMY" section): one file is the source of
truth, so the prompt the model reads and the list the answers are checked against cannot drift
apart. Edit the prompt file to change either.

The IDs (``C2.10``, ``P3.6.1``) are the list's numbering, not the textbook's printed numbers. Each
topic is matched by title to the audited textbook unit it comes from, so the candidate-section
search reads the section's own text as well as the topic's key terms.

The IDs repeat Social Science's (``P4.1`` is Physics here and Political Science there), so this
is a taxonomy of its own, never merged with that one.

Read only; nothing imports it except the OCR mapper.
"""

from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache

from app.curriculum.book_map import REFERENCE, UNIT_FILES
from app.mapping import prompt_taxonomy as pt

PROMPT_FILE = REFERENCE / "book_map_science" / "ocr_prompt.md"
#: the subject headings in the taxonomy, and the code each gives its chapters
SUBJECTS = {"CHEMISTRY": "X.CHEM", "BIOLOGY": "X.BIO", "PHYSICS": "X.PHY", "ENVIRONMENT": "X.ENV"}

# ``ID | Title  (note) [key term; key term]``; a key term may hold brackets ("[H]"), so the
# bracket group runs to the LAST "]" on the line
_LINE = re.compile(
    r"^(?P<indent> *)(?P<id>[A-Z]+\d+(?:\.\d+)*)\s*\|\s*(?P<title>.+?)"
    r"(?:\s*\((?:inside|PARENT of)[^)]*\))?(?:\s*\[(?P<terms>.*)\])?\s*$")


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def prompt_text() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _taxonomy_lines(text: str) -> list[str]:
    """The lines inside the code fence that follows the prompt's "TAXONOMY" heading."""
    lines = text.splitlines()
    head = next(i for i, ln in enumerate(lines) if ln.startswith("## ") and ln.rstrip().endswith("TAXONOMY"))
    start = next(i for i in range(head, len(lines)) if lines[i].startswith("```")) + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("```"))
    return lines[start:end]


def parse_prompt(text: str) -> list[tuple[str, str, str, str, tuple[str, ...]]]:
    """``(subject, chapter id, topic id, title, key terms)`` for every line of the taxonomy; a
    chapter's own line has topic id == chapter id."""
    out = []
    subject = ""
    for raw in _taxonomy_lines(text):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.strip() in SUBJECTS:
            subject = SUBJECTS[line.strip()]
            continue
        m = _LINE.match(line)
        if not m:
            raise ValueError(f"cannot read the Science taxonomy line: {raw!r}")
        tid = m.group("id")
        terms = tuple(t.strip() for t in (m.group("terms") or "").split(";") if t.strip())
        out.append((subject, tid.split(".")[0], tid, m.group("title").strip(), terms))
    return out


def _parse() -> list[tuple[str, str, str, str, tuple[str, ...]]]:
    return parse_prompt(prompt_text())


def _units_by_chapter() -> list[dict]:
    return json.loads((REFERENCE / UNIT_FILES["X.SCI"]).read_text(encoding="utf-8"))


def _match_unit(title: str, units: list[dict], used: set[int]) -> dict | None:
    """The textbook unit with this title (case, dashes and punctuation ignored)."""
    want = _key(title)
    for i, u in enumerate(units):
        if i not in used and u.get("number") and _key(u.get("title", "")) == want:
            used.add(i)
            return u
    scored = [
        (difflib.SequenceMatcher(None, want, _key(u.get("title", ""))).ratio(), i)
        for i, u in enumerate(units) if i not in used and u.get("number")
    ]
    best = max(scored, default=(0.0, -1))
    if best[0] >= 0.82:
        used.add(best[1])
        return units[best[1]]
    return None


@lru_cache(maxsize=1)
def _built() -> tuple[pt.Taxonomy, dict[str, tuple[str, str]]]:
    """The taxonomy, and ``topic id -> (subject, section text)`` for retrieval."""
    lines = _parse()
    chapters_src = _units_by_chapter()
    chapters: list[pt.Chapter] = []
    docs: dict[str, tuple[str, str]] = {}
    for index, (subject, cid, _tid0, ctitle, _t) in enumerate(x for x in lines if x[1] == x[2]):
        src = chapters_src[index]
        units = src.get("units", [])
        used: set[int] = set()
        topics = []
        for _, _, tid, title, terms in (x for x in lines if x[1] == cid and x[2] != cid):
            number = tid[len(cid) + 1:]
            unit = _match_unit(title, units, used) or {}
            topics.append(pt.Topic(
                id=tid, number=number, title=title, depth=number.count(".") + 1, chapter_id=cid,
                keywords=terms,
            ))
            parts = ([title] * 3 + ["; ".join(terms)] + pt._strings(unit.get("body") or [])
                     + pt._strings(unit.get("activities") or []))
            docs[tid] = (subject, " ".join(pt._clean(x) for x in parts if x))
        chapters.append(pt.Chapter(cid, src["code"], ctitle, subject, tuple(topics)))
    return pt.Taxonomy(chapters), docs


def build() -> pt.Taxonomy:
    return _built()[0]


def docs() -> dict[str, tuple[str, str]]:
    return _built()[1]
