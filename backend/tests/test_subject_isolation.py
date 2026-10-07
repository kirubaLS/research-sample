"""Mapping logic is kept per subject: the flags that change how a paper is mapped act only
for the subjects in ``mapping_v2_subjects``. Any other subject runs the original path with
every one of them off, so reworking one subject can never move another's finished mapping."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from app.mapping.subject_scope import SUBJECT_FLAGS, applies, for_subject


def _everything_on(**extra) -> Settings:
    flags = {name: True for name in SUBJECT_FLAGS}
    return Settings(**{**flags, **extra})


def test_every_flag_in_the_list_is_a_real_boolean_setting():
    s = Settings()
    for name in SUBJECT_FLAGS:
        assert isinstance(getattr(s, name), bool), name


@pytest.mark.parametrize(
    "code", ["X.MATH", "X.ENG", "X.MATH.REAL", "X.ENG.FF", "X.HIN.KR", "X.TAM", None, ""],
)
def test_a_subject_outside_the_list_sees_every_mapping_flag_off(code):
    s = _everything_on()
    seen = for_subject(s, code)
    assert not applies(code, s)
    assert [n for n in SUBJECT_FLAGS if getattr(seen, n)] == []
    assert all(getattr(s, n) for n in SUBJECT_FLAGS), "the global settings object is never changed"


@pytest.mark.parametrize("code", [
    "X.SST", "X.HIST", "X.GEO", "X.POL", "X.ECO", "X.SCI",
    "X.GEO.MINERALSENERGY", "X.HIST.PRINTCULTURE", "X.ECO.GLOBALISATION", "X.SCI.CARBON",
])
def test_the_listed_subjects_keep_every_flag(code):
    s = _everything_on()
    assert applies(code, s)
    assert for_subject(s, code) is s


def test_a_prefix_is_not_a_match():
    s = _everything_on(mapping_v2_subjects=["X.SCI"])
    assert applies("X.SCI.CARBON", s)
    assert not applies("X.SCIENCEX", s) and not applies("X.SC", s)


def test_the_default_list_is_social_science_and_science_and_nothing_else():
    s = _everything_on()
    assert applies("X.SCI.CARBON", s) and applies("X.GEO.WATER", s)
    assert not applies("X.MATH.REAL", s) and not applies("X.ENG", s)
    assert not applies("X.MATH", Settings(mapping_v2_subjects=["X.SST", "X.HIST"]))
    assert not applies("X.SCI", Settings(mapping_v2_subjects=["X.SST", "X.HIST"])), \
        "taking Science off the list is one environment setting"


def test_the_depth_cap_follows_the_subject_list(monkeypatch):
    from app.curriculum.depth import max_depth_for

    live = get_settings()
    monkeypatch.setattr(live, "topic_depth_cap", True)
    monkeypatch.setattr(live, "topic_max_depth_by_subject", {"X.GEO": 2, "X.SCI": 3, "X.MATH": 3})
    assert max_depth_for("X.GEO.MINERALSENERGY") == 2
    assert max_depth_for("X.SCI.CARBON") == 3
    assert max_depth_for("X.MATH.REAL") is None, "listed for a depth, but not in mapping_v2_subjects"
    monkeypatch.setattr(live, "mapping_v2_subjects", ["X.GEO"])
    assert max_depth_for("X.SCI.CARBON") is None
    assert max_depth_for("X.GEO.WATER") == 2


def test_the_major_topic_view_and_book_map_subtopics_follow_the_subject_list(monkeypatch):
    from types import SimpleNamespace

    from app.mapping.topic_node import _book_map_only, major_view

    live = get_settings()
    monkeypatch.setattr(live, "topic_depth_cap", True)
    monkeypatch.setattr(live, "topic_major_only_document", True)
    monkeypatch.setattr(live, "book_map_only_subtopics", True)
    geo = SimpleNamespace(code="X.GEO.MINERALSENERGY")
    sci = SimpleNamespace(code="X.SCI.CARBON")
    maths = SimpleNamespace(code="X.MATH.REAL")
    assert major_view(geo) == ("X.GEO.MINERALSENERGY", 2)
    assert major_view(sci) == ("X.SCI.CARBON", 2)
    assert major_view(maths) is None
    assert _book_map_only(geo) and _book_map_only(sci) and not _book_map_only(maths)


def test_a_maths_paper_never_reads_structure_or_review_rules(client, school, monkeypatch):
    live = get_settings()
    for name in SUBJECT_FLAGS:
        monkeypatch.setattr(live, name, True)
    assert not for_subject(live, "X.MATH").review_flag_rule
    assert for_subject(live, "X.SST").review_flag_rule


def test_section_cards_exist_only_for_the_subjects_on_the_list():
    from app.classify.section_cards import load_cards

    assert load_cards("X.GEO.MINERALSENERGY") and load_cards("X.HIST.PRINTCULTURE")
    assert load_cards("X.SCI.CARBON") and load_cards("X.SCI.LIFEPROC")
    assert load_cards("X.MATH.REAL") is None and load_cards("X.ENG.FF") is None


def test_a_subject_outside_the_list_reads_the_topic_prompts_it_always_read():
    from app.classify import topic
    from app.classify.legacy_prompts import LEGACY_DOCUMENT_SYSTEM, LEGACY_SYSTEM
    from app.classify.topic import TopicJudge

    legacy = TopicJudge("k", "m", legacy_prompts=True, major_only=True)
    live = TopicJudge("k", "m", major_only=True)
    document = legacy._document_system("Chapter", {"1": "One"}, "text")
    assert document[0]["text"] == LEGACY_DOCUMENT_SYSTEM, "legacy wins even when major_only is on"
    assert legacy._pick_system() == LEGACY_SYSTEM
    assert live._document_system("Chapter", {"1": "One"}, "text")[0]["text"] == topic._DOCUMENT_SYSTEM_MAJOR
    assert live._pick_system() == topic._SYSTEM_MAJOR


def test_the_legacy_prompts_are_the_ones_from_before_the_rework():
    """Pinned: these two are never edited. They keep the examples the live prompts dropped."""
    from app.classify.legacy_prompts import LEGACY_DOCUMENT_SYSTEM, LEGACY_SYSTEM

    assert "Index of Prohibited Books" in LEGACY_SYSTEM
    assert "nuclear plant" in LEGACY_DOCUMENT_SYSTEM
    assert (len(LEGACY_SYSTEM), len(LEGACY_DOCUMENT_SYSTEM)) == (1805, 2033)
