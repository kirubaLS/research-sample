"""Tier 0 chapter gate: shadow records, enforcement skips the judge, off changes nothing.
Every judge is a stub; no paid API is called."""

from __future__ import annotations

from types import SimpleNamespace

from app.classify.gate import chapter_gate, summarise
from app.classify.judge import Classification
from app.classify.pipeline import PassOptions, place_paper
from app.ingest.probe import LexicalIndex


class _Chunk:
    def __init__(self, cid, text, node):
        self.chunk_id = self.id = cid
        self.text = text
        self.reference = cid
        self.node_id = node
        self.bucket = "T"
        self.embedding = None
        self.section_number = None


NAMES = {"G1": "Minerals and Energy", "H1": "Print Culture"}


def _corpus():
    chunks = [
        _Chunk("g1a", "coal mines iron ore bauxite mineral deposits coal", "G1"),
        _Chunk("g1b", "mineral coal ferrous mines ore energy", "G1"),
        _Chunk("h1a", "printing press books readers pamphlets", "H1"),
    ]
    return chunks + [_Chunk(f"pad{i}", f"unrelated filler topic {i}", f"X{i}") for i in range(20)]


class _Judge:
    def __init__(self, chapter="Minerals and Energy"):
        self.chapter = chapter
        self.seen = 0

    def classify(self, question, evidence, *, scoped=False):
        self.seen += 1
        return Classification(
            chapter=self.chapter, curriculum_section=None, tier="R&U", skill_required="",
            reasoning="stub", evidence=[], confidence=0.9, alternative_chapter=None,
        )


def _run(judge, **options):
    # two readers, as in production, so ChapterVerdict.agreed can be true
    indexes = [LexicalIndex(_corpus()), LexicalIndex(_corpus())]
    return place_paper(
        [("q", "coal mines iron ore", 1.0)], indexes, judge,
        chapter_of=NAMES.get, unit_of=NAMES.get, section_of=lambda r: None,
        evidence_passages=4, evidence_chapters=1,
        options=PassOptions(**options),
    )


def _verdict(**kw):
    base = dict(node_id="G1", score=0.1, margin=0.08, agreed=True)
    return SimpleNamespace(**{**base, **kw})


def test_the_gate_passes_only_when_the_readers_agree_and_lead_clearly():
    assert chapter_gate(_verdict(), "Minerals", min_relative_margin=0.3).passed
    assert not chapter_gate(_verdict(agreed=False), "Minerals", min_relative_margin=0.3).passed
    narrow = chapter_gate(_verdict(margin=0.01), "Minerals", min_relative_margin=0.3)
    assert not narrow.passed and "narrow" in narrow.reason
    assert not chapter_gate(_verdict(node_id=None), None, min_relative_margin=0.3).passed


def test_shadow_asks_the_judge_and_records_whether_the_gate_would_have_agreed():
    judge, log = _Judge(), {}
    out = _run(judge, gate=True, gate_log=log)
    assert judge.seen == 1, "shadow mode never skips the judge"
    assert not out.questions[0].chapter_judge_skipped and not out.questions[0].chapter_gated
    entry = log["q"]
    assert entry["passed"] and entry["chapter"] == "Minerals and Energy"
    assert entry["judge_chapter"] == "Minerals and Energy" and not entry["enforced"]
    report = summarise(log)
    assert report["passed"] == 1 and report["agreed_with_judge"] == 1
    assert report["disagreed_with_judge"] == 0


def test_shadow_counts_a_disagreement():
    log = {}
    _run(_Judge("Print Culture"), gate=True, gate_log=log)
    assert summarise(log)["disagreed_with_judge"] == 1


def test_enforced_skips_the_judge_and_leaves_the_tier_to_the_topic_judge():
    judge, log = _Judge(), {}
    out = _run(judge, gate=True, gate_enforce=True, gate_log=log)
    q = out.questions[0]
    assert judge.seen == 0
    assert q.chapter == "Minerals and Energy" and q.chapter_judge_skipped
    assert q.chapter_gated and q.tier is None and 0.5 < q.confidence <= 0.9
    assert log["q"]["enforced"] and "judge_chapter" not in log["q"]


def test_a_failing_gate_still_asks_the_judge_when_enforced():
    judge = _Judge()
    _run(judge, gate=True, gate_enforce=True, gate_min_margin=10.0)
    assert judge.seen == 1


def test_off_is_the_original_pass():
    judge, log = _Judge(), {}
    _run(judge, gate_log=log)
    assert judge.seen == 1 and log == {}
