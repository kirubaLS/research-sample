"""The Class X Mathematics topic list, for the OCR mapper.

The school's own list (``reference/book_map_math/prompt_taxonomy.txt``), parsed the same way as
the Science list. Unlike Science and Social Science there is no audited textbook text in the
repository to take each topic's key terms and searchable text from, so they come from
``reference/book_map_math/topic_terms.json``: key terms and typical exam wording written for each
topic. That file is the thing to edit to change what a topic is matched on.

Read only; nothing imports it except the OCR mapper.
"""

from __future__ import annotations

import json
from functools import lru_cache

from app.curriculum.book_map import REFERENCE
from app.mapping import prompt_taxonomy as pt
from app.mapping import science_taxonomy as st

DIR = REFERENCE / "book_map_math"
SUBJECT = "X.MATH"


@lru_cache(maxsize=1)
def _built() -> tuple[pt.Taxonomy, dict[str, tuple[str, str]]]:
    lines = st.parse_list(DIR / "prompt_taxonomy.txt", {"MATHEMATICS": SUBJECT})
    terms = json.loads((DIR / "topic_terms.json").read_text(encoding="utf-8"))
    chapters: list[pt.Chapter] = []
    docs: dict[str, tuple[str, str]] = {}
    for _subject, cid, _tid, ctitle in (x for x in lines if x[1] == x[2]):
        topics = []
        for _s, _c, tid, title in (x for x in lines if x[1] == cid and x[2] != cid):
            number = tid[len(cid) + 1:]
            entry = terms.get(tid) or {}
            topics.append(pt.Topic(
                id=tid, number=number, title=title, depth=number.count(".") + 1, chapter_id=cid,
                keywords=tuple(entry.get("terms") or ()),
            ))
            parts = [title] * 3 + [entry.get("text", ""), " ".join(entry.get("terms") or ())]
            docs[tid] = (SUBJECT, " ".join(parts))
        chapters.append(pt.Chapter(cid, f"{SUBJECT}.{cid}", ctitle, SUBJECT, tuple(topics)))
    return pt.Taxonomy(chapters), docs


def build() -> pt.Taxonomy:
    return _built()[0]


def docs() -> dict[str, tuple[str, str]]:
    return _built()[1]
