"""Board units and their weightage: the layer that does not come from the book.

CBSE publishes weightage per *unit*, and a unit may span several chapters (Algebra covers
four) or exist where no chapter does (English's Reading section). The book never states
this -- it is a syllabus fact -- so it is defined here with a citation and applied before
any book is loaded.

One source, used by both `scripts.seed` and the operator console, so a deployment that
cannot run a shell is not a second-class one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SYLLABUS_URL = "https://cbseacademic.nic.in/"


@dataclass(frozen=True)
class BoardUnit:
    code: str
    label: str
    weight_pct: float


@dataclass(frozen=True)
class Chapter:
    code: str
    label: str
    board_unit: str


@dataclass(frozen=True)
class Curriculum:
    subject_code: str
    subject_label: str
    grade: int
    units: list[BoardUnit]
    chapters: list[Chapter]
    #: stable trend axes, curated rather than extracted -- renaming one after a class has
    #: been tested breaks every comparison that references it
    concept_families: list[tuple[str, str, str]] = field(default_factory=list)
    source_doc_url: str = SYLLABUS_URL


X_MATH = Curriculum(
    subject_code="X.MATH",
    subject_label="Class X Mathematics",
    grade=10,
    units=[
        BoardUnit("X.MATH.U.NUMBER", "Number Systems", 6.0),
        BoardUnit("X.MATH.U.ALGEBRA", "Algebra", 20.0),
        BoardUnit("X.MATH.U.COORD", "Coordinate Geometry", 6.0),
        BoardUnit("X.MATH.U.GEOMETRY", "Geometry", 15.0),
        BoardUnit("X.MATH.U.TRIG", "Trigonometry", 12.0),
        BoardUnit("X.MATH.U.MENSURATION", "Mensuration", 10.0),
        BoardUnit("X.MATH.U.STATSPROB", "Statistics & Probability", 11.0),
    ],
    chapters=[
        Chapter("X.MATH.REAL", "Real Numbers", "X.MATH.U.NUMBER"),
        Chapter("X.MATH.POLY", "Polynomials", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.LINEQ", "Pair of Linear Equations", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.QUAD", "Quadratic Equations", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.AP", "Arithmetic Progressions", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.TRIANGLE", "Triangles", "X.MATH.U.GEOMETRY"),
        Chapter("X.MATH.COORD", "Coordinate Geometry", "X.MATH.U.COORD"),
        Chapter("X.MATH.TRIG", "Introduction to Trigonometry", "X.MATH.U.TRIG"),
        Chapter("X.MATH.APPTRIG", "Applications of Trigonometry", "X.MATH.U.TRIG"),
        Chapter("X.MATH.CIRCLE", "Circles", "X.MATH.U.GEOMETRY"),
        Chapter("X.MATH.AREAS", "Areas Related to Circles", "X.MATH.U.MENSURATION"),
        Chapter("X.MATH.SAV", "Surface Areas and Volumes", "X.MATH.U.MENSURATION"),
        Chapter("X.MATH.STATS", "Statistics", "X.MATH.U.STATSPROB"),
        Chapter("X.MATH.PROB", "Probability", "X.MATH.U.STATSPROB"),
    ],
    concept_families=[
        ("X.MATH.CF.VOLUME_COMPOSITE", "Volume of Composite Solids", "X.MATH.SAV"),
        ("X.MATH.CF.IRRATIONALITY", "Irrationality Proofs", "X.MATH.REAL"),
        ("X.MATH.CF.TRIG_IDENTITIES", "Trigonometric Identities", "X.MATH.TRIG"),
    ],
)

CURRICULA: dict[str, Curriculum] = {X_MATH.subject_code: X_MATH}


def chapter_title(subject_code: str, number: int) -> str | None:
    """The book's chapter N, by the name the syllabus gives it.

    An NCERT filename (jemh101.pdf) carries a number and no title, and the title on the
    page is a running header that only appears on odd pages -- six of fourteen chapters do
    not show it before their first section. The curriculum lists chapters in book order and
    is already the authority for chapter identity, since it carries the board-unit mapping.
    """
    curriculum = CURRICULA.get(subject_code)
    if curriculum is None or not (1 <= number <= len(curriculum.chapters)):
        return None
    return curriculum.chapters[number - 1].label
