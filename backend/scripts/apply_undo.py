"""Reverse an applied script run from the JSON undo file it wrote (scripts/_row_safety.py).

The undo file lists every row the run changed, in order: an ``insert`` (the new row's id
and values), an ``update`` (the old and new values of the columns it changed) or a
``delete`` (the deleted row's old values). This walks it backwards and puts each row back:
an inserted row is deleted, an updated row gets its old values again, a deleted row is
re-inserted with its old id and values.

Before touching a row it checks the row is still as the run left it (an updated row still
holds the run's new values, an inserted row still exists, a deleted row's id is free). A
row someone changed since is reported as a CONFLICT and nothing is written unless
``--force``: reversing over a later edit would silently lose it.

Dry run by default: it prints what it would do. Writing needs --apply and
--i-have-a-backup, like every script that changes rows, and writes an undo file of its own.

    python -m scripts.apply_undo undo-clean_book_map_subtopics-20261005-101500.json
    python -m scripts.apply_undo undo-....json --apply --i-have-a-backup

Run the undo files newest first when reversing several runs.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Date, DateTime, delete, insert, select, update

from scripts._row_safety import UndoLog, add_safety_args, require_backup


def _coerce(table, values: dict) -> dict:
    """JSON-read values back to what the columns take (the undo file stores datetimes as
    strings); unknown keys are dropped."""
    out = {}
    for key, value in (values or {}).items():
        column = table.columns.get(key)
        if column is None:
            continue
        if isinstance(value, str) and isinstance(column.type, DateTime):
            value = datetime.fromisoformat(value)
        elif isinstance(value, str) and isinstance(column.type, Date):
            value = date.fromisoformat(value[:10])
        out[key] = value
    return out


def _same(row, values: dict) -> bool:
    return all(
        str(getattr(row, k)) == str(v) if v is not None else getattr(row, k) is None
        for k, v in values.items()
    )


def plan(db, entries: list[dict]) -> list[tuple[dict, str]]:
    """(entry, "ok" | a conflict description) for each entry, newest first."""
    from app.models import Base

    out = []
    for entry in reversed(entries):
        table = Base.metadata.tables.get(entry["table"])
        if table is None:
            out.append((entry, f"no table {entry['table']!r}"))
            continue
        row = db.execute(select(table).where(table.c.id == entry["id"])).first()
        if entry["op"] == "insert":
            status = "ok" if row is not None else "already gone"
        elif entry["op"] == "update":
            new = _coerce(table, entry.get("new"))
            status = "ok" if row is not None and _same(row, new) else (
                "row missing" if row is None else "changed since the run")
        elif entry["op"] == "delete":
            status = "ok" if row is None else "id is in use again"
        else:
            status = f"unknown op {entry['op']!r}"
        out.append((entry, status))
    return out


def main(argv: list[str] | None = None) -> int:
    from app.db import SessionLocal
    from app.models import Base

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", metavar="UNDO_FILE", help="the undo file a run wrote")
    parser.add_argument("--force", action="store_true",
                        help="reverse the rows that are ok even when others conflict")
    add_safety_args(parser)
    args = parser.parse_args(argv)
    require_backup(args)
    data = json.loads(Path(args.source).read_text())
    entries = data.get("entries", [])
    db = SessionLocal()
    try:
        steps = plan(db, entries)
        print("DRY RUN -- nothing will be written" if not args.apply else "APPLYING")
        print(f"undo file {args.source}: {len(entries)} entries from {data.get('script')!r} "
              f"written {data.get('written_at')}")
        conflicts = [(e, s) for e, s in steps if s != "ok"]
        for entry, status in steps:
            action = {"insert": "delete", "update": "restore", "delete": "re-insert"}.get(entry["op"], "?")
            print(f"  {'ok      ' if status == 'ok' else 'CONFLICT'} {action:<9} {entry['table']:<20} "
                  f"{entry['id']}" + ("" if status == "ok" else f"  ({status})"))
        print(f"\nTOTAL {len(steps) - len(conflicts)} to reverse, {len(conflicts)} conflict(s)")
        if not args.apply:
            return 0
        if conflicts and not args.force:
            print("Refusing to apply with conflicts; resolve them or pass --force.")
            return 3
        undo = UndoLog("apply_undo", args.undo_file)
        for entry, status in steps:
            if status != "ok":
                continue
            table = Base.metadata.tables[entry["table"]]
            if entry["op"] == "insert":
                row = db.execute(select(table).where(table.c.id == entry["id"])).first()
                undo.deleted(entry["table"], entry["id"], dict(row._mapping))
                db.execute(delete(table).where(table.c.id == entry["id"]))
            elif entry["op"] == "update":
                old = _coerce(table, entry.get("old"))
                undo.updated(entry["table"], entry["id"], entry.get("new") or {}, entry.get("old") or {})
                db.execute(update(table).where(table.c.id == entry["id"]).values(**old))
            elif entry["op"] == "delete":
                values = {**_coerce(table, entry.get("old")), "id": entry["id"]}
                undo.inserted(entry["table"], entry["id"], entry.get("old") or {})
                db.execute(insert(table).values(**values))
        db.commit()
        print(f"applied; undo file: {undo.write()}")
    finally:
        db.rollback()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
