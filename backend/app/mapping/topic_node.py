"""The topic a question tests, as a taxonomy node: the book's own heading for one
chapter+section.

Used by every step that decides or corrects a question's section -- the retrieval-only
map step, the classify step's topic judge, and a person settling a row in review -- so
the Topic column always shows the heading of whatever section was decided LAST. Before
this lived here, only the map step wrote a topic, and classify's better answer (and a
teacher's correction) changed the section on the question while the displayed topic kept
the retrieval-time guess forever.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuestionSkill, TaxonomyNode

#: 'X.MATH.STATS.S13_2' -> '13.2'. The tail of a subtopic node's code. The last part may
#: carry one lowercase letter: 'X.HIST.GLOBALWORLD.S2_4b' -> '2.4b', the second of two
#: headings the book prints as 2.4.
SECTION_CODE = re.compile(r"^S(\d+(?:_\d+)*[a-z]?)$")

#: Subjects loaded by scripts/import_book_map.py (see its own SUBJECT_FILES). For these,
#: BookChunk.reference IS the book's own heading text ("6 How can parties be reformed?"),
#: written straight from the audited book_map JSON's own "number"/"title" fields at import
#: time -- see import_book_map._text_chunks. The separate taxonomy_node(kind='subtopic')
#: rows these subjects carry were never touched by that importer (it deliberately leaves
#: subtopic nodes alone, see its own module docstring) and predate it under a different,
#: unrelated numbering, so a number-match between the two is a coincidence, not a join.
BOOK_MAP_SUBJECTS = {"X.HIST", "X.GEO", "X.POL", "X.ECO", "X.SCI"}

#: A book_map body chunk's reference is "{number} {title}", optionally with one of these
#: suffixes appended for a glossary/box/source/activity/caption chunk (see _text_chunks).
#: Strip it so the topic is the section's own heading, not one incidental passage's label.
BOOK_MAP_SUFFIX = re.compile(
    r"\s*\((?:activity|caption|box|source|glossary|map)[^)]*\)$"
)

#: QuestionSkill.weight of a secondary topic: a section a PART of the question is
#: answered in, beside the primary (weight 1.0). Reports read both; the Topic column
#: shows the heaviest.
SECONDARY_WEIGHT = 0.5

#: QuestionSkill rows a machine wrote. A person's ("import", "human") are never replaced
#: by a later automated pass.
MACHINE_TOPIC_SOURCES = ("retrieval", "model", "classify")


def section_number(code: str) -> str | None:
    """'X.MATH.STATS.S13_2' -> '13.2'. None when the code carries no section."""
    match = SECTION_CODE.match(code.rsplit(".", 1)[-1])
    return match.group(1).replace("_", ".") if match else None


def book_map_topic_label(chunks: list, chapter_id: str, section: str) -> str | None:
    """The book's own heading for this chapter+section, straight from a book_map chunk's
    reference, or None when no such chunk exists (an ordinary non-book_map subject, or a
    section the book map never recorded)."""
    candidates = [
        c.reference for c in chunks
        if c.node_id == chapter_id and c.section_number == section and c.reference
    ]
    if not candidates:
        return None
    # Prefer the shortest -- a plain body reference has no suffix at all, and is the
    # cleanest heading; a glossary/box/etc reference is only ever longer once stripped.
    stripped = sorted({BOOK_MAP_SUFFIX.sub("", ref).strip() for ref in candidates}, key=len)
    return stripped[0]


def section_headings(
    chunks: list, chapter: TaxonomyNode, nodes: dict[str, TaxonomyNode] | None = None,
) -> dict[str, str]:
    """Every section of ``chapter`` the book actually has, with its heading.

    The closed set a topic judge chooses from. Headings come from the chapter's own
    subtopic nodes when it has them (a book ingested with a taxonomy), and otherwise from
    the book_map chunk references (History/Geography/Politics/Economics/Science), which
    are the headings themselves. Every section any chunk carries is included even when
    neither source has a heading for it -- a section without a name is still a real
    place in the book, and the number alone is enough to file under.
    """
    out: dict[str, str] = {}
    from_book_map = False
    for c in chunks:
        if c.node_id != chapter.id or not c.section_number:
            continue
        out.setdefault(c.section_number, "")
        if getattr(c, "subject_code", None) in BOOK_MAP_SUBJECTS:
            from_book_map = True
    if not out:
        return out
    # A book_map subject's chunk references ARE the headings, and its subtopic nodes are
    # the stale, differently-numbered rows the importer left alone (see BOOK_MAP_SUBJECTS)
    # -- so for those the reference wins, and the node label is never consulted.
    if from_book_map:
        for number in out:
            out[number] = book_map_topic_label(chunks, chapter.id, number) or number
        return dict(sorted(out.items(), key=_section_order))
    if nodes:
        for node in nodes.values():
            if node.kind != "subtopic" or node.parent_id != chapter.id:
                continue
            number = section_number(node.code)
            if number in out and node.label:
                out[number] = node.label
    for number, heading in out.items():
        if not heading:
            out[number] = book_map_topic_label(chunks, chapter.id, number) or number
    return dict(sorted(out.items(), key=_section_order))


def major_view(chapter: TaxonomyNode) -> tuple[str, int] | None:
    """(chapter code, depth) when the topic judge sees only this chapter's major topics
    (topic_major_only_document on, the subject capped, and the book map describing the
    chapter); None otherwise."""
    from app.config import get_settings
    from app.curriculum.book_map import chapter_units
    from app.curriculum.depth import max_depth_for

    if not get_settings().topic_major_only_document:
        return None
    depth = max_depth_for(chapter.code)
    if depth is None or chapter_units(chapter.code) is None:
        return None
    return chapter.code, depth


def topic_headings(
    chunks: list, chapter: TaxonomyNode, nodes: dict[str, TaxonomyNode] | None = None,
) -> dict[str, str]:
    """The closed set a topic judge chooses from: the major topics when ``major_view``
    applies -- every one, including a heading with no text of its own, never a box, and
    "0 Introduction" -- otherwise ``section_headings`` as before."""
    view = major_view(chapter)
    if view is not None:
        from app.curriculum.book_map import major_headings

        headings = major_headings(*view)
        if headings:
            return headings
    return section_headings(chunks, chapter, nodes)


def _section_order(item: tuple[str, str]) -> tuple[tuple[int, str], ...]:
    from app.curriculum.book_map import section_key

    return section_key(item[0])


def _capped(chapter: TaxonomyNode, section: str, label: str) -> tuple[str, str]:
    """(section, label) cut to the subject's depth (topic_depth_cap) -- the last guard,
    so no caller can create or write a topic deeper than the cap. A cut section takes
    the book map's own heading for its new number."""
    from app.curriculum.depth import collapse_section, is_capped

    if not is_capped(chapter.code):
        return section, label
    cut = collapse_section(None, section, chapter_code=chapter.code)
    if cut == section or not cut:
        return section, label
    from app.curriculum.book_map import heading_label, unit_by_number

    unit = unit_by_number(chapter.code).get(cut)
    return cut, heading_label(cut, unit.title) if unit else cut


def _book_map_only(chapter: TaxonomyNode) -> bool:
    """book_map_only_subtopics, for a book-map subject: a node is matched by its printed
    number only and never relabelled -- an existing node under that code may carry a
    label from the ingest's reading-order numbering, and overwriting it made one node
    mean two different sections (see scripts/clean_book_map_subtopics.py, which puts the
    labels right once, reviewed)."""
    from app.config import get_settings
    from app.curriculum.depth import subject_of

    return bool(get_settings().book_map_only_subtopics) and (
        subject_of(chapter.code) in BOOK_MAP_SUBJECTS
    )


def topic_node(db: Session, chapter: TaxonomyNode, section: str, label: str) -> TaxonomyNode:
    """Get-or-create the subtopic node for a chapter+section, keyed and labelled from
    the same book data the chapter/section themselves came from -- so, unlike the stale
    pre-book_map subtopic rows, this key and this label can never drift apart."""
    section, label = _capped(chapter, section, label)
    code = f"{chapter.code}.S{section.replace('.', '_')}"
    node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
    if node is None:
        node = TaxonomyNode(
            kind="subtopic", code=code, label=label, parent_id=chapter.id,
            path=code, curriculum_version=chapter.curriculum_version,
        )
        db.add(node)
        db.flush()
    elif node.label != label and label != section and not _book_map_only(chapter):
        # Re-mapping after the book data changed (a title correction) must not leave the
        # old label sitting here forever -- the same reasoning books.py's own
        # subtopic-label refresh already relies on. A bare number is not a better label
        # than whatever the node already carries, so it never overwrites one.
        node.label = label
    return node


def set_question_topic(
    db: Session, question_id: str, chapter: TaxonomyNode, section: str, label: str,
    *, source: str, confidence: float | None = None,
    secondaries: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
) -> TaxonomyNode:
    """Make ``section`` the question's topic, replacing whatever a machine wrote before.

    QuestionSkill is the Q-matrix every report groups sub-topics by, and it is what the
    Topic column shows. Any earlier automated row is removed rather than kept beside the
    new one: the same question's section decided twice is one topic, not two.

    ``secondaries`` are the other (section, label) pairs a PART of a multi-part question
    is answered in -- a chronology, a match-the-columns, statements to judge. Those ARE
    a multi-skill question, and they are written beside the primary at
    ``SECONDARY_WEIGHT`` so a report on either section sees the marks.
    """
    node = topic_node(db, chapter, section, label)
    wanted: dict[str, float] = {node.id: 1.0}
    for other, other_label in secondaries:
        if other == section:
            continue
        # a secondary that collapses onto the primary (topic_depth_cap) is the primary
        wanted.setdefault(topic_node(db, chapter, other, other_label or other).id, SECONDARY_WEIGHT)
    rows = list(db.scalars(
        select(QuestionSkill).where(QuestionSkill.question_id == question_id)
    ))
    if source != "human" and any(r.source not in MACHINE_TOPIC_SOURCES for r in rows):
        # A person already chose this question's topic; a later machine pass does not
        # overrule them.
        return node
    kept: set[str] = set()
    for row in rows:
        if row.node_id in wanted and row.node_id not in kept:
            row.source, row.confidence, row.weight = source, confidence, wanted[row.node_id]
            kept.add(row.node_id)
        elif row.source in MACHINE_TOPIC_SOURCES or source == "human":
            db.delete(row)
    for node_id, weight in wanted.items():
        if node_id not in kept:
            db.add(QuestionSkill(
                question_id=question_id, node_id=node_id, source=source,
                confidence=confidence, weight=weight,
            ))
    db.flush()
    return node
