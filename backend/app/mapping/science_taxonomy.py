"""The Class X Science topic list, for the OCR mapper.

Same idea as ``prompt_taxonomy`` (a closed list of chapters and topics the model chooses from,
each topic carrying key terms taken from its own section's text) but for Science, whose list is
the school's own: ``reference/book_map_science/prompt_taxonomy.txt``. Its IDs (``C2.10``,
``P3.6.1``) are the list's numbering, not the textbook's printed numbers; each topic is matched
by title to the audited textbook unit it comes from so its hints and its retrieval text are the
section's own.

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

LIST_FILE = REFERENCE / "book_map_science" / "prompt_taxonomy.txt"
#: the subject headings in the list file, and the chapter-id prefix each uses
SUBJECTS = {"CHEMISTRY": "X.CHEM", "BIOLOGY": "X.BIO", "PHYSICS": "X.PHY", "ENVIRONMENT": "X.ENV"}

_LINE = re.compile(r"^(?P<indent> *)(?P<id>[A-Z]+\d+(?:\.\d+)*)\s*\|\s*(?P<title>.+?)\s*$")


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def parse_list(path, subjects: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """``(subject, chapter id, topic id, title)`` for every line of a topic-list file; a chapter's
    own line has topic id == chapter id. ``subjects`` maps the file's "# HEADING" lines to codes."""
    out: list[tuple[str, str, str, str]] = []
    subject = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            heading = line[2:].strip()
            if heading in subjects:
                subject = subjects[heading]
            continue
        m = _LINE.match(line)
        if not m:
            raise ValueError(f"cannot read the topic list line: {raw!r}")
        tid = m.group("id")
        out.append((subject, tid.split(".")[0], tid, m.group("title")))
    return out


def _parse() -> list[tuple[str, str, str, str]]:
    return parse_list(LIST_FILE, SUBJECTS)


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
    chapter_ids = [cid for _, cid, tid, _ in lines if cid == tid]
    chapters: list[pt.Chapter] = []
    docs: dict[str, tuple[str, str]] = {}
    for index, (subject, cid, _tid0, ctitle) in enumerate(x for x in lines if x[1] == x[2]):
        src = chapters_src[index]
        units = src.get("units", [])
        used: set[int] = set()
        members = [x for x in lines if x[1] == cid and x[2] != cid]
        # a pseudo-unit per listed topic: the list's own number, the matched textbook unit's text
        pseudo = []
        for _, _, tid, title in members:
            number = tid[len(cid) + 1:]
            unit = _match_unit(title, units, used)
            pseudo.append({
                "number": number, "kind": "section", "title": title,
                "body": (unit or {}).get("body") or [], "boxes": (unit or {}).get("boxes") or [],
                "activities": (unit or {}).get("activities") or [],
                "_unit": unit,
            })
        # science is concept-heavy ("concave", "focal length"), not names and dates, so plain words count more
        hints = pt._derive_hints(pseudo, word_min_tf=2, word_max_df=4)
        topics = []
        for p, (_, _, tid, title) in zip(pseudo, members, strict=True):
            number = p["number"]
            topics.append(pt.Topic(
                id=tid, number=number, title=title, depth=number.count(".") + 1, chapter_id=cid,
                keywords=hints.get(number, ()),
            ))
            parts = [title] * 3 + pt._strings(p["body"]) + pt._strings(p["activities"])
            docs[tid] = (subject, " ".join(pt._clean(x) for x in parts if x))
        chapters.append(pt.Chapter(cid, src["code"], ctitle, subject, tuple(topics)))
    assert len(chapters) == len(chapter_ids)
    return pt.Taxonomy(chapters), docs


def build() -> pt.Taxonomy:
    return _built()[0]


def docs() -> dict[str, tuple[str, str]]:
    return _built()[1]
