"""Seed a demo school, a Class X Maths taxonomy slice and a Section B assessment.

Run with:  python -m scripts.seed
"""

from __future__ import annotations

import secrets

from sqlalchemy import select

from app.curriculum import X_MATH
from app.curriculum.apply import apply as apply_curriculum
from app.db import SessionLocal, init_db
from app.models import (
    Assessment,
    Question,
    School,
    Section,
    StudentProfile,
    TaxonomyNode,
)
from app.taxonomy.variants import variant_hash

# No hand-written subtopics: the book supplies them, verified against its own contents
# page. Seeding invented ones ("Cone", "Wordprob") left placeholders sitting beside the
# real sections, indistinguishable from them in the tree and in any report built on it.

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

    apply_curriculum(db, X_MATH)

    def node_for(code: str) -> TaxonomyNode:
        return db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))

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
