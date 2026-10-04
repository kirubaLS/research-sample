"""Build ``reference/book_map/section_cards.json``: one card per major topic of every
Social Science chapter (History, Geography, Politics, Economics). Offline and
deterministic -- no database, no network, no model call.

    python -m scripts.build_section_cards            # write the file
    python -m scripts.build_section_cards --check    # exit 1 when the file is stale

``--check`` also verifies coverage: every major topic of every chapter has a card.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.classify.section_cards import CARDS_FILE, build_cards, tokens
from app.curriculum.book_map import major_headings, major_of
from scripts.import_book_map import REFERENCE_DIR, SUBJECT_FILES, _load_chapter, _text_chunks

SUBJECTS = ("X.HIST", "X.GEO", "X.POL", "X.ECO")
DEPTH = 2


def chapter_sections(chapter_code: str) -> dict[str, dict]:
    """major topic -> {"heading", "chunks"} for one chapter, every unit folded under
    the major topic it belongs to (the same view the topic judge reads)."""
    subject = ".".join(chapter_code.split(".")[:2])
    chapter = _load_chapter(REFERENCE_DIR / SUBJECT_FILES[subject], chapter_code)
    out: dict[str, dict] = {}
    for unit in chapter["units"]:
        top = major_of(chapter_code, unit.get("number"), DEPTH)
        if top is None:
            continue
        slot = out.setdefault(top, {"heading": None, "chunks": []})
        if unit.get("number") == top or slot["heading"] is None:
            slot["heading"] = f"{top} {unit.get('title') or ''}".strip()
        slot["chunks"] += [text for _, _, text in _text_chunks(chapter_code, unit)]
    return out


def structural_terms(chapter_code: str) -> dict[str, list[str]]:
    """Glossary terms and box/source titles per major topic: the book's own vocabulary."""
    subject = ".".join(chapter_code.split(".")[:2])
    chapter = _load_chapter(REFERENCE_DIR / SUBJECT_FILES[subject], chapter_code)
    out: dict[str, list[str]] = {}
    for unit in chapter["units"]:
        top = major_of(chapter_code, unit.get("number"), DEPTH)
        if top is None:
            continue
        got = out.setdefault(top, [])
        got += [t["term"] for t in unit.get("terms", []) if t.get("term")]
        got += [b["title"] for b in unit.get("boxes", []) + unit.get("sources", []) if b.get("title")]
    return out


def build() -> tuple[dict, list[str]]:
    """(the file's content, the problems found: topics without a card)."""
    out: dict[str, dict] = {}
    problems: list[str] = []
    for subject in SUBJECTS:
        for chapter in json.loads((REFERENCE_DIR / SUBJECT_FILES[subject]).read_text()):
            code = chapter["code"]
            sections = chapter_sections(code)
            cards = build_cards(sections, structural_terms(code))
            for topic in major_headings(code, DEPTH) or {}:
                if topic not in cards:
                    problems.append(f"{code} topic {topic} has no card")
            out[code] = {
                "title": chapter["title"], "topics": len(cards),
                "full_tokens": sum(tokens(" ".join(v["chunks"])) for v in sections.values()),
                "card_tokens": sum(tokens(c) for c in cards.values()), "cards": cards,
            }
    return out, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="verify instead of writing")
    args = ap.parse_args(argv)
    data, problems = build()
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    full = sum(c["full_tokens"] for c in data.values())
    small = sum(c["card_tokens"] for c in data.values())
    for code, c in data.items():
        print(f"  {code:<30} {c['topics']:>3} topics  {c['card_tokens']:>5} / {c['full_tokens']:>6} tok")
    print(f"{len(data)} chapters: cards {small} tok vs full text {full} tok ({small / full:.0%})")
    for p in problems:
        print("PROBLEM", p)
    if args.check:
        stale = not CARDS_FILE.exists() or CARDS_FILE.read_text() != text
        print("STALE: run python -m scripts.build_section_cards" if stale else "up to date")
        return 1 if problems or stale else 0
    CARDS_FILE.write_text(text)
    print(f"wrote {CARDS_FILE}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
