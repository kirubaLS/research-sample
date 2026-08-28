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
    # Layer 1 needs real nodes to resolve against: every question carries a board unit and
    # a concept family, and the ingest refuses codes it cannot find.
    from app.models import TaxonomyNode

    subject = TaxonomyNode(kind="subject", code="X.MATH", label="Class X Maths", path="X.MATH")
    db.add(subject)
    db.flush()
    for kind, code, label in (
        ("board_unit", "X.MATH.U.MENSURATION", "Mensuration"),
        ("chapter", "X.MATH.SAV", "Surface Areas and Volumes"),
        ("concept_family", "X.MATH.CF.VOLUME", "Volume of Composite Solids"),
    ):
        db.add(TaxonomyNode(kind=kind, code=code, label=label, parent_id=subject.id, path=code))
    db.commit()

    out = {"school_id": s.id, "section_id": sec.id, "api_key": s.api_key}
    db.close()
    return out
