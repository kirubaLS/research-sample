"""Which chapters one question may be placed in -- one rule, used by map and by place.

The paper says what it covers in up to three places, and a teacher can say it too. In
order of precedence, highest first:

1. **teacher** -- ``assessment.syllabus_scope``, chapter codes a person set.
2. **section_title** -- the chapters (or the whole subject) the question's own section
   header names: "SECTION B (Geography : Minerals and Energy Resources)".
3. **syllabus** -- the chapters the paper's printed syllabus lines name: "History Ch 1-2,
   Geography Ch 1, 3".
4. **inferred** -- nothing declared: the place step's own scope inference
   (``app.classify.scope``) runs, as before. This module returns no chapter set for it.
5. **group** -- the whole subject group.

A lower source only ever narrows a higher one. When the two do not overlap at all, the
higher one stands: a teacher's scope is never overruled by a header, and a header is
never overruled by a cover line.

A bare section letter means nothing here. "SECTION A" of a board paper is a set of MCQs
drawn from all four books; only a title that resolves to a subject or a chapter narrows
the scope. (The old fixed convention A/B/C/D -> History/Geography/Political
Science/Economics stays in ``app.api.marks._SST_SECTION_SUBJECT`` for the flag-off path.)

Everything is in chapter CODES. Map compares chunk chapter ids and place compares chapter
labels; each converts at its own edge.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.curriculum import CURRICULA
from app.curriculum.resolve import Resolution, resolve_text

TEACHER = "teacher"
SECTION_TITLE = "section_title"
SYLLABUS = "syllabus"
GROUP = "group"


@dataclass(frozen=True)
class ScopeDecision:
    #: chapter codes the question may be placed in; None means no chapter restriction
    #: beyond the subject group (the place step may still infer one)
    chapter_codes: frozenset[str] | None
    source: str
    #: the printed text the decision came from, for the placement's explanation
    detail: str = ""
    #: set when a printed title was overruled -- a section title naming chapters outside
    #: the teacher's scope. Reported in the job result, never silent.
    warning: str = ""

    @property
    def single_chapter(self) -> str | None:
        if self.chapter_codes is not None and len(self.chapter_codes) == 1:
            return next(iter(self.chapter_codes))
        return None


def _codes_of(resolution: Resolution) -> frozenset[str]:
    """A resolution's chapters, or every chapter of the subjects it names when it names
    a subject but no chapter ('SECTION A -- History')."""
    if resolution.chapters:
        return frozenset(resolution.chapters)
    codes: set[str] = set()
    for subject in resolution.subjects:
        curriculum = CURRICULA.get(subject)
        if curriculum is not None:
            codes.update(c.code for c in curriculum.chapters)
    return frozenset(codes)


class PaperScope:
    """The scope rule for one paper, built once and asked per question."""

    def __init__(
        self,
        subject_codes: list[str],
        *,
        teacher_scope: list[str] | None = None,
        declared: dict | None = None,
        aliases: dict[str, list[str]] | None = None,
    ) -> None:
        self.subject_codes = [c for c in subject_codes if c in CURRICULA]
        group_chapters = {
            ch.code for code in self.subject_codes for ch in CURRICULA[code].chapters
        }
        # a one-book paper: a bare "Ch 3" can only mean that book's chapter 3
        default_subject = self.subject_codes[0] if len(self.subject_codes) == 1 else None

        teacher = frozenset(c for c in (teacher_scope or []) if c in group_chapters)
        self.teacher: frozenset[str] | None = teacher or None

        declared = declared or {}
        syllabus: set[str] = set()
        lines = [line for line in (declared.get("syllabus_lines") or []) if line]
        for line in lines:
            syllabus |= _codes_of(resolve_text(
                line, self.subject_codes, aliases, default_subject=default_subject,
            ))
        self.syllabus: frozenset[str] | None = frozenset(syllabus & group_chapters) or None
        self.syllabus_text = " | ".join(lines)

        self.titles: dict[str, tuple[frozenset[str], str]] = {}
        for letter, title in (declared.get("section_titles") or {}).items():
            if not (title or "").strip():
                continue
            codes = _codes_of(resolve_text(
                title, self.subject_codes, aliases, default_subject=default_subject,
            )) & group_chapters
            if codes:
                self.titles[letter.strip().upper()] = (frozenset(codes), title)

    def paper_level(self) -> ScopeDecision:
        """The scope every question shares before its own section title is read."""
        if self.teacher is not None:
            return ScopeDecision(self.teacher, TEACHER)
        if self.syllabus is not None:
            return ScopeDecision(self.syllabus, SYLLABUS, self.syllabus_text)
        return ScopeDecision(None, GROUP)

    def for_section(self, section: str | None) -> ScopeDecision:
        """The scope of a question printed under ``section`` (a letter, or None)."""
        base = self.paper_level()
        titled = self.titles.get((section or "").strip().upper())
        if titled is None:
            return base
        codes, title = titled
        if base.chapter_codes is None:
            return ScopeDecision(codes, SECTION_TITLE, title)
        narrowed = codes & base.chapter_codes
        if narrowed:
            return ScopeDecision(frozenset(narrowed), SECTION_TITLE, title)
        if base.source == SYLLABUS:
            # the header outranks the cover: a section titled with a chapter the cover
            # line did not list is still that chapter
            return ScopeDecision(codes, SECTION_TITLE, title)
        # The teacher's scope stands and the title is ignored for this question -- but a
        # header that contradicts the teacher is a fact somebody should see.
        return ScopeDecision(
            base.chapter_codes, base.source, base.detail,
            warning=(
                f"section {(section or '').strip().upper()} is titled {title!r}, which names "
                f"{', '.join(sorted(codes))} -- outside the teacher's scope "
                f"({', '.join(sorted(base.chapter_codes))}); the teacher's scope was kept "
                "and the title ignored"
            ),
        )

    def warnings(self) -> list[str]:
        """Every titled section whose title was overruled, one line each."""
        out = []
        for letter in sorted(self.titles):
            warning = self.for_section(letter).warning
            if warning:
                out.append(warning)
        return out


def paper_scope_for(db, assessment, subject_codes: list[str]) -> PaperScope:
    """Build the rule for ``assessment`` from what it stores and the alias table."""
    from app.curriculum.resolve import load_chapter_aliases

    return PaperScope(
        subject_codes,
        teacher_scope=assessment.syllabus_scope,
        declared=assessment.declared,
        aliases=load_chapter_aliases(db, subject_codes),
    )
