"""Shared guard rails for every script that changes database rows.

* Dry-run is the default: a script prints exactly what it would change and writes nothing.
* ``--apply`` is refused unless ``--i-have-a-backup`` is also given; without it the script
  prints the backup command to run first and exits non-zero.
* Every applied run writes a JSON undo file listing each changed row's old values (or,
  for an inserted row, its id), so a run can be reversed by hand.

Run these against a staging copy of the database first. No secret is printed: the backup
command names the environment variable that holds the connection string, never its value.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKUP_COMMAND = (
    'pg_dump "$YAADHUM_MIGRATION_DATABASE_URL" --format=custom '
    '--file "yaadhum-backup-$(date +%Y%m%d-%H%M%S).dump"'
)


def add_safety_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--apply", action="store_true",
        help="write the changes (default: dry run, print only)",
    )
    parser.add_argument(
        "--i-have-a-backup", action="store_true",
        help="confirm a database backup was taken just now; required with --apply",
    )
    parser.add_argument(
        "--undo-file", default=None,
        help="where to write the JSON undo file (default: ./undo-<script>-<time>.json)",
    )


def require_backup(args: argparse.Namespace) -> None:
    """Exit unless a dry run, or an apply the operator has confirmed a backup for."""
    if not args.apply:
        return
    if not args.i_have_a_backup:
        print(
            "Refusing to --apply without a backup. Take one first, for example:\n\n"
            f"    {BACKUP_COMMAND}\n\n"
            "then re-run with --apply --i-have-a-backup.",
            file=sys.stderr,
        )
        raise SystemExit(2)


class UndoLog:
    """Old values of every row an applied run changes, written as JSON at the end."""

    def __init__(self, script: str, path: str | None = None) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        self.path = Path(path or f"undo-{script}-{stamp}.json")
        self.script = script
        self.entries: list[dict] = []

    def inserted(self, table: str, row_id: str, values: dict) -> None:
        self.entries.append({"table": table, "op": "insert", "id": row_id, "new": values})

    def updated(self, table: str, row_id: str, old: dict, new: dict) -> None:
        self.entries.append({"table": table, "op": "update", "id": row_id, "old": old, "new": new})

    def deleted(self, table: str, row_id: str, old: dict) -> None:
        self.entries.append({"table": table, "op": "delete", "id": row_id, "old": old})

    def write(self) -> Path:
        self.path.write_text(json.dumps({
            "script": self.script,
            "written_at": datetime.now(UTC).isoformat(),
            "entries": self.entries,
        }, indent=2, default=str, ensure_ascii=False))
        return self.path
