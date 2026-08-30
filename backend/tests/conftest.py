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
