"""Phase 2C-2D: clean subtopic nodes and one family per major topic. The family table the
map and place steps read, and the two dry-run-first scripts that put existing rows right.

The scripts are run against the shared test database, seeded here with the real book map
import of the four Social Science books plus the reading-order nodes the PDF ingest left
behind. No paid API is called."""

from __future__ import annotations

import json
import types
import uuid

import pytest
from sqlalchemy import select

from app.config import get_settings


@pytest.fixture
def cap(monkeypatch):
    monkeypatch.setattr(get_settings(), "topic_depth_cap", True)
    monkeypatch.setattr(get_settings(), "book_map_only_subtopics", True)


def _row(code, sections):
    return types.SimpleNamespace(code=code, from_sections=sections)


# --- the family table ----------------------------------------------------------------------


def test_sections_are_a_union_over_rows_with_the_flag_on():
    from app.mapping.family_sections import build

    rows = [_row("X.POL.CF.FUNCTIONS", ["1.2"]), _row("X.POL.CF.FUNCTIONS", ["1.3"])]
    assert build(rows, union=True).sections_of["X.POL.CF.FUNCTIONS"] == {"1.2", "1.3"}
    assert build(rows, union=False).sections_of["X.POL.CF.FUNCTIONS"] == {"1.3"}, "last wins, as before"


def test_under_the_cap_deep_and_box_families_are_marked_and_major_ones_claim_their_topic(cap):
    from app.mapping.family_sections import build

    chapter = "X.GEO.MINERALSENERGY"
    rows = [
        _row("X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY", ["4.1"]),
        _row("X.GEO.CF.COAL", ["4.1.1"]),
        _row("X.GEO.CF.PETROLEUM", ["4.1.2"]),
        _row("X.GEO.CF.RAT_HOLE_MINING", ["2.1"]),
        _row("X.GEO.CF.MODE_OCCURRENCE_MINERALS", ["2"]),
        _row("X.GEO.CF.MINERALSENERGY_INTRODUCTION", []),
    ]
    table = build(rows, union=True, chapter_code_of={r.code: chapter for r in rows})
    assert table.deep == {"X.GEO.CF.COAL", "X.GEO.CF.PETROLEUM", "X.GEO.CF.RAT_HOLE_MINING"}
    assert table.sections_of["X.GEO.CF.COAL"] == {"4.1"}
    assert table.sections_of["X.GEO.CF.RAT_HOLE_MINING"] == {"2"}
    assert table.sections_of["X.GEO.CF.MINERALSENERGY_INTRODUCTION"] == {"0"}
    assert all(s.count(".") <= 1 for v in table.sections_of.values() for s in v)


def test_a_new_placement_never_picks_a_deep_family(cap):
    from app.mapping.family import choose_family
    from app.mapping.family_sections import build

    chapter = "X.GEO.MINERALSENERGY"
    codes = ["X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY", "X.GEO.CF.COAL", "X.GEO.CF.PETROLEUM",
             "X.GEO.CF.NATURAL_GAS", "X.GEO.CF.ELECTRICITY"]
    rows = [_row(codes[0], ["4.1"])] + [
        _row(c, [s]) for c, s in zip(codes[1:], ["4.1.1", "4.1.2", "4.1.3", "4.1.4"], strict=True)
    ]
    table = build(rows, union=True, chapter_code_of={c: chapter for c in codes})
    families = [types.SimpleNamespace(code=c, label=c.rsplit(".", 1)[-1].title()) for c in codes]
    choice = choose_family(
        table.candidates(families), table.sections_of, "4.1", "Minerals and Energy Resources",
        exact_sections_of=table.exact_of,
    )
    assert choice.family.code == "X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY"
    assert choice.unsettled is None, "one family per major topic: nothing to settle"
    # even when every candidate is offered, the exact claim wins over the collapsed ones
    choice = choose_family(families, table.sections_of, "4.1", "Minerals and Energy Resources",
                           exact_sections_of=table.exact_of)
    assert choice.family.code == "X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY"


def test_candidates_never_empties_a_chapter_of_families(cap):
    from app.mapping.family_sections import FamilySections

    table = FamilySections(deep={"A"})
    families = [types.SimpleNamespace(code="A", label="a")]
    assert table.candidates(families) == families


# --- topic_node under book_map_only_subtopics --------------------------------------------


def test_an_existing_node_is_never_relabelled_for_a_book_map_subject(school, monkeypatch):
    from app.curriculum import X_POLITICAL_SCIENCE
    from app.curriculum.apply import apply as apply_curriculum
    from app.db import SessionLocal
    from app.mapping.topic_node import topic_node
    from app.models import TaxonomyNode

    db = SessionLocal()
    apply_curriculum(db, X_POLITICAL_SCIENCE)
    chapter = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.POL.OUTCOMES"))
    code = "X.POL.OUTCOMES.S6"
    node = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == code))
    if node is None:
        node = TaxonomyNode(kind="subtopic", code=code, label="Dignity", parent_id=chapter.id,
                            path=code, curriculum_version=chapter.curriculum_version)
        db.add(node)
        db.flush()
    node.label = "Dignity"
    monkeypatch.setattr(get_settings(), "book_map_only_subtopics", True)
    assert topic_node(db, chapter, "6", "6 Dignity and freedom of the citizens").label == "Dignity"
    monkeypatch.setattr(get_settings(), "book_map_only_subtopics", False)
    assert topic_node(db, chapter, "6", "6 Dignity and freedom of the citizens").label == (
        "6 Dignity and freedom of the citizens")
    db.rollback()
    db.close()


# --- the two scripts -----------------------------------------------------------------------


@pytest.fixture
def book_maps(school):
    """The four Social Science book maps imported, plus nodes the PDF ingest left."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        return _seed_book_maps(db, school)
    finally:
        db.rollback()
        db.close()


def _seed_book_maps(db, school):
    from app.curriculum import X_ECONOMICS, X_GEOGRAPHY, X_HISTORY, X_POLITICAL_SCIENCE
    from app.curriculum.apply import apply as apply_curriculum
    from app.models import Assessment, Question, QuestionSkill, TaxonomyNode
    from app.taxonomy.variants import variant_hash
    from scripts import import_book_map

    for c in (X_HISTORY, X_GEOGRAPHY, X_POLITICAL_SCIENCE, X_ECONOMICS):
        apply_curriculum(db, c)
    db.commit()
    if db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.POL.CF.FUNCTIONS")) is None:
        for subject in ("X.HIST", "X.GEO", "X.POL", "X.ECO"):    # never Science: other
            rel = import_book_map.SUBJECT_FILES[subject]          # tests need it absent
            path = import_book_map.REFERENCE_DIR / rel
            import_book_map._apply_subject(db, subject, import_book_map._plan_subject(db, subject, path))
        db.commit()

    nodes = {n.code: n for n in db.scalars(select(TaxonomyNode))}
    parties = nodes["X.POL.PARTIES"]
    minerals = nodes["X.GEO.MINERALSENERGY"]
    tag = uuid.uuid4().hex[:6]
    made = {}
    for chapter, code, label in [
        (parties, "X.POL.PARTIES.S4", "Functions"),          # reading order: 1.2 in the map
        (parties, "X.POL.PARTIES.S7", "Popular"),            # a box title, no unit
        (minerals, "X.GEO.MINERALSENERGY.S4_1_2", "4.1.2 Petroleum"),
        (minerals, "X.GEO.MINERALSENERGY.S4_1_4", "4.1.4 Electricity"),
        (minerals, "X.GEO.MINERALSENERGY.S0", "0 Introduction"),     # before the title
        (minerals, "X.GEO.MINERALSENERGY.S2_1", "2.1 Rat-Hole Mining"),
    ]:
        node = nodes.get(code)
        if node is None:
            node = TaxonomyNode(kind="subtopic", code=code, label=label, parent_id=chapter.id,
                                path=code, curriculum_version=chapter.curriculum_version)
            db.add(node)
            db.flush()
        node.label = label
        made[code] = node
    a = Assessment(school_id=school["school_id"], subject_code="X.SST", title=f"scripts {tag}")
    board = Assessment(school_id=school["school_id"], subject_code="X.SST",
                       title=f"board {tag}", paper_kind="board")
    db.add_all([a, board])
    db.flush()
    unit = nodes["X.GEO.U.WHOLE"]
    family = {f.code: f for f in db.scalars(select(TaxonomyNode).where(
        TaxonomyNode.kind == "concept_family"))}
    questions = {}
    for paper, addr, chapter, section, node_code, fam in [
        (a, "C/23//", parties, "4", "X.POL.PARTIES.S4", "X.POL.CF.FUNCTIONS"),
        (a, "B/19/19.3/", minerals, "4.1.2", "X.GEO.MINERALSENERGY.S4_1_2", "X.GEO.CF.PETROLEUM"),
        (board, "B/5//", minerals, "4.1.2", "X.GEO.MINERALSENERGY.S4_1_2", "X.GEO.CF.PETROLEUM"),
        # on a deep family, but the question's own section is a different major topic
        (a, "B/11//", minerals, "2.2.1", "X.GEO.MINERALSENERGY.S4_1_2", "X.GEO.CF.PETROLEUM"),
        # on a deep family, with a section that is no topic at all: the family decides
        (a, "B/12//", minerals, "9.9", "X.GEO.MINERALSENERGY.S4_1_2", "X.GEO.CF.COAL"),
        # the backup's case: a topic link on 4.1.4 Electricity, the question itself in 4.2.1
        (a, "B/19/19.7/", minerals, "4.2.1", "X.GEO.MINERALSENERGY.S4_1_4",
         "X.GEO.CF.ELECTRICITY"),
    ]:
        text = f"{tag} {addr} {paper.paper_kind}"
        q = Question(assessment_id=paper.id, address=addr, section=addr[0],
                     question_no=addr.split("/")[1], max_marks=1, stem_text=text,
                     board_unit_id=unit.id, chapter_id=chapter.id, curriculum_section=section,
                     concept_family_id=family[fam].id, concept_variant=text,
                     variant_hash=variant_hash(text))
        db.add(q)
        db.flush()
        db.add(QuestionSkill(question_id=q.id, node_id=made[node_code].id, source="retrieval",
                             weight=1.0))
        questions[(paper.paper_kind, addr)] = q.id
    db.commit()
    return questions


def test_clean_subtopics_dry_run_writes_nothing_and_names_each_class(book_maps, capsys):
    from app.db import SessionLocal
    from app.models import QuestionSkill, TaxonomyNode
    from scripts import clean_book_map_subtopics

    def snapshot():
        db = SessionLocal()
        try:
            return (
                sorted((n.code, n.label) for n in db.scalars(select(TaxonomyNode).where(
                    TaxonomyNode.kind == "subtopic"))),
                sorted((s.question_id, s.node_id) for s in db.scalars(select(QuestionSkill))),
            )
        finally:
            db.close()

    before = snapshot()
    assert clean_book_map_subtopics.main([]) == 0
    out = capsys.readouterr().out
    assert snapshot() == before
    assert "DRY RUN" in out
    assert "ORPHAN  X.POL.PARTIES.S4" in out and "-> 1.2" in out
    assert "DEEP    X.GEO.MINERALSENERGY.S4_1_2" in out
    assert "a box ('Rat-Hole Mining'), never a topic" in out
    links = [line.split() for line in out.splitlines() if line.strip().startswith("question_skill")]
    by_address = {(w[3], w[5]): w[-1] for w in links}
    # a DEEP node's topic links follow the question's own collapsed section first ...
    assert by_address[("B/19/19.7/", "4.2.1")] == "4.2"
    assert by_address[("B/11//", "2.2.1")] == "2.2"
    # ... and the node's own major topic only when that section is no topic
    assert by_address[("B/12//", "9.9")] == "4.1"
    relabel = next(line.split(None, 2) for line in out.splitlines()
                   if line.strip().startswith("RELABEL X.GEO.MINERALSENERGY.S0 "))
    assert relabel[2] == "'0 Introduction' -> '0 Introduction: Importance of Minerals'"


def test_clean_subtopics_refuses_apply_without_a_backup(book_maps):
    from scripts import clean_book_map_subtopics

    with pytest.raises(SystemExit) as stop:
        clean_book_map_subtopics.main(["--apply"])
    assert stop.value.code == 2


def test_clean_subtopics_applies_repoints_and_writes_an_undo_file(book_maps, tmp_path):
    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, TaxonomyNode
    from scripts import clean_book_map_subtopics

    undo = tmp_path / "undo.json"
    assert clean_book_map_subtopics.main(
        ["--apply", "--i-have-a-backup", "--undo-file", str(undo)]) == 0
    entries = json.loads(undo.read_text())["entries"]
    assert any(e["table"] == "question_skill" and e["op"] == "update" for e in entries)

    db = SessionLocal()
    try:
        def topic(qid):
            link = db.scalar(select(QuestionSkill).where(QuestionSkill.question_id == qid))
            return db.get(TaxonomyNode, link.node_id).code, db.get(Question, qid).curriculum_section

        assert topic(book_maps[("school", "C/23//")]) == ("X.POL.PARTIES.S1_2", "1.2")
        assert topic(book_maps[("school", "B/19/19.3/")]) == ("X.GEO.MINERALSENERGY.S4_1", "4.1")
        assert topic(book_maps[("school", "B/19/19.7/")])[0] == "X.GEO.MINERALSENERGY.S4_2"
        assert topic(book_maps[("school", "B/11//")])[0] == "X.GEO.MINERALSENERGY.S2_2"
        assert topic(book_maps[("school", "B/12//")])[0] == "X.GEO.MINERALSENERGY.S4_1"
        s4 = db.scalar(select(TaxonomyNode).where(TaxonomyNode.code == "X.POL.PARTIES.S4"))
        assert s4.label == "4 State parties", "the code is a major topic's: kept, relabelled"
        deep = db.scalar(select(TaxonomyNode).where(
            TaxonomyNode.code == "X.GEO.MINERALSENERGY.S4_1_2"))
        assert deep is not None, "DEEP nodes stay"
    finally:
        db.close()


def test_major_topic_families_dry_run_then_apply_leaves_board_papers_alone(book_maps, capsys, tmp_path):
    from app.db import SessionLocal
    from app.models import Question, TaxonomyNode
    from scripts import propose_major_topic_families

    assert propose_major_topic_families.main([]) == 0
    out = capsys.readouterr().out
    assert "REUSE   4.1   X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY" in out
    assert "deep    X.GEO.CF.PETROLEUM" in out
    assert "major topic ?" not in out
    conclusion = next(line for line in out.splitlines() if "deep    X.HIST.CF.CONCLUSION" in line)
    assert conclusion.endswith("-> chapter level (kept, unused)")
    assert "(board paper, untouched)" in out
    assert "B/11//       X.GEO.CF.PETROLEUM -> X.GEO.CF.FERROUS_MINERALS (section 2.2, by question section)" in out
    assert "B/12//       X.GEO.CF.COAL -> X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY (section 4.1, by deep family's topic)" in out
    minerals = out[out.index("X.GEO.MINERALSENERGY "):out.index("X.GEO.MANUFACTURING ")]
    offered = [line.split()[1] for line in minerals.splitlines()
               if line.strip().startswith(("REUSE", "CREATE"))]
    assert "4.1" in offered and "2.1" not in offered, "a box never gets a family of its own"

    with pytest.raises(SystemExit):
        propose_major_topic_families.main(["--apply"])
    undo = tmp_path / "undo.json"
    assert propose_major_topic_families.main(
        ["--apply", "--i-have-a-backup", "--undo-file", str(undo)]) == 0
    db = SessionLocal()
    try:
        def family(qid):
            return db.get(TaxonomyNode, db.get(Question, qid).concept_family_id).code

        assert family(book_maps[("school", "B/19/19.3/")]) == "X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY"
        # the question's own collapsed section wins over the deep family's topic ...
        assert family(book_maps[("school", "B/11//")]) == "X.GEO.CF.FERROUS_MINERALS"
        # ... and the deep family's topic stands in only when that section has none
        assert family(book_maps[("school", "B/12//")]) == "X.GEO.CF.CONVENTIONAL_SOURCES_ENERGY"
        assert family(book_maps[("board", "B/5//")]) == "X.GEO.CF.PETROLEUM"
        assert db.scalar(select(TaxonomyNode).where(
            TaxonomyNode.code == "X.GEO.CF.PETROLEUM")) is not None, "deep families stay"
    finally:
        db.close()
    assert json.loads(undo.read_text())["entries"]


def test_a_label_merely_inside_a_longer_heading_is_not_that_heading():
    """'Water Resources' (the chapter's own title, at reading-order S2) must not be read as
    section 2 'Multi-purpose River Projects and Integrated Water Resources Management'."""
    from scripts.clean_book_map_subtopics import _same

    assert not _same("Water Resources",
                     "2 Multi-purpose River Projects and Integrated Water Resources Management")
    assert not _same("PRODUCTION ACROSS COUNTRIES", "2 INTERLINKING PRODUCTION ACROSS COUNTRIES")
    assert _same("Post-war Settlement and the",
                 "4.1 Post-war Settlement and the Bretton Woods Institutions")
    assert _same("INCOME AND OTHER GOALS", "2 INCOME AND OTHER GOALS")


def test_an_applied_cleanup_is_reversed_exactly_by_its_undo_file(book_maps, tmp_path, capsys):
    from app.db import SessionLocal
    from app.models import Question, QuestionSkill, TaxonomyNode
    from scripts import apply_undo, clean_book_map_subtopics

    def snapshot():
        db = SessionLocal()
        try:
            return (
                sorted((n.code, n.label) for n in db.scalars(select(TaxonomyNode).where(
                    TaxonomyNode.kind == "subtopic"))),
                sorted((s.id, s.question_id, s.node_id, s.weight) for s in db.scalars(
                    select(QuestionSkill))),
                sorted((q.id, q.curriculum_section) for q in db.scalars(select(Question))),
            )
        finally:
            db.close()

    before = snapshot()
    undo = tmp_path / "undo.json"
    assert clean_book_map_subtopics.main(
        ["--apply", "--i-have-a-backup", "--undo-file", str(undo)]) == 0
    assert snapshot() != before, "the case under test: the run changed rows"
    capsys.readouterr()
    # dry run first: reports, writes nothing
    assert apply_undo.main([str(undo)]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "0 conflict(s)" in out
    with pytest.raises(SystemExit):
        apply_undo.main([str(undo), "--apply"])                      # no backup, no write
    assert apply_undo.main([str(undo), "--apply", "--i-have-a-backup",
                            "--undo-file", str(tmp_path / "undo2.json")]) == 0
    assert snapshot() == before
    # a second reversal finds every row already back: all conflicts, nothing written
    assert apply_undo.main([str(undo), "--apply", "--i-have-a-backup",
                            "--undo-file", str(tmp_path / "undo3.json")]) == 3
    assert snapshot() == before
