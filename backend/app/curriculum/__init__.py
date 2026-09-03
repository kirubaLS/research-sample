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

#: CBSE Class X Science: five units, 80 theory marks, 13 NCERT chapters.
#:
#: The unit weightage is the board's and is verified. The chapter list is deliberately
#: EMPTY: the rationalised syllabus renumbered the book, secondary sources disagree, and a
#: chapter mapped to the wrong unit sends a student's marks to the wrong place in the
#: report. The contents page of the book is the oracle for that -- as it already is for
#: sections -- so chapters are added from it rather than from recollection.
#:
#: Until they are, `scripts.ingest_book` will create the chapters and name them as
#: unmapped to a board unit, which is visible rather than silent.
X_SCIENCE = Curriculum(
    subject_code="X.SCI",
    subject_label="Class X Science",
    grade=10,
    units=[
        BoardUnit("X.SCI.U.CHEMICAL", "Chemical Substances -- Nature and Behaviour", 25.0),
        BoardUnit("X.SCI.U.LIVING", "World of Living", 25.0),
        BoardUnit("X.SCI.U.CURRENT", "Effects of Current", 13.0),
        BoardUnit("X.SCI.U.PHENOMENA", "Natural Phenomena", 12.0),
        BoardUnit("X.SCI.U.RESOURCES", "Natural Resources", 5.0),
    ],
    # Read off the contents page of the NCERT Class X Science textbook, Reprint 2026-27
    # (jesc1ps.pdf, page xi): thirteen chapters, in book order. Order is load-bearing --
    # chapter_title() resolves an NCERT filename like jesc108.pdf by position, so an
    # inserted or reordered row silently retitles a chapter.
    chapters=[
        Chapter("X.SCI.CHEMRXN", "Chemical Reactions and Equations", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.ACIDS", "Acids, Bases and Salts", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.METALS", "Metals and Non-metals", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.CARBON", "Carbon and its Compounds", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.LIFEPROC", "Life Processes", "X.SCI.U.LIVING"),
        Chapter("X.SCI.CONTROL", "Control and Coordination", "X.SCI.U.LIVING"),
        Chapter("X.SCI.REPRO", "How do Organisms Reproduce?", "X.SCI.U.LIVING"),
        Chapter("X.SCI.HEREDITY", "Heredity", "X.SCI.U.LIVING"),
        Chapter("X.SCI.LIGHT", "Light \u2013 Reflection and Refraction", "X.SCI.U.PHENOMENA"),
        Chapter("X.SCI.EYE", "The Human Eye and the Colourful World", "X.SCI.U.PHENOMENA"),
        Chapter("X.SCI.ELECTRICITY", "Electricity", "X.SCI.U.CURRENT"),
        Chapter("X.SCI.MAGNETIC", "Magnetic Effects of Electric Current", "X.SCI.U.CURRENT"),
        Chapter("X.SCI.ENVIRONMENT", "Our Environment", "X.SCI.U.RESOURCES"),
    ],
    # Deliberately empty. The Maths families were proposed from the book's own section
    # headings once the chapters were embedded, then reviewed; Science gets the same
    # treatment and not a set invented ahead of the text.
    concept_families=[],
)

#: CBSE Class X Social Science is four separate NCERT books, not one: each book's own
#: chapter numbering restarts at 1, and `chapter_number()` reads that number off the
#: filename alone (jess101.pdf -> chapter 1). One subject code per book, the same way
#: X.MATH and X.SCI are each exactly one book, so two different books' "chapter 1" can
#: never collide under a shared code.
#:
#: Board-unit weightage is a placeholder (0.0) pending the official CBSE blueprint --
#: `apply()` only ever creates a BoardUnitWeight once, so setting a guessed number now
#: would need a second write path to correct later, not just a re-run. The chapter list
#: itself is real: read off each book's own contents page (Reprint 2026-27), not recalled.
X_HISTORY = Curriculum(
    subject_code="X.HIST",
    subject_label="Class X History (India and the Contemporary World – II)",
    grade=10,
    units=[
        BoardUnit("X.HIST.U.WHOLE", "India and the Contemporary World – II", 0.0),
    ],
    # jess3ps.pdf, page xi. Three named sections in the book; kept as one board unit
    # until the blueprint says otherwise.
    chapters=[
        Chapter("X.HIST.NATIONALISM_EUROPE", "The Rise of Nationalism in Europe", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.NATIONALISM_INDIA", "Nationalism in India", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.GLOBALWORLD", "The Making of a Global World", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.INDUSTRIALISATION", "The Age of Industrialisation", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.PRINTCULTURE", "Print Culture and the Modern World", "X.HIST.U.WHOLE"),
    ],
    concept_families=[],
)

X_GEOGRAPHY = Curriculum(
    subject_code="X.GEO",
    subject_label="Class X Geography (Contemporary India – II)",
    grade=10,
    units=[
        BoardUnit("X.GEO.U.WHOLE", "Contemporary India – II", 0.0),
    ],
    # jess1ps.pdf, Contents page.
    chapters=[
        Chapter("X.GEO.RESOURCES", "Resources and Development", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.FORESTWILDLIFE", "Forest and Wildlife Resources", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.WATER", "Water Resources", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.AGRICULTURE", "Agriculture", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.MINERALSENERGY", "Minerals and Energy Resources", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.MANUFACTURING", "Manufacturing Industries", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.LIFELINES", "Lifelines of National Economy", "X.GEO.U.WHOLE"),
    ],
    concept_families=[],
)

X_POLITICAL_SCIENCE = Curriculum(
    subject_code="X.POL",
    subject_label="Class X Political Science (Democratic Politics – II)",
    grade=10,
    units=[
        BoardUnit("X.POL.U.WHOLE", "Democratic Politics – II", 0.0),
    ],
    # jess4ps.pdf, Contents page. The book itself labels these Unit I-IV; kept as one
    # board unit here for the same reason as History's sections, until the blueprint
    # says whether the board scores them separately.
    chapters=[
        Chapter("X.POL.POWERSHARING", "Power-sharing", "X.POL.U.WHOLE"),
        Chapter("X.POL.FEDERALISM", "Federalism", "X.POL.U.WHOLE"),
        Chapter("X.POL.GENDERRELIGIONCASTE", "Gender, Religion and Caste", "X.POL.U.WHOLE"),
        Chapter("X.POL.PARTIES", "Political Parties", "X.POL.U.WHOLE"),
        Chapter("X.POL.OUTCOMES", "Outcomes of Democracy", "X.POL.U.WHOLE"),
    ],
    concept_families=[],
)

X_ECONOMICS = Curriculum(
    subject_code="X.ECO",
    subject_label="Class X Economics (Understanding Economic Development)",
    grade=10,
    units=[
        BoardUnit("X.ECO.U.WHOLE", "Understanding Economic Development", 0.0),
    ],
    # jess2ps.pdf, Contents page.
    chapters=[
        Chapter("X.ECO.DEVELOPMENT", "Development", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.SECTORS", "Sectors of the Indian Economy", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.MONEYCREDIT", "Money and Credit", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.GLOBALISATION", "Globalisation and the Indian Economy", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.CONSUMERRIGHTS", "Consumer Rights", "X.ECO.U.WHOLE"),
    ],
    concept_families=[],
)

CURRICULA: dict[str, Curriculum] = {
    X_MATH.subject_code: X_MATH,
    X_SCIENCE.subject_code: X_SCIENCE,
    X_HISTORY.subject_code: X_HISTORY,
    X_GEOGRAPHY.subject_code: X_GEOGRAPHY,
    X_POLITICAL_SCIENCE.subject_code: X_POLITICAL_SCIENCE,
    X_ECONOMICS.subject_code: X_ECONOMICS,
}


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
