"""The teacher dashboard's map step, decided by the OCR mapper's pipeline.

These helpers serve ``app.api.marks._map_paper_ocr_mapper``, the teacher reader's map step: the
OCR mapper's pipeline is the only thing that decides a question's chapter and topic (the older
retrieval plus chapter and topic judges were removed). The staged questions go through the SAME
code the admin OCR mapper uses (``app.api.ocr_lab._map`` -> ``app.mapping.ocr_mapper_v2``): the
book's own text finds candidate sections, a cheap model chooses with those passages in view using
the subject's prompt, and a strong model rereads the doubtful answers. Then each answer is
written where the map step always wrote its own: a ``Question`` with its chapter, board unit,
section and concept family, a
``QuestionPlacement`` carrying the reasoning, and the topic in the Q-matrix. Reading the paper,
saving it, the original file in S3, duplicate checks and answer sheets are not touched.

The mapper's IDs are its own lists', so they are translated to the database's:

* Social Science and Science: the list's chapter codes ARE the curriculum's. A Social topic's
  number is the book's printed section number; a Science topic is filed under the section number
  of the textbook unit it was matched to by title (the list's own numbers differ).
* Mathematics: the 14 list chapters are the curriculum's 14, in order. A topic is filed under the
  list's own number, with the list's title as its heading.
* English: FF1..FF9 and FW1..FW9 are the curriculum's chapters of First Flight and Footprints
  without Feet, in order. The curriculum has no chapter for the First Flight poems or for
  Reading, Grammar and Writing, so those list chapters are created on first use
  (``ensure_english_chapters``): the poems FP1..FP10 as chapters of First Flight, and R1..W2 as
  chapters of Words and Expressions (the workbook that drills them), each counting towards its
  book's board unit, so every part of an English paper can be filed.

No tier is decided here (the OCR mapper does not decide one); an abstaining tier row is written
so the paper still reads as classified.
"""

from __future__ import annotations

import re

from app.mapping import ocr_mapper_v2 as v2

#: certainty written on the placement for each of the model's labels
CONFIDENCE = {"high": 0.9, "medium": 0.6, "low": 0.3}


def profile_for_assessment(subject_code: str | None) -> v2.Profile | None:
    """The OCR mapper profile for a paper's subject, or None when the mapper has no list for it
    (Hindi, Tamil, anything else): those keep the older path."""
    code = (subject_code or "").upper()
    if code.startswith(("X.HIN", "X.TAM")):
        return None
    if code.startswith(("X.SCI", "X.MATH", "X.ENG")):
        return v2.profile_for(code)
    if code.startswith(("X.SST", "X.HIST", "X.GEO", "X.POL", "X.ECO")):
        return v2.SOCIAL
    return None


def chapter_code(profile: v2.Profile, taxonomy_chapter, curricula: dict) -> str | None:
    """The database chapter code for a list chapter, or None when the curriculum has none."""
    if profile.name in ("social", "science"):
        return taxonomy_chapter.code
    if profile.name == "maths":
        chapters = curricula["X.MATH"].chapters
        n = int(taxonomy_chapter.id[1:])
        return chapters[n - 1].code if 1 <= n <= len(chapters) else None
    if profile.name == "english":
        for prefix, book in (("FF", "X.ENG.FF"), ("FW", "X.ENG.FWF")):
            if taxonomy_chapter.id.startswith(prefix) and taxonomy_chapter.id[len(prefix):].isdigit():
                chapters = curricula[book].chapters
                n = int(taxonomy_chapter.id[len(prefix):])
                return chapters[n - 1].code if 1 <= n <= len(chapters) else None
        if taxonomy_chapter.id.startswith("FP"):
            return f"X.ENG.FF.{taxonomy_chapter.id}"
        return f"X.ENG.WB.{taxonomy_chapter.id}"
    return None


def ensure_english_chapters(db, version: str) -> int:
    """Create the English chapters the curriculum does not list (the First Flight poems, and
    Reading, Grammar and Writing), under First Flight and Words and Expressions, each counting
    towards that book's board unit. Idempotent; returns how many chapters it created. Needs the
    English books to be set up already (their subject and unit nodes)."""
    from sqlalchemy import select

    from app.mapping import english_taxonomy as et
    from app.models import ChapterBoardUnit, TaxonomyNode

    def node(code):
        return db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))

    made = 0
    for chapter in et.build().chapters:
        if chapter.id.startswith(("FF", "FW")):
            continue
        book = "X.ENG.FF" if chapter.id.startswith("FP") else "X.ENG.WB"
        subject, unit = node(book), node(f"{book}.U.WHOLE")
        if subject is None or unit is None:
            continue
        code = f"{book}.{chapter.id}"
        row = node(code)
        if row is None:
            row = TaxonomyNode(kind="chapter", code=code, label=chapter.title, parent_id=subject.id,
                               path=code, curriculum_version=version)
            db.add(row)
            db.flush()
            made += 1
        if db.scalar(select(ChapterBoardUnit).where(
            ChapterBoardUnit.chapter_id == row.id, ChapterBoardUnit.curriculum_version == version,
        )) is None:
            db.add(ChapterBoardUnit(curriculum_version=version, chapter_id=row.id, board_unit_id=unit.id))
    db.flush()
    return made


def section_of(profile: v2.Profile, topic_id: str, number: str) -> str | None:
    """The section number a topic is filed under in the database.

    Social Science: the book's printed section number (the list's own). Science: the section
    number of the textbook unit the topic was matched to by title, else the list's number
    qualified by its chapter. Mathematics and English have no audited section numbers in the
    repository, so a topic is filed under the list's number qualified by its chapter number
    ("13.1" for M13.1, "2.3" for FF2.3) with the list's title as its heading."""
    if profile.name == "science":
        from app.mapping import science_taxonomy

        units = science_taxonomy.unit_numbers()
        parts = topic_id
        while parts:
            if parts in units:
                return units[parts]
            if "." not in parts:
                break
            parts = parts.rsplit(".", 1)[0]
    if not number:
        return None
    if profile.name == "social":
        return number
    digits = "".join(ch for ch in topic_id.split(".")[0] if ch.isdigit())
    return f"{digits}.{number}" if digits else number


def review_reason(result: dict) -> str:
    """One of the stored review reasons (app.classify.review_rule.REASONS)."""
    book = result.get("book_check") or {}
    if book.get("second_reader_changed"):
        return "topic_differs"
    if result.get("confidence") == "low":
        return "low_confidence"
    return "topic_unverified"


_ID = re.compile(r"\b[A-Z]{1,2}\d+(?:\.\d+)*\b")


def topics_named_in(result: dict, taxonomy) -> list[dict]:
    """The other topics the model named by ID in its own reason ("tests four events: H5.2.1,
    H5.2, H5.6.2, H5.9") that exist in the list, as secondary topics: the question is about all of
    them, and the model said so in words without always listing them. Only IDs of the closed list
    count; the primary and anything already listed are left out."""
    topic = (result.get("topic") or {}).get("id")
    have = {topic} | {s["id"] for s in result.get("secondary") or []}
    out = []
    for tid in dict.fromkeys(_ID.findall(result.get("reason_full") or "")):
        t = taxonomy.topic(tid)
        chapter = taxonomy.chapter(t.chapter_id) if t else None
        if t is None or chapter is None or tid in have:
            continue
        out.append({"id": t.id, "title": t.title, "chapter": chapter.title, "number": t.number})
    return out
