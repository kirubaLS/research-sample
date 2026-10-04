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
from collections import Counter, defaultdict
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
_MID = re.compile(r"(?<=[)\-–—,;] )([A-Z][a-z][\w'’-]{3,})")
_YEAR = re.compile(r"\b(1[4-9]\d\d|20\d\d)\b")
TERMS_PER_CARD = 18
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


def _candidates(sections: dict[str, dict], key: str) -> Counter:
    """Everything on a section that could decide a question: names, years, mid-sentence
    capitalised words and rare lowercase content words. Glossary terms and box titles are
    added by the caller from the book map's own structure."""
    text = " ".join(sections[key]["chunks"])
    counts = Counter(_NAMES.findall(text) + _YEAR.findall(text))
    counts.update(m for m in _MID.findall(text))
    counts.update(w for w in words(text) if len(w) >= 5)
    return counts


def build_cards(sections: dict[str, dict], extras: dict[str, list[str]] | None = None,
                n_terms: int = TERMS_PER_CARD) -> dict[str, str]:
    extras = extras or {}
    cand = {k: _candidates(sections, k) for k in sections}
    df: Counter = Counter()
    for c in cand.values():
        df.update(c.keys())
    cards = {}
    for key, counts in cand.items():
        picked = list(dict.fromkeys(extras.get(key, [])))[:6]
        seen = {p.lower() for p in picked}
        for t in sorted(counts, key=lambda t: (df[t], -counts[t], t)):
            if len(picked) >= n_terms:
                break
            if df[t] <= 2 and t.lower() not in seen:
                picked.append(t)
                seen.add(t.lower())
        first = (sections[key]["chunks"] or [""])[0][:FIRST_CHARS].rsplit(" ", 1)[0]
        cards[key] = f"{sections[key]['heading']}. {first}. Key: {'; '.join(picked)}"
    return cards


def structural_terms(chapter_code: str) -> dict[str, list[str]]:
    """Glossary terms and box/source titles per major topic: the book's own vocabulary."""
    subject = ".".join(chapter_code.split(".")[:2])
    chapter = _load_chapter(REFERENCE_DIR / SUBJECT_FILES[subject], chapter_code)
    out: dict[str, list[str]] = {}
    for unit in chapter["units"]:
        top = major_of(chapter_code, unit.get("number"), 2)
        if top is None:
            continue
        got = out.setdefault(top, [])
        got += [t["term"] for t in unit.get("terms", []) if t.get("term")]
        got += [b["title"] for b in unit.get("boxes", []) + unit.get("sources", []) if b.get("title")]
    return out


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


def bm25_sections(query: str, sections: dict[str, dict], k1: float = 1.4, b: float = 0.75) -> list[str]:
    """Stage 1: BM25 over every CHUNK of the chapter, then each section scores its best
    chunk plus 0.3 x its next two. (Whole-section TF-IDF and fusing with the cards both
    measured worse on the gold paper.)"""
    chunks = [(k, Counter(words(t))) for k, v in sections.items() for t in v["chunks"]]
    n = len(chunks)
    avg = sum(sum(c.values()) for _, c in chunks) / n
    df = Counter(t for _, c in chunks for t in c)
    q = set(words(query))
    per: dict[str, list[float]] = defaultdict(list)
    for k, c in chunks:
        length = sum(c.values())
        per[k].append(sum(
            math.log(1 + (n - df[t] + .5) / (df[t] + .5)) * c[t] * (k1 + 1)
            / (c[t] + k1 * (1 - b + b * length / avg))
            for t in q if t in c))
    score = {k: (v := sorted(vs, reverse=True))[0] + 0.3 * sum(v[1:3]) for k, vs in per.items()}
    return sorted(score, key=lambda k: (-score[k], k))


def fuse(*orders: list[str]) -> list[str]:
    """Reciprocal-rank fusion of several rankings of the same sections."""
    score: Counter = Counter()
    for order in orders:
        for i, k in enumerate(order):
            score[k] += 1 / (10 + i)
    return sorted(score, key=lambda k: (-score[k], k))


def stems_from(pdf: str) -> dict[str, str]:
    from app.extraction.paper import extract_paper

    """(section, question number) -> the stems of that question's rows joined; the gold
    key's sub-part addresses differ from what the text route reads, the question does not."""
    out: dict[str, str] = {}
    for q in extract_paper(pdf).questions:
        key = f"{q.section or ''}/{q.question_no}"
        out[key] = f"{out.get(key, '')} {q.stem_text or ''}".strip()
    return out


def write_all(path: Path) -> None:
    out, total_full, total_cards = {}, 0, 0
    for rel in SUBJECT_FILES.values():
        file = REFERENCE_DIR / rel
        if not file.exists():
            continue
        for chapter in json.loads(file.read_text()):
            code = chapter["code"]
            sections = chapter_sections(code)
            cards = build_cards(sections, structural_terms(code))
            full = sum(tokens(" ".join(v["chunks"])) for v in sections.values())
            small = sum(tokens(c) for c in cards.values())
            total_full, total_cards = total_full + full, total_cards + small
            out[code] = {"sections": len(cards), "full_tokens": full, "card_tokens": small, "cards": cards}
            print(f"  {code:<30} {len(cards):>3} cards  {small:>5} / {full:>6} tok")
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"ALL  {len(out)} chapters  cards {total_cards} tok vs full {total_full} tok "
          f"({total_cards / total_full:.0%}) -> {path}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--show-cards", action="store_true")
    ap.add_argument("--write-all", metavar="PATH",
                    help="also write the cards of EVERY chapter of every subject to this JSON file")
    args = ap.parse_args(argv)
    if args.write_all:
        write_all(Path(args.write_all))
    gold = json.loads(GOLD.read_text())
    stems = stems_from(args.pdf)
    built: dict[str, tuple[dict, dict, dict]] = {}
    for sec, info in gold["section_chapters"].items():
        code = info["chapter"]
        sections = chapter_sections(code)
        cards = build_cards(sections, structural_terms(code))
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
        by_mix = bm25_sections(stem, sections)
        for name, order in (("card", by_card), ("full", by_full), ("mix", by_mix)):
            for k in (1, 3, 5):
                hits[f"{name}@{k}"] += bool(gold_sections & set(order[:k]))
        sizes.append(sum(tokens(cards[k]) for k in by_mix[:5]) + sum(tokens(full[k]) for k in by_mix[:2]))
        wanted = [t for t in distinctive_terms(stem)
                  if any(t.lower() in full[g].lower() for g in gold_sections)]
        if wanted:
            decisive += len(wanted)
            got = [t for t in wanted if any(t.lower() in cards[g].lower() for g in gold_sections)]
            covered += len(got)
            if len(got) < len(wanted):
                misses.append((address, sorted(gold_sections), [t for t in wanted if t not in got]))
    print(f"\nquestions scored {n} (not read from the PDF or off-chapter: {unread})")
    for k in (1, 3, 5):
        print(f"recall@{k}   cards {hits[f'card@{k}']}/{n}   full text {hits[f'full@{k}']}/{n}"
              f"   bm25 {hits[f'mix@{k}']}/{n}")
    print(f"decisive terms on the card: {covered}/{decisive}")
    print(f"avg tokens, top-5 cards + top-2 full sections (bm25): {sum(sizes) // max(len(sizes), 1)}")
    for address, gs, terms in misses:
        print(f"  no card coverage {address:<10} {','.join(gs):<6} {terms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
