"""Show or rotate a school's admin API key -- the principal's only credential.

There are no admin accounts and no passwords by design: one key per school, held by the
principal, sent as X-API-Key. This is how you find it after a deploy, and how you replace
it if it leaks.

    python -m scripts.admin_key                 # list every school and its key
    python -m scripts.admin_key --rotate <id>   # issue a new key, invalidating the old one
"""

from __future__ import annotations

import argparse
import secrets

from sqlalchemy import select

from app.db import SessionLocal
from app.models import School


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotate", metavar="SCHOOL_ID", help="issue a new key for this school")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.rotate:
            school = db.get(School, args.rotate)
            if school is None:
                raise SystemExit(f"no school with id {args.rotate}")
            school.api_key = secrets.token_urlsafe(24)
            db.commit()
            print("rotated. anyone holding the old key is now signed out.\n")

        schools = db.scalars(select(School).order_by(School.name)).all()
        if not schools:
            raise SystemExit("no schools yet -- run: python -m scripts.seed")
        for school in schools:
            print(f"school  : {school.name}")
            print(f"id      : {school.id}")
            print(f"API key : {school.api_key}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
