"""Add short chapter names for Class X Social Science as ``taxonomy_alias`` rows.

Papers name chapters by short forms -- "Globalisation", "Minerals", "Lifelines", "Print
Culture" -- that the curriculum's full titles do not match closely enough for
``app.curriculum.resolve`` to accept. This script inserts those short names as aliases of
the chapter nodes. It only inserts: no existing row is changed or removed, and an alias
that already exists for the chapter (case-insensitively) or equals the chapter's own label
is skipped.

Dry run by default. Run against a staging copy of the database first.

    python -m scripts.seed_sst_aliases
    python -m scripts.seed_sst_aliases --apply --i-have-a-backup
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.curriculum.resolve import normalise
from app.db import SessionLocal
from app.models import TaxonomyAlias, TaxonomyNode
from scripts._row_safety import UndoLog, add_safety_args, require_backup

#: Short names a paper prints for each chapter. General names only, never one paper's
#: wording; each must still name exactly one chapter of the group.
SST_SHORT_NAMES: dict[str, list[str]] = {
    "X.HIST.NATIONALISM_EUROPE": ["Nationalism in Europe", "Rise of Nationalism in Europe"],
    "X.HIST.NATIONALISM_INDIA": ["Nationalism in India"],
    "X.HIST.GLOBALWORLD": ["Making of a Global World", "Global World"],
    "X.HIST.INDUSTRIALISATION": ["Age of Industrialisation", "Industrialisation"],
    "X.HIST.PRINTCULTURE": ["Print Culture"],
    "X.GEO.FORESTWILDLIFE": ["Forest and Wildlife", "Forests and Wildlife"],
    "X.GEO.MINERALSENERGY": ["Minerals", "Minerals and Energy", "Energy Resources"],
    "X.GEO.MANUFACTURING": ["Manufacturing"],
    "X.GEO.LIFELINES": ["Lifelines", "Lifelines of the National Economy"],
    "X.POL.PARTIES": ["Political Parties"],
    "X.ECO.SECTORS": ["Sectors of Economy", "Sectors of the Economy"],
    "X.ECO.GLOBALISATION": ["Globalisation", "Globalization"],
}


def plan(db) -> list[tuple[TaxonomyNode, str, str]]:
    """(chapter node, alias, action) for every short name; action is 'insert' or a skip
    reason."""
    out: list[tuple[TaxonomyNode, str, str]] = []
    for code, names in SST_SHORT_NAMES.items():
        node = db.scalar(select(TaxonomyNode).where(
            TaxonomyNode.code == code, TaxonomyNode.kind == "chapter",
        ))
        if node is None:
            out.append((None, f"{code}: {', '.join(names)}", "skip: chapter not in database"))
            continue
        held = {
            normalise(a.alias)
            for a in db.scalars(select(TaxonomyAlias).where(TaxonomyAlias.node_id == node.id))
        }
        for name in names:
            if normalise(name) == normalise(node.label):
                out.append((node, name, "skip: equals the chapter label"))
            elif normalise(name) in held:
                out.append((node, name, "skip: alias already exists"))
            else:
                out.append((node, name, "insert"))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    add_safety_args(parser)
    args = parser.parse_args(argv)
    require_backup(args)

    db = SessionLocal()
    try:
        rows = plan(db)
        inserts = 0
        print("DRY RUN -- nothing will be written" if not args.apply else "APPLYING")
        for node, alias, action in rows:
            code = node.code if node is not None else ""
            print(f"  {action:<32} {code:<28} {alias}")
            inserts += action == "insert"
        print(f"{inserts} alias row(s) to insert, {len(rows) - inserts} skipped")
        if not args.apply or not inserts:
            return 0
        undo = UndoLog("seed_sst_aliases", args.undo_file)
        for node, alias, action in rows:
            if action != "insert":
                continue
            row = TaxonomyAlias(node_id=node.id, alias=alias, locale="en")
            db.add(row)
            db.flush()
            undo.inserted("taxonomy_alias", row.id,
                          {"node_id": node.id, "alias": alias, "locale": "en"})
        db.commit()
        print(f"inserted {inserts}; undo file: {undo.write()}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
