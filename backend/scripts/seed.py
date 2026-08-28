"""Seed a demo school, a Class X Maths taxonomy slice and a Section B assessment.

Run with:  python -m scripts.seed
"""

from __future__ import annotations

import secrets

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import (
    Assessment,
    BoardUnitWeight,
    ChapterBoardUnit,
    Question,
    School,
    Section,
    StudentProfile,
    TaxonomyNode,
)
from app.taxonomy.variants import variant_hash

#: CBSE's own published weightage units for Class X Mathematics. Note that Algebra spans
#: four chapters and Geometry two -- the case that makes Board Unit a separate field from
#: Chapter rather than a rename of it.
BOARD_UNITS = [
    ("X.MATH.U.NUMBER", "Number Systems", 6.0),
    ("X.MATH.U.ALGEBRA", "Algebra", 20.0),
    ("X.MATH.U.COORD", "Coordinate Geometry", 6.0),
    ("X.MATH.U.GEOMETRY", "Geometry", 15.0),
    ("X.MATH.U.TRIG", "Trigonometry", 12.0),
    ("X.MATH.U.MENSURATION", "Mensuration", 10.0),
    ("X.MATH.U.STATSPROB", "Statistics & Probability", 11.0),
]

#: (code, label, board unit). Weight lives on the unit now, never on the chapter.
CHAPTERS = [
    ("X.MATH.REAL", "Real Numbers", "X.MATH.U.NUMBER"),
    ("X.MATH.POLY", "Polynomials", "X.MATH.U.ALGEBRA"),
    ("X.MATH.LINEQ", "Pair of Linear Equations", "X.MATH.U.ALGEBRA"),
    ("X.MATH.QUAD", "Quadratic Equations", "X.MATH.U.ALGEBRA"),
    ("X.MATH.AP", "Arithmetic Progressions", "X.MATH.U.ALGEBRA"),
    ("X.MATH.TRIANGLE", "Triangles", "X.MATH.U.GEOMETRY"),
    ("X.MATH.COORD", "Coordinate Geometry", "X.MATH.U.COORD"),
    ("X.MATH.TRIG", "Introduction to Trigonometry", "X.MATH.U.TRIG"),
    ("X.MATH.CIRCLE", "Circles", "X.MATH.U.GEOMETRY"),
    ("X.MATH.SAV", "Surface Areas and Volumes", "X.MATH.U.MENSURATION"),
    ("X.MATH.STATS", "Statistics", "X.MATH.U.STATSPROB"),
    ("X.MATH.PROB", "Probability", "X.MATH.U.STATSPROB"),
]

#: Concept families are held constant across cycles -- this is the axis a trend groups by.
CONCEPT_FAMILIES = [
    ("X.MATH.CF.VOLUME_COMPOSITE", "Volume of Composite Solids", "X.MATH.SAV"),
    ("X.MATH.CF.IRRATIONALITY", "Irrationality Proofs", "X.MATH.REAL"),
    ("X.MATH.CF.TRIG_IDENTITIES", "Trigonometric Identities", "X.MATH.TRIG"),
]

SUBTOPICS = {
    "X.MATH.SAV": ["CONE", "CYLINDER", "SPHERE", "COMPOSITE", "WORDPROB"],
    "X.MATH.REAL": ["IRRATIONAL", "HCF_LCM", "FTA"],
    "X.MATH.TRIG": ["RATIOS", "IDENTITIES", "SPECIFIC_ANGLES"],
}


def main() -> None:
    init_db()
    db = SessionLocal()

    school = db.scalar(select(School).where(School.name.like("Bharath%")))
    if school is None:
        school = School(
            name="Bharath International Sr. Sec. School",
            state="Tamil Nadu",
            api_key=secrets.token_urlsafe(24),
            training_consent="operational_only",
        )
        db.add(school)
        db.flush()

    section = db.scalar(select(Section).where(Section.school_id == school.id))
    if section is None:
        section = Section(school_id=school.id, grade=10, name="A")
        db.add(section)
        db.flush()

    for i in range(1, 41):
        roll = f"{i:03d}"
        if not db.scalar(
            select(StudentProfile).where(
                StudentProfile.section_id == section.id, StudentProfile.roll_no == roll
            )
        ):
            db.add(
                StudentProfile(
                    school_id=school.id, section_id=section.id,
                    name=f"Student {roll}", roll_no=roll, age=15,
                )
            )

    subject = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.MATH"))
    if subject is None:
        subject = TaxonomyNode(
            kind="subject", code="X.MATH", label="Class X Mathematics", path="X.MATH"
        )
        db.add(subject)
        db.flush()

    def node_for(code: str) -> TaxonomyNode:
        return db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))

    for code, label, weight in BOARD_UNITS:
        if node_for(code) is None:
            unit = TaxonomyNode(
                kind="board_unit", code=code, label=label, parent_id=subject.id, path=code
            )
            db.add(unit)
            db.flush()
            db.add(
                BoardUnitWeight(
                    curriculum_version="CBSE-2026-27", board_unit_id=unit.id,
                    weight_pct=weight, source_doc_url="https://cbseacademic.nic.in/",
                )
            )

    for code, label, unit_code in CHAPTERS:
        node = node_for(code)
        if node is None:
            node = TaxonomyNode(
                kind="chapter", code=code, label=label, parent_id=subject.id, path=code
            )
            db.add(node)
            db.flush()
            # explicit mapping, never inferred from the tree -- the History-map-marks case
            db.add(
                ChapterBoardUnit(
                    curriculum_version="CBSE-2026-27", chapter_id=node.id,
                    board_unit_id=node_for(unit_code).id,
                )
            )
        for sub in SUBTOPICS.get(code, []):
            sub_code = f"{code}.{sub}"
            if node_for(sub_code) is None:
                db.add(
                    TaxonomyNode(
                        kind="subtopic", code=sub_code, label=sub.replace("_", " ").title(),
                        parent_id=node.id, path=sub_code,
                    )
                )

    for code, label, chapter_code in CONCEPT_FAMILIES:
        if node_for(code) is None:
            db.add(
                TaxonomyNode(
                    kind="concept_family", code=code, label=label,
                    parent_id=node_for(chapter_code).id, path=code,
                )
            )
    db.flush()

    assessment = db.scalar(select(Assessment).where(Assessment.paper_code == "30(B)"))
    if assessment is None:
        assessment = Assessment(
            school_id=school.id, subject_code="X.MATH",
            title="Unit Test II — Section B", paper_code="30(B)", total_marks=10,
            imposition=4, rotation=0, languages=["en", "hi"], route="vision",
            declared={"question_count": 5, "total_marks": 10, "sections": {"B": 10}},
        )
        db.add(assessment)
        db.flush()
        # Every question carries a board unit and a concept family; chapter and section
        # are filled here because these are content-anchored. Variants differ per question
        # so a later cycle can reuse the family without reusing the question.
        mensuration = node_for("X.MATH.U.MENSURATION").id
        family = node_for("X.MATH.CF.VOLUME_COMPOSITE").id
        variants = {
            "21": "Cone + Hemisphere, r = 3.5 cm",
            "22a": "Cylinder + Hemisphere, h = 10 cm",
            "22b": "Frustum, R = 8 cm",
            "23": "Cone + Cylinder, slant height given",
            "24": "Sphere inscribed in a cylinder",
            "25": "Hemisphere on a cube",
        }

        def question_kwargs(key: str) -> dict:
            label = variants[key]
            return {
                "board_unit_id": mensuration,
                "chapter_id": node_for("X.MATH.SAV").id,
                "curriculum_section": "12.2",
                "curriculum_section_title": "Volume of Combination of Solids",
                "verified_against": "NCERT Mathematics X, 2023 reprint",
                "concept_family_id": family,
                "concept_variant": label,
                "variant_hash": variant_hash(label),
            }

        for i in range(1, 6):
            qno = str(20 + i)
            if qno == "22":
                for alt in ("a", "b"):
                    db.add(
                        Question(
                            assessment_id=assessment.id, address=f"B/22//{alt}", section="B",
                            question_no="22", choice_alt=alt, max_marks=2,
                            question_type="VSA", choice_group_id="cg-B-22",
                            **question_kwargs(f"22{alt}"),
                        )
                    )
            else:
                db.add(
                    Question(
                        assessment_id=assessment.id, address=f"B/{qno}//", section="B",
                        question_no=qno, max_marks=2, question_type="VSA",
                        **question_kwargs(qno),
                    )
                )

    db.commit()
    print("school     :", school.name)
    print("API key    :", school.api_key)
    print("class code :", section.id)
    print("assessment :", assessment.id)
    db.close()


if __name__ == "__main__":
    main()
