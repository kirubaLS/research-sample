"""Score a paper's mapping against a gold key: chapter, major topic, and the review flags.

READ-ONLY. It reads one of:

* ``--assessment <id>``: the paper as stored. Each question's chapter and
  ``curriculum_section``, its secondary topics, its latest placement row (``needs_review``,
  ``review_reason``), and the spend reported by the latest succeeded map and classify
  jobs. On Postgres the session is opened READ ONLY.
* ``--fixture <file>``: predictions saved earlier with ``--export``, or written by hand in
  the same shape. Nothing is read from a database.

Every predicted section is collapsed to the gold key's two levels with ``collapse_section``
(the book map decides what a box or a deeper unit belongs to), whatever the settings are.
A topic is **exact** when the collapsed section is in the key's ``exact`` list, **partial**
when it is in ``partial``, otherwise **wrong**; a question in the wrong chapter is wrong
on both. Reported:

* totals and the same per paper section (A, B, C, ...);
* flags: how many rows are flagged, precision (flagged and wrong / flagged), recall
  (flagged and wrong / wrong), and the ``review_reason`` counts;
* sections stored deeper than two levels (there should be none with the cap on);
* model calls, tokens and estimated cost from the jobs' own spend, per question;
* every miss, one line each;
* the gold key's targets, each marked PASS or FAIL.

``--export <file>`` writes the predictions (the ``--fixture`` shape) and the scores as
JSON, so a run can be re-scored offline after the database is gone.

    python -m scripts.eval_mapping --assessment <id>
    python -m scripts.eval_mapping --assessment <id> --export run.json
    python -m scripts.eval_mapping --fixture run.json

Run it against a staging copy of the database, never production.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

DEFAULT_GOLD = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sst_gold" / "unit_test_2026_09.json"
)
#: the gold key's depth: "4.1", never "4.1.1"
GOLD_DEPTH = 2


# --- reading ------------------------------------------------------------------------------


def predictions_from_db(db, assessment_id: str) -> dict:
    """The fixture shape, from the stored paper."""
    from sqlalchemy import select

    from app.mapping.topic_node import primary_order, section_number
    from app.models import PlacementJob, Question, QuestionPlacement, QuestionSkill, TaxonomyNode

    questions = list(db.scalars(select(Question).where(Question.assessment_id == assessment_id)))
    ids = [q.id for q in questions]
    nodes = {n.id: n for n in db.scalars(select(TaxonomyNode).where(TaxonomyNode.id.in_(
        {q.chapter_id for q in questions if q.chapter_id} or {""})))}
    latest: dict[str, QuestionPlacement] = {}
    for row in db.scalars(select(QuestionPlacement).where(
        QuestionPlacement.question_id.in_(ids or [""]),
    ).order_by(QuestionPlacement.created_at, QuestionPlacement.id)):
        latest[row.question_id] = row
    links: dict[str, list] = {}
    for link in db.scalars(select(QuestionSkill).where(QuestionSkill.question_id.in_(ids or [""]))):
        links.setdefault(link.question_id, []).append(link)
    out: dict[str, dict] = {}
    for q in questions:
        chapter = nodes.get(q.chapter_id) if q.chapter_id else None
        secondaries = []
        for link in sorted(links.get(q.id, []), key=primary_order)[1:]:
            node = db.get(TaxonomyNode, link.node_id)
            sec = section_number(node.code) if node is not None else None
            if sec:
                secondaries.append(sec)
        row = latest.get(q.id)
        out[q.address] = {
            "chapter_code": chapter.code if chapter else None,
            "chapter": chapter.label if chapter else None,
            "section": q.curriculum_section,
            "secondaries": secondaries,
            "needs_review": bool(row.needs_review) if row is not None else False,
            "review_reason": row.review_reason if row is not None else None,
        }
    spend = {}
    for kind in ("map", "place"):
        job = db.scalars(select(PlacementJob).where(
            PlacementJob.assessment_id == assessment_id, PlacementJob.kind == kind,
            PlacementJob.status == "succeeded",
        ).order_by(PlacementJob.created_at.desc())).first()
        if job is not None and isinstance(job.result, dict) and job.result.get("spend"):
            spend[kind] = job.result["spend"]
    return {"assessment_id": assessment_id, "questions": out, "spend": spend}


# --- scoring ------------------------------------------------------------------------------


def _gold_chapter(gold: dict, address: str, key: dict) -> tuple[str | None, str | None]:
    """(chapter code, label) the key expects: the question's own override, else its
    paper section's chapter."""
    by_section = gold.get("section_chapters", {}).get(address.split("/", 1)[0], {})
    if key.get("chapter"):
        label = key["chapter"]
        code = next((s["chapter"] for s in gold.get("section_chapters", {}).values()
                     if s.get("label") == label), None)
        return code, label
    return by_section.get("chapter"), by_section.get("label")


def _depth(section: str | None) -> int:
    return len(section.split(".")) if section else 0


def score(gold: dict, predictions: dict) -> dict:
    """Per-question verdicts and every total the report prints."""
    from app.curriculum.depth import collapse_section

    rows = []
    preds = predictions.get("questions", {})
    for address, key in gold["questions"].items():
        want_code, want_label = _gold_chapter(gold, address, key)
        p = preds.get(address)
        if p is None:
            rows.append({"address": address, "missing": True, "chapter_ok": False,
                         "topic": "wrong", "flagged": False, "reason": None,
                         "section": None, "collapsed": None, "deep": False,
                         "exact": key.get("exact", []), "partial": key.get("partial", []),
                         "chapter": None, "want_chapter": want_label})
            continue
        chapter_ok = (
            p.get("chapter_code") == want_code if p.get("chapter_code") and want_code
            else (p.get("chapter") or "").strip().lower() == (want_label or "").strip().lower()
        )
        collapsed = collapse_section(None, p.get("section"), chapter_code=p.get("chapter_code"),
                                     max_depth=GOLD_DEPTH)
        if not chapter_ok:
            topic = "wrong"
        elif collapsed in key.get("exact", []):
            topic = "exact"
        elif collapsed in key.get("partial", []):
            topic = "partial"
        else:
            topic = "wrong"
        rows.append({
            "address": address, "missing": False, "chapter_ok": chapter_ok, "topic": topic,
            "flagged": bool(p.get("needs_review")), "reason": p.get("review_reason"),
            "section": p.get("section"), "collapsed": collapsed,
            "deep": _depth(p.get("section")) > GOLD_DEPTH,
            "exact": key.get("exact", []), "partial": key.get("partial", []),
            "chapter": p.get("chapter"), "want_chapter": want_label,
            "secondaries": p.get("secondaries", []),
        })

    def totals(subset: list[dict]) -> dict:
        wrong = [r for r in subset if r["topic"] == "wrong"]
        flagged = [r for r in subset if r["flagged"]]
        caught = [r for r in flagged if r["topic"] == "wrong"]
        inexact = [r for r in subset if r["topic"] != "exact"]
        caught_inexact = [r for r in flagged if r["topic"] != "exact"]
        return {
            "questions": len(subset),
            "chapter_correct": sum(r["chapter_ok"] for r in subset),
            "topic_exact": sum(r["topic"] == "exact" for r in subset),
            "topic_partial": sum(r["topic"] == "partial" for r in subset),
            "topic_wrong": len(wrong),
            "flagged": len(flagged),
            "flag_precision": round(len(caught) / len(flagged), 3) if flagged else None,
            "flag_recall": round(len(caught) / len(wrong), 3) if wrong else None,
            #: the same with a partial counted as a miss a flag is right to catch
            "flag_precision_inexact": (
                round(len(caught_inexact) / len(flagged), 3) if flagged else None),
            "flag_recall_inexact": (
                round(len(caught_inexact) / len(inexact), 3) if inexact else None),
        }

    by_section = {}
    for letter in sorted({r["address"].split("/", 1)[0] for r in rows}):
        by_section[letter] = totals([r for r in rows if r["address"].startswith(letter + "/")])
    reasons: Counter = Counter()
    for r in rows:
        if r["flagged"]:
            for code in (r["reason"] or "(none recorded)").split(","):
                reasons[code] += 1
    return {
        "rows": rows,
        "totals": totals(rows),
        "by_section": by_section,
        "review_reasons": dict(sorted(reasons.items())),
        "three_level_sections": [r["address"] for r in rows if r["deep"]],
        "missing": [r["address"] for r in rows if r["missing"]],
        "spend": spend_per_question(predictions.get("spend") or {}, len(rows)),
    }


def spend_per_question(spend: dict, questions: int) -> dict:
    """The map and classify jobs' own reported spend, summed, and per question."""
    keys = ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
            "estimated_usd")
    total = {k: sum((s or {}).get(k, 0) or 0 for s in spend.values()) for k in keys}
    if not spend:
        return {"reported": False}
    per = {
        k: round(v / questions, 4 if k == "estimated_usd" else 1) for k, v in total.items()
    } if questions else {}
    return {"reported": True, "jobs": sorted(spend), "total": total, "per_question": per}


def check_targets(gold: dict, scored: dict) -> list[tuple[str, bool, str]]:
    """(target, passed, detail) for each target the key states."""
    t, tot = gold.get("targets", {}), scored["totals"]
    out = []
    if "chapter_correct" in t:
        out.append(("chapter", tot["chapter_correct"] >= t["chapter_correct"],
                    f"{tot['chapter_correct']}/{tot['questions']} (target {t['chapter_correct']})"))
    if "topic_exact_min" in t:
        out.append(("topic exact", tot["topic_exact"] >= t["topic_exact_min"],
                    f"{tot['topic_exact']} (target >= {t['topic_exact_min']})"))
    if "flagged_max" in t:
        out.append(("flags", tot["flagged"] <= t["flagged_max"],
                    f"{tot['flagged']} (target <= {t['flagged_max']}"
                    + (f"; expected {t['flagged_expected']}" if t.get("flagged_expected") else "")
                    + ")"))
    if "flag_precision_min" in t and tot["flag_precision"] is not None:
        out.append(("flag precision", tot["flag_precision"] >= t["flag_precision_min"],
                    f"{tot['flag_precision']} (target >= {t['flag_precision_min']})"))
    if "max_depth" in t:
        deep = scored["three_level_sections"]
        out.append(("no 3-level section", not deep, f"{len(deep)} deeper than {t['max_depth']}"))
    return out


# --- reporting ----------------------------------------------------------------------------


def report(gold: dict, predictions: dict, scored: dict) -> str:
    tot = scored["totals"]
    lines = [
        "READ-ONLY -- nothing will be written",
        f"gold: {gold.get('paper', '?')}   run: {predictions.get('assessment_id') or 'fixture'}",
        "",
        f"CHAPTER  {tot['chapter_correct']}/{tot['questions']}",
        f"TOPIC    exact {tot['topic_exact']}, partial {tot['topic_partial']}, "
        f"wrong {tot['topic_wrong']}",
        f"FLAGS    {tot['flagged']} flagged; precision {tot['flag_precision']}, "
        f"recall {tot['flag_recall']} (wrong only); counting partial as a miss: precision "
        f"{tot['flag_precision_inexact']}, recall {tot['flag_recall_inexact']}",
        "REASONS  " + (", ".join(f"{k} {v}" for k, v in scored["review_reasons"].items()) or "none"),
        f"DEPTH    {len(scored['three_level_sections'])} section(s) deeper than {GOLD_DEPTH} levels"
        + (f": {', '.join(scored['three_level_sections'])}" if scored["three_level_sections"] else ""),
    ]
    if scored["missing"]:
        lines.append(f"MISSING  {len(scored['missing'])}: {', '.join(scored['missing'])}")
    s = scored["spend"]
    if s.get("reported"):
        per, total = s["per_question"], s["total"]
        lines.append(
            f"SPEND    {total['calls']} calls, {total['input_tokens']} in / {total['output_tokens']} out"
            f" / {total['cache_read_tokens']} cache-read tokens, ~${total['estimated_usd']:.2f} "
            f"({' + '.join(s['jobs'])}); per question {per['calls']} calls, "
            f"{per['input_tokens']:.0f} in / {per['output_tokens']:.0f} out, ~${per['estimated_usd']:.4f}"
        )
    else:
        lines.append("SPEND    not reported (no succeeded map/classify job with a spend record)")
    lines += ["", "BY SECTION", f"  {'sec':<4} {'qs':>3} {'chapter':>8} {'exact':>6} {'partial':>8} "
              f"{'wrong':>6} {'flagged':>8}"]
    for letter, t in scored["by_section"].items():
        lines.append(f"  {letter:<4} {t['questions']:>3} {t['chapter_correct']:>8} {t['topic_exact']:>6} "
                     f"{t['topic_partial']:>8} {t['topic_wrong']:>6} {t['flagged']:>8}")
    misses = [r for r in scored["rows"] if r["topic"] != "exact"]
    lines += ["", f"MISSES ({len(misses)})"]
    for r in misses:
        where = (f"chapter {r['chapter']!r} (key {r['want_chapter']!r})" if not r["chapter_ok"]
                 else f"section {r['section']} -> {r['collapsed']}")
        lines.append(
            f"  {r['address']:<12} {r['topic']:<8} {where}; key exact {r['exact']}"
            + (f" partial {r['partial']}" if r["partial"] else "")
            + (f"; flagged [{r['reason'] or '-'}]" if r["flagged"] else "; not flagged")
        )
    targets = check_targets(gold, scored)
    if targets:
        lines += ["", "TARGETS"]
        lines += [f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}" for name, ok, detail in targets]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--assessment", help="score this stored paper (read-only)")
    source.add_argument("--fixture", help="score predictions saved with --export")
    parser.add_argument("--gold", default=str(DEFAULT_GOLD), help="the gold key (JSON)")
    parser.add_argument("--export", help="write predictions and scores to this JSON file")
    args = parser.parse_args(argv)

    gold = json.loads(Path(args.gold).read_text())
    if args.fixture:
        predictions = json.loads(Path(args.fixture).read_text())
    else:
        from sqlalchemy import text

        from app.db import SessionLocal

        db = SessionLocal()
        try:
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
            predictions = predictions_from_db(db, args.assessment)
        finally:
            db.rollback()
            db.close()
    scored = score(gold, predictions)
    print(report(gold, predictions, scored))
    if args.export:
        Path(args.export).write_text(json.dumps(
            {**predictions, "scores": {k: v for k, v in scored.items() if k != "rows"},
             "rows": scored["rows"]}, indent=1, ensure_ascii=False))
        print(f"\nexported to {args.export}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
