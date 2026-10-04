"""Prototype (read-only, offline): a compact "section card" index of a chapter.

No database, no network, no model call. For each chapter of the gold paper it builds one
card per major topic (heading, opening sentence, the section's rarest names and years) and
reports:

* tokens (chars / 4): the full chapter text, the card index, the card index plus the full
  text of the top-2 sections;
* findability: TF-IDF recall@1 / @3 of the gold section over the cards vs over the full
  section text;
* decisive-term coverage: of the question's distinctive terms that appear in its gold
  section's full text, the share the card also carries.

    python -m scripts.prototype_section_cards --pdf paper.pdf [--show-cards]
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from app.classify.topic import distinctive_terms
from app.curriculum.book_map import major_of
from scripts.import_book_map import REFERENCE_DIR, SUBJECT_FILES, _load_chapter, _text_chunks

GOLD = Path(__file__).resolve().parent.parent / "tests/fixtures/sst_gold/unit_test_2026_09.json"
_WORD = re.compile(r"[a-z][a-z'’-]{2,}|\d{4}")
_STOP = set("the and for are was were that this with from which their they have has had not but "
            "its into than then also such these those been being can may will would about "
            "when where who what why how all any each other more most one two".split())
_NAMES = re.compile(r"(?<![\w'])(?:[A-Z][\w'’-]+)(?:\s+(?:(?:of|the|and|for|in|on|to)\s+)?[A-Z][\w'’-]+)+")
_YEAR = re.compile(r"\b(1[4-9]\d\d|20\d\d)\b")
TERMS_PER_CARD = 8
FIRST_CHARS = 200


def tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def chapter_sections(chapter_code: str) -> dict[str, dict]:
    """major topic -> {"heading", "chunks": [text, ...]} for one chapter."""
    subject = ".".join(chapter_code.split(".")[:2])
    chapter = _load_chapter(REFERENCE_DIR / SUBJECT_FILES[subject], chapter_code)
    out: dict[str, dict] = {}
    for unit in chapter["units"]:
        top = major_of(chapter_code, unit.get("number"), 2)
        if top is None:
            continue
        slot = out.setdefault(top, {"heading": None, "chunks": []})
        if unit.get("number") == top or slot["heading"] is None:
            slot["heading"] = f"{top} {unit.get('title') or ''}".strip()
        slot["chunks"] += [text for _, _, text in _text_chunks(chapter_code, unit)]
    return out


def build_cards(sections: dict[str, dict]) -> dict[str, str]:
    full = {k: " ".join(v["chunks"]) for k, v in sections.items()}
    df: Counter = Counter()
    for text in full.values():
        df.update({t for t in _NAMES.findall(text)} | set(_YEAR.findall(text)))
    cards = {}
    for key, text in full.items():
        counts = Counter(_NAMES.findall(text) + _YEAR.findall(text))
        ranked = sorted(counts, key=lambda t: (df[t], -counts[t], t))[:TERMS_PER_CARD]
        first = (sections[key]["chunks"] or [""])[0][:FIRST_CHARS].rsplit(" ", 1)[0]
        cards[key] = f"{sections[key]['heading']}. {first}. Key: {'; '.join(ranked)}"
    return cards


def rank(query: str, docs: dict[str, str]) -> list[str]:
    toks = {k: Counter(words(v)) for k, v in docs.items()}
    n = len(docs)
    df = Counter(t for c in toks.values() for t in c)
    q = Counter(words(query))
    score = {}
    for k, c in toks.items():
        length = sum(c.values()) or 1
        score[k] = sum(qc * (c[t] / length) * math.log(1 + n / df[t]) for t, qc in q.items() if t in c)
    return sorted(docs, key=lambda k: (-score[k], k))


def stems_from(pdf: str) -> dict[str, str]:
    from app.extraction.paper import extract_paper

    """(section, question number) -> the stems of that question's rows joined; the gold
    key's sub-part addresses differ from what the text route reads, the question does not."""
    out: dict[str, str] = {}
    for q in extract_paper(pdf).questions:
        key = f"{q.section or ''}/{q.question_no}"
        out[key] = f"{out.get(key, '')} {q.stem_text or ''}".strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--show-cards", action="store_true")
    args = ap.parse_args(argv)
    gold = json.loads(GOLD.read_text())
    stems = stems_from(args.pdf)
    built: dict[str, tuple[dict, dict, dict]] = {}
    for sec, info in gold["section_chapters"].items():
        code = info["chapter"]
        sections = chapter_sections(code)
        cards = build_cards(sections)
        full = {k: " ".join(v["chunks"]) for k, v in sections.items()}
        built[sec] = (sections, cards, full)
        t_full, t_cards = sum(tokens(t) for t in full.values()), sum(tokens(t) for t in cards.values())
        print(f"{code:<26} sections {len(cards):>2}  full {t_full:>6} tok  cards {t_cards:>5} tok "
              f"({t_cards / t_full:.0%})")
        if args.show_cards:
            for k, c in cards.items():
                print(f"    [{k}] {c}")
    hits = Counter()
    n = covered = decisive = unread = 0
    sizes = []
    misses = []
    for address, key in gold["questions"].items():
        stem = stems.get("/".join(address.split("/")[:2]))
        if not stem or key.get("chapter"):
            unread += 1
            continue
        sections, cards, full = built[address.split("/", 1)[0]]
        gold_sections = {major_of(gold["section_chapters"][address.split("/", 1)[0]]["chapter"], s, 2)
                         for s in key["exact"]}
        gold_sections &= set(cards)
        if not gold_sections:
            continue
        n += 1
        by_card, by_full = rank(stem, cards), rank(stem, full)
        for name, order in (("card", by_card), ("full", by_full)):
            for k in (1, 3):
                hits[f"{name}@{k}"] += bool(gold_sections & set(order[:k]))
        sizes.append(tokens(" ".join(cards.values())) + sum(tokens(full[k]) for k in by_card[:2]))
        wanted = [t for t in distinctive_terms(stem)
                  if any(t.lower() in full[g].lower() for g in gold_sections)]
        if wanted:
            decisive += len(wanted)
            got = [t for t in wanted if any(t.lower() in cards[g].lower() for g in gold_sections)]
            covered += len(got)
            if len(got) < len(wanted):
                misses.append((address, sorted(gold_sections), [t for t in wanted if t not in got]))
    print(f"\nquestions scored {n} (not read from the PDF or off-chapter: {unread})")
    for k in (1, 3):
        print(f"recall@{k}   cards {hits[f'card@{k}']}/{n}   full text {hits[f'full@{k}']}/{n}")
    print(f"decisive terms on the card: {covered}/{decisive}")
    print(f"avg tokens, cards + top-2 full sections: {sum(sizes) // max(len(sizes), 1)}")
    for address, gs, terms in misses:
        print(f"  no card coverage {address:<10} {','.join(gs):<6} {terms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
