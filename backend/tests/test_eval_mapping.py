"""Phase 6: scripts/eval_mapping.py scores a run against the gold key, read-only."""

from __future__ import annotations

import json

import pytest

from scripts.eval_mapping import DEFAULT_GOLD, check_targets, main, score

GOLD = json.loads(DEFAULT_GOLD.read_text())


def _perfect() -> dict:
    """Every question placed exactly as the key says."""
    chapters = GOLD["section_chapters"]
    by_label = {s["label"]: s["chapter"] for s in chapters.values()}
    out = {}
    for address, key in GOLD["questions"].items():
        own = chapters[address.split("/", 1)[0]]
        code = by_label[key["chapter"]] if key.get("chapter") else own["chapter"]
        out[address] = {"chapter_code": code, "chapter": None, "section": key["exact"][0],
                        "secondaries": [], "needs_review": False, "review_reason": None}
    return {"assessment_id": "fixture", "questions": out, "spend": {}}


def test_the_gold_key_is_the_55_question_paper():
    assert len(GOLD["questions"]) == 55
    assert set(GOLD["section_chapters"]) == {"A", "B", "C", "D"}


def test_a_perfect_run_scores_55_of_55_and_passes_every_target():
    scored = score(GOLD, _perfect())
    t = scored["totals"]
    assert (t["chapter_correct"], t["topic_exact"], t["topic_wrong"], t["flagged"]) == (55, 55, 0, 0)
    assert all(ok for _, ok, _ in check_targets(GOLD, scored))
    assert scored["by_section"]["B"]["questions"] == 16


def test_each_kind_of_miss_is_scored_and_listed():
    run = _perfect()
    q = run["questions"]
    q["B/18//b"].update(chapter_code="X.GEO.MANUFACTURING", section="3.2")    # wrong chapter
    q["B/16//"].update(section="2")                                           # a partial
    q["A/3//"].update(section="7")                                            # wrong topic
    del q["D/30//"]                                                           # never placed
    scored = score(GOLD, run)
    t = scored["totals"]
    assert (t["chapter_correct"], t["topic_exact"], t["topic_partial"], t["topic_wrong"]) == (53, 51, 1, 3)
    assert scored["missing"] == ["D/30//"]
    verdicts = {r["address"]: r["topic"] for r in scored["rows"] if r["topic"] != "exact"}
    assert verdicts == {"B/18//b": "wrong", "B/16//": "partial", "A/3//": "wrong", "D/30//": "wrong"}


def test_predictions_are_collapsed_with_the_book_map_before_scoring():
    run = _perfect()
    q = run["questions"]
    q["B/12//"].update(section="4.1.1")     # Coal -> 4.1, the key's section
    q["B/16//"].update(section="2.1")       # the Rat-Hole Mining box -> its parent 2 (partial)
    scored = score(GOLD, run)
    rows = {r["address"]: r for r in scored["rows"]}
    assert rows["B/12//"]["collapsed"] == "4.1" and rows["B/12//"]["topic"] == "exact"
    assert rows["B/16//"]["collapsed"] == "2" and rows["B/16//"]["topic"] == "partial"
    # a section stored three levels deep is still reported: the cap should prevent it
    assert scored["three_level_sections"] == ["B/12//"]
    assert dict((n, ok) for n, ok, _ in check_targets(GOLD, scored))["no 3-level section"] is False


def test_flag_precision_recall_and_reasons():
    run = _perfect()
    q = run["questions"]
    q["B/18//b"].update(chapter_code="X.GEO.MANUFACTURING", needs_review=True,
                        review_reason="low_confidence")                       # caught
    q["A/3//"].update(needs_review=True, review_reason="topic_differs,family")  # false alarm
    q["C/21//"].update(section="1")                                           # missed
    q["D/31//"].update(needs_review=True, review_reason=None)                 # an old row
    scored = score(GOLD, run)
    t = scored["totals"]
    assert t["flagged"] == 3 and t["topic_wrong"] == 2
    assert t["flag_precision"] == round(1 / 3, 3) and t["flag_recall"] == 0.5
    assert t["flag_precision_inexact"] == round(1 / 3, 3) and t["flag_recall_inexact"] == 0.5
    assert scored["review_reasons"] == {
        "(none recorded)": 1, "family": 1, "low_confidence": 1, "topic_differs": 1}


def test_a_flagged_partial_counts_as_caught_when_partial_is_a_miss():
    run = _perfect()
    run["questions"]["B/16//"].update(section="2", needs_review=True, review_reason="topic_differs")
    t = score(GOLD, run)["totals"]
    assert t["flag_precision"] == 0.0 and t["flag_recall"] is None
    assert t["flag_precision_inexact"] == 1.0 and t["flag_recall_inexact"] == 1.0


def test_spend_is_read_from_the_jobs_and_divided_per_question():
    run = _perfect()
    run["spend"] = {
        "map": {"calls": 55, "input_tokens": 110000, "output_tokens": 55000,
                "cache_read_tokens": 0, "estimated_usd": 0.77},
        "place": {"calls": 165, "input_tokens": 82500, "output_tokens": 198000,
                  "cache_read_tokens": 1650000, "estimated_usd": 1.6},
    }
    s = score(GOLD, run)["spend"]
    assert s["total"]["calls"] == 220 and s["per_question"]["calls"] == 4.0
    assert s["per_question"]["estimated_usd"] == round(2.37 / 55, 4)


def test_export_then_rescore_offline_gives_the_same_scores(tmp_path, capsys):
    run = _perfect()
    run["questions"]["B/16//"].update(section="2", needs_review=True, review_reason="family")
    first = tmp_path / "run.json"
    first.write_text(json.dumps(run))
    exported = tmp_path / "exported.json"
    assert main(["--fixture", str(first), "--export", str(exported)]) == 0
    out1 = capsys.readouterr().out
    assert "READ-ONLY" in out1 and "TOPIC    exact 54, partial 1, wrong 0" in out1
    assert "B/16//       partial  section 2 -> 2" in out1
    assert "PASS  chapter: 55/55" in out1
    assert main(["--fixture", str(exported)]) == 0
    out2 = capsys.readouterr().out
    assert out2.split("\nMISSES")[0].split("\n", 2)[2] == out1.split("\nMISSES")[0].split("\n", 2)[2]
    saved = json.loads(exported.read_text())
    assert saved["scores"]["totals"]["topic_partial"] == 1 and len(saved["rows"]) == 55


def test_a_stored_paper_is_read_and_scored_without_writing(client, school, book, tmp_path, capsys):
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import PlacementJob, QuestionPlacement, QuestionSkill
    from tests.test_topic_column import _mapped, _question

    aid, qid = _question(client, school)
    db = SessionLocal()
    try:
        _mapped(db, qid, "13.3", "X.MATH.STATS.S13_3")
        db.add(QuestionPlacement(question_id=qid, confidence=0.6, needs_review=True,
                                 review_reason="low_confidence"))
        db.add(PlacementJob(school_id=school["school_id"], assessment_id=aid, kind="place",
                            status="succeeded", result={"spend": {
                                "calls": 3, "input_tokens": 900, "output_tokens": 1500,
                                "cache_read_tokens": 30000, "estimated_usd": 0.03}}))
        db.commit()
        counts = lambda: tuple(db.scalar(select(func.count()).select_from(m))  # noqa: E731
                               for m in (QuestionPlacement, QuestionSkill, PlacementJob))
        before = counts()
    finally:
        db.close()
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps({
        "paper": "tiny", "section_chapters": {"A": {"chapter": "X.MATH.STATS", "label": "Statistics"}},
        "questions": {"A/1//": {"exact": ["13.3"]}}, "targets": {"chapter_correct": 1},
    }))
    assert main(["--assessment", aid, "--gold", str(gold)]) == 0
    out = capsys.readouterr().out
    assert "CHAPTER  1/1" in out and "TOPIC    exact 1, partial 0, wrong 0" in out
    assert "REASONS  low_confidence 1" in out
    assert "SPEND    3 calls" in out and "per question 3.0 calls" in out
    db = SessionLocal()
    try:
        assert counts() == before
    finally:
        db.close()


@pytest.mark.parametrize("argv", [[], ["--assessment", "x", "--fixture", "y"]])
def test_exactly_one_source_is_required(argv):
    with pytest.raises(SystemExit):
        main(argv)


def test_collapse_section_takes_an_explicit_depth_whatever_the_settings():
    from app.curriculum.depth import collapse_section

    assert collapse_section(None, "4.1.2", chapter_code="X.GEO.MINERALSENERGY", max_depth=2) == "4.1"
    assert collapse_section("X.MATH", "13.2.1", max_depth=2) == "13.2"
    assert collapse_section("X.MATH", "13.2.1") == "13.2.1", "without it, the settings decide"
