"""How deep a subject's topics go, and the one helper that cuts a section to that depth.

A major topic is at most ``topic_max_depth`` levels deep -- "4" or "4.1", never "4.1.1"
-- for every subject listed in ``topic_max_depth_by_subject`` while ``topic_depth_cap`` is
on. A subject not listed (Maths, Science, the languages) keeps today's behaviour.

``collapse_section`` is applied everywhere a section is decided or stored, so no code path
can write a three-level section for a capped subject.
"""

from __future__ import annotations

from app.curriculum import CURRICULA

NONE_WORDS = frozenset({"none", ""})


def subject_of(code: str) -> str | None:
    """'X.GEO.MINERALSENERGY' or 'X.GEO' -> 'X.GEO'; None when no subject matches."""
    if code in CURRICULA:
        return code
    for subject in sorted(CURRICULA, key=len, reverse=True):
        if code.startswith(subject + "."):
            return subject
    return None


def max_depth_for(subject_code: str | None) -> int | None:
    """The cap for ``subject_code`` (a subject or chapter code), or None when uncapped."""
    from app.config import get_settings

    settings = get_settings()
    if not settings.topic_depth_cap or not subject_code:
        return None
    subject = subject_of(subject_code) or subject_code
    listed = settings.topic_max_depth_by_subject or {}
    if subject not in listed:
        return None
    return int(listed[subject] or settings.topic_max_depth)


def is_capped(subject_code: str | None) -> bool:
    return max_depth_for(subject_code) is not None


def collapse_section(
    subject_code: str | None, section: str | None, *, chapter_code: str | None = None,
) -> str | None:
    """``section`` cut to the subject's depth: "4.1.1" -> "4.1".

    ``None`` and "none" come back unchanged, and so does every section of an uncapped
    subject. When ``chapter_code`` names a book-map chapter, a box is also lifted to its
    parent ("2.1 Rat-Hole Mining" is a box in Minerals and Energy Resources, so it
    collapses to "2"): a box is never a topic.
    """
    if section is None or section.strip().lower() in NONE_WORDS:
        return section
    depth = max_depth_for(chapter_code or subject_code)
    if depth is None:
        return section
    if chapter_code:
        from app.curriculum.book_map import major_of

        major = major_of(chapter_code, section, depth)
        if major is not None:
            return major
    parts = section.split(".")
    return ".".join(parts[:depth])


def collapse_all(
    subject_code: str | None, sections, *, chapter_code: str | None = None,
    exclude: str | None = None,
) -> list[str]:
    """Collapse each of ``sections``, drop any equal to ``exclude`` (the primary), and
    remove duplicates, keeping the first occurrence's order."""
    out: list[str] = []
    for s in sections:
        c = collapse_section(subject_code, s, chapter_code=chapter_code)
        if c is None or c.lower() in NONE_WORDS or c == exclude or c in out:
            continue
        out.append(c)
    return out
