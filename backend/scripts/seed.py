"""Seed a demo school, a Class X Maths taxonomy slice and a Section B assessment.

Run with:  python -m scripts.seed
"""

from __future__ import annotations

import secrets

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import (
    Assessment,
    ChapterWeight,
    Question,
    School,
    Section,
    StudentProfile,
    TaxonomyNode,
)

CHAPTERS = [
    ("X.MATH.REAL", "Real Numbers", 6.0),
    ("X.MATH.POLY", "Polynomials", 6.0),
    ("X.MATH.LINEQ", "Pair of Linear Equations", 8.0),
    ("X.MATH.QUAD", "Quadratic Equations", 8.0),
    ("X.MATH.AP", "Arithmetic Progressions", 8.0),
    ("X.MATH.TRIANGLE", "Triangles", 10.0),
    ("X.MATH.COORD", "Coordinate Geometry", 6.0),
    ("X.MATH.TRIG", "Introduction to Trigonometry", 12.0),
    ("X.MATH.CIRCLE", "Circles", 10.0),
    ("X.MATH.SAV", "Surface Areas and Volumes", 13.0),
    ("X.MATH.STATS", "Statistics", 11.0),
    ("X.MATH.PROB", "Probability", 2.0),
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

    for code, label, weight in CHAPTERS:
        node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
        if node is None:
            node = TaxonomyNode(
                kind="chapter", code=code, label=label, parent_id=subject.id, path=code
            )
            db.add(node)
            db.flush()
            db.add(
                ChapterWeight(
                    curriculum_version="CBSE-2026-27", chapter_id=node.id, weight_pct=weight,
                    source_doc_url="https://cbseacademic.nic.in/",
                )
            )
        for sub in SUBTOPICS.get(code, []):
            sub_code = f"{code}.{sub}"
            if not db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == sub_code)):
                db.add(
                    TaxonomyNode(
                        kind="subtopic", code=sub_code, label=sub.replace("_", " ").title(),
                        parent_id=node.id, path=sub_code,
                    )
                )

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
        for i in range(1, 6):
            qno = str(20 + i)
            if qno == "22":
                for alt in ("a", "b"):
                    db.add(
                        Question(
                            assessment_id=assessment.id, address=f"B/22//{alt}", section="B",
                            question_no="22", choice_alt=alt, max_marks=2,
                            question_type="VSA", choice_group_id="cg-B-22",
                        )
                    )
            else:
                db.add(
                    Question(
                        assessment_id=assessment.id, address=f"B/{qno}//", section="B",
                        question_no=qno, max_marks=2, question_type="VSA",
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
