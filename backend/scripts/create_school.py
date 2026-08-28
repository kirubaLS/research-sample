"""Provision a real school in production -- no demo data.

`scripts.seed` exists for a laptop: it invents forty students so the dashboard has
something to show. Do not run it against a school's live database. This does the real
thing instead: one school, its sections, and the API key the principal signs in with.

    python -m scripts.create_school "Bharath International Sr. Sec. School" \
        --state "Tamil Nadu" --sections 10-A 10-B

Students are NOT created here. A student enrols themselves the first time they open the
class link and fill in the form, which is also how their name and roll number get in.
"""

from __future__ import annotations

import argparse
import secrets

from sqlalchemy import select

from app.db import SessionLocal
from app.models import School, Section


def parse_section(spec: str) -> tuple[int, str]:
    """'10-A' -> (10, 'A'). Kept strict: a typo here becomes a wrong class link."""
    grade, _, name = spec.partition("-")
    if not grade.isdigit() or not name:
        raise argparse.ArgumentTypeError(f"section must look like 10-A, got {spec!r}")
    return int(grade), name.upper()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="the school's full name, as it should appear to staff")
    parser.add_argument("--state", default="Tamil Nadu")
    parser.add_argument("--board", default="CBSE")
    parser.add_argument(
        "--sections", nargs="+", type=parse_section, default=[(10, "A")],
        help="one or more sections, as GRADE-NAME (e.g. 10-A 10-B)",
    )
    parser.add_argument(
        "--consent", default="operational_only",
        choices=["operational_only", "improve_models", "research"],
        help="what the school has agreed their data may be used for",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        school = db.scalar(select(School).where(School.name == args.name))
        if school is None:
            school = School(
                name=args.name, board=args.board, state=args.state,
                api_key=secrets.token_urlsafe(24), training_consent=args.consent,
            )
            db.add(school)
            db.flush()
            print(f"created school {args.name!r}")
        else:
            print(f"school {args.name!r} already exists -- adding any missing sections")

        created = []
        for grade, name in args.sections:
            section = db.scalar(
                select(Section).where(
                    Section.school_id == school.id, Section.grade == grade, Section.name == name
                )
            )
            if section is None:
                section = Section(school_id=school.id, grade=grade, name=name)
                db.add(section)
                db.flush()
            created.append(section)

        db.commit()

        print()
        print(f"school  : {school.name}")
        print(f"id      : {school.id}")
        print(f"API key : {school.api_key}      <- the principal signs in with this")
        print()
        print("class links (the dashboard shows these with a Copy button):")
        for section in created:
            print(f"  Class {section.grade}-{section.name}  ->  /t/{section.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
