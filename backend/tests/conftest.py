from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("YAADHUM_DATABASE_URL", "")


@pytest.fixture(scope="session", autouse=True)
def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["YAADHUM_DATABASE_URL"] = f"sqlite+pysqlite:///{path}"
    yield
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture(scope="session")
def client(_tmp_db):
    from fastapi.testclient import TestClient

    from app.db import init_db
    from app.main import app

    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def school(_tmp_db):
    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.models import School, Section

    init_db()
    db = SessionLocal()
    s = School(name="Bharath International Sr. Sec.", api_key="test-key-123",
               state="Tamil Nadu", training_consent="training_permitted")
    db.add(s)
    db.flush()
    sec = Section(school_id=s.id, grade=10, name="A")
    db.add(sec)
    db.commit()
    # One source for the taxonomy: the same curriculum the operator console applies, so a
    # test cannot pass against a shape production never has.
    from app.curriculum import X_MATH
    from app.curriculum.apply import apply as apply_curriculum
    from app.models import TaxonomyNode

    apply_curriculum(db, X_MATH)
    if db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.VOLUME")
    ) is None:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.SAV"))
        db.add(TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.VOLUME",
            label="Volume of Composite Solids", parent_id=chapter.id,
            path="X.MATH.CF.VOLUME",
        ))
        db.commit()

    out = {"school_id": s.id, "section_id": sec.id, "api_key": s.api_key}
    db.close()
    return out


@pytest.fixture
def book(school):
    """A minimal loaded book: one chunk under a chapter, and a family applied to it.

    Mapping needs all three -- a chapter to retrieve, a board unit for its marks to count
    towards, and a concept family for the report to group by -- so a test that seeds none
    of them only ever exercises the blocked path.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import BookChunk, ConceptFamilyProposal, TaxonomyNode

    db = SessionLocal()

    # Several chunks across several chapters, because one chunk cannot be retrieved
    # against: TF-IDF gives every term an inverse document frequency of log(1/1) = 0 when
    # there is a single document, so every score is zero. Real books have hundreds.
    seed = [
        ("X.MATH.STATS", "S13_2", "Mean of Grouped Data", "Section 13.2",
         "The mean of grouped data by the step-deviation method uses an assumed mean "
         "and a common class size h to simplify the arithmetic of large class marks."),
        ("X.MATH.STATS", "S13_3", "Mode of Grouped Data", "Section 13.3",
         "The modal class is the class with the greatest frequency, and the mode is "
         "found from the frequencies either side of it."),
        ("X.MATH.CIRCLE", "S10_1", "Tangent to a Circle", "Theorem 10.1",
         "The tangent at any point of a circle is perpendicular to the radius through "
         "the point of contact."),
        ("X.MATH.REAL", "S1_2", "Fundamental Theorem", "Theorem 1.1",
         "Every composite number can be expressed as a product of primes, and this "
         "factorisation is unique apart from the order of the factors."),
        ("X.MATH.AP", "S5_2", "nth Term of an AP", "Section 5.2",
         "In an arithmetic progression with first term a and common difference d the "
         "nth term is given by a plus n minus one times d."),
    ]
    for chapter_code, section, label, reference, text in seed:
        chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == chapter_code))
        code = f"{chapter_code}.{section}"
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        if node is None:
            node = TaxonomyNode(
                kind="subtopic", code=code, label=label, parent_id=chapter.id,
                path=code, curriculum_version=chapter.curriculum_version,
            )
            db.add(node)
            db.flush()
            # Filed under the CHAPTER with the section recorded beside it, which is what
            # the book ingest does. Filing it under the section node instead -- as this
            # fixture used to -- let the section be recovered from the node's code, so
            # every test passed while production, where every chunk points at its chapter,
            # could never work out a section at all.
            db.add(BookChunk(
                curriculum_version=chapter.curriculum_version, subject_code="X.MATH",
                node_id=chapter.id, bucket="T", reference=reference, text=text,
                section_number=section[1:].replace("_", "."),
                normalised=text.lower(), stem_hash=code,
            ))

    stats = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.STATS"))
    if db.scalar(
        select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH.CF.MEAN_STEP_DEVIATION")
    ) is None:
        db.add(TaxonomyNode(
            kind="concept_family", code="X.MATH.CF.MEAN_STEP_DEVIATION",
            label="Mean by step-deviation", parent_id=stats.id,
            path="X.MATH.CF.MEAN_STEP_DEVIATION",
            curriculum_version=stats.curriculum_version,
        ))
    # The proposal that says which section this family covers. Without it the family is
    # chosen only when it is the chapter's sole one -- and another test in this suite
    # applies a second family to Statistics, so the pair became ambiguous and mapping
    # correctly refused. Production always has these rows; the fixture should too.
    if db.scalar(
        select(ConceptFamilyProposal).where(
            ConceptFamilyProposal.code == "X.MATH.CF.MEAN_STEP_DEVIATION"
        )
    ) is None:
        db.add(ConceptFamilyProposal(
            curriculum_version=stats.curriculum_version, subject_code="X.MATH",
            run_id="fixture", source="llm", model="fixture",
            code="X.MATH.CF.MEAN_STEP_DEVIATION", label="Mean by step-deviation",
            chapter_id=stats.id, evidence=["Section 13.2"], from_sections=["13.2"],
        ))
    db.commit()
    db.close()


