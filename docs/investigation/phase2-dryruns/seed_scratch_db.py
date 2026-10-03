"""Scratch database for the Phase 2 dry runs. Not part of the repo."""
import subprocess, sys
from sqlalchemy import select
from app.db import init_db, SessionLocal
from app.curriculum import CURRICULA, X_HISTORY, X_GEOGRAPHY, X_POLITICAL_SCIENCE, X_ECONOMICS, X_SCIENCE
from app.curriculum.apply import apply
from app.models import TaxonomyNode, Question, QuestionSkill, Assessment, School
from app.taxonomy.variants import variant_hash

init_db(); db = SessionLocal()
for c in (X_HISTORY, X_GEOGRAPHY, X_POLITICAL_SCIENCE, X_ECONOMICS, X_SCIENCE):
    apply(db, c)
db.commit(); db.close()
print(subprocess.run([sys.executable, "-m", "scripts.import_book_map", "--apply"], capture_output=True, text=True).stdout[-600:])

from scripts.load_expected_sections import EXPECTED_SECTIONS, UNVERIFIED_EXPECTED_SECTIONS, _merged
from app.curriculum.book_map import chapter_units
db = SessionLocal()
by_code = {n.code: n for n in db.scalars(select(TaxonomyNode))}
made = 0
oracle = _merged(EXPECTED_SECTIONS, UNVERIFIED_EXPECTED_SECTIONS)
for subject in ("X.HIST", "X.GEO", "X.POL", "X.ECO"):
    chapters = CURRICULA[subject].chapters
    for number, sections in oracle.get(subject, {}).items():
        chapter = by_code[chapters[int(number) - 1].code]
        for s in sections:   # what books._load wrote at PDF ingest: reading-order numbers
            code = f"{chapter.code}.S{s['number'].replace('.', '_')}"
            if code not in by_code:
                n = TaxonomyNode(kind="subtopic", code=code, label=s["title"], parent_id=chapter.id,
                                 path=code, curriculum_version=chapter.curriculum_version)
                db.add(n); by_code[code] = n; made += 1
    for ch in chapters:      # what the old mapping path created for deep sections
        chapter = by_code[ch.code]
        for u in chapter_units(ch.code) or ():
            if u.number and u.number.count(".") >= 2:
                code = f"{chapter.code}.S{u.number.replace('.', '_')}"
                if code not in by_code:
                    n = TaxonomyNode(kind="subtopic", code=code, label=f"{u.number} {u.title}",
                                     parent_id=chapter.id, path=code, curriculum_version=chapter.curriculum_version)
                    db.add(n); by_code[code] = n; made += 1
db.flush()
# three synthetic questions, so the reference listing has rows to show
school = School(name="Scratch", api_key="scratch-key", state="TN", training_consent="training_permitted")
db.add(school); db.flush()
a = Assessment(school_id=school.id, subject_code="X.SST", title="Scratch")
db.add(a); db.flush()
unit = by_code["X.GEO.U.WHOLE"]
for addr, chapter_code, section, node_code, family_code in [
    ("C/23//", "X.POL.PARTIES", "4", "X.POL.PARTIES.S4", "X.POL.CF.FUNCTIONS"),
    ("B/19/19.3/", "X.GEO.MINERALSENERGY", "4.1.2", "X.GEO.MINERALSENERGY.S4_1_2", "X.GEO.CF.PETROLEUM"),
    ("B/16//", "X.GEO.MINERALSENERGY", "2.1", "X.GEO.MINERALSENERGY.S2_1", "X.GEO.CF.RAT_HOLE_MINING"),
    # the backup's shape: a topic link on 4.1.4 Electricity, the question itself in 4.2.1
    ("B/19/19.7/", "X.GEO.MINERALSENERGY", "4.2.1", "X.GEO.MINERALSENERGY.S4_1_4", "X.GEO.CF.ELECTRICITY"),
]:
    fam = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == family_code))
    unit = by_code["X.POL.U.WHOLE" if chapter_code.startswith("X.POL") else "X.GEO.U.WHOLE"]
    if node_code not in by_code:
        ch = by_code[chapter_code]
        n = TaxonomyNode(kind="subtopic", code=node_code, label="2.1 Rat-Hole Mining", parent_id=ch.id,
                         path=node_code, curriculum_version=ch.curriculum_version)
        db.add(n); db.flush(); by_code[node_code] = n; made += 1
    q = Question(assessment_id=a.id, address=addr, section=addr[0], question_no=addr.split("/")[1],
                 max_marks=1, stem_text=f"synthetic {addr}", board_unit_id=unit.id,
                 chapter_id=by_code[chapter_code].id, curriculum_section=section,
                 concept_family_id=fam.id, concept_variant=f"synthetic {addr}",
                 variant_hash=variant_hash(f"synthetic {addr}"))
    db.add(q); db.flush()
    db.add(QuestionSkill(question_id=q.id, node_id=by_code[node_code].id, source="retrieval", weight=1.0))
db.commit()
print("simulated subtopic nodes:", made)
