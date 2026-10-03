"""Phase 1.2: printed text -> Social Science subjects and chapters, with no model call."""

from __future__ import annotations

import json

import pytest

from app.curriculum.resolve import TITLE_THRESHOLD, normalise, resolve_text

SST = ["X.HIST", "X.GEO", "X.POL", "X.ECO"]
ALIASES = {
    "X.ECO.GLOBALISATION": ["Globalisation"],
    "X.GEO.MINERALSENERGY": ["Minerals"],
    "X.HIST.PRINTCULTURE": ["Print Culture"],
    "X.GEO.LIFELINES": ["Lifelines"],
}


def _chapters(text, **kw):
    return sorted(resolve_text(text, SST, ALIASES, **kw).chapters)


@pytest.mark.parametrize("text, subject, chapter", [
    ("Geography : Minerals and Energy Resources", "X.GEO", "X.GEO.MINERALSENERGY"),
    ("HISTORY - PRINT CULTURE AND THE MODERN WORLD", "X.HIST", "X.HIST.PRINTCULTURE"),
    ("Political Science (Political Parties)", "X.POL", "X.POL.PARTIES"),
    ("Democratic Politics: Federalism", "X.POL", "X.POL.FEDERALISM"),
    ("Civics -- Power Sharing", "X.POL", "X.POL.POWERSHARING"),
    ("Economics: Money & Credit", "X.ECO", "X.ECO.MONEYCREDIT"),
    ("Economics : Globalization and the Indian Economy", "X.ECO", "X.ECO.GLOBALISATION"),
    ("Geography: Minerals & Energy Resorces", "X.GEO", "X.GEO.MINERALSENERGY"),
])
def test_a_titled_section_resolves_to_its_subject_and_chapter(text, subject, chapter):
    out = resolve_text(text, SST, ALIASES)
    assert set(out.subjects) == {subject}
    assert set(out.chapters) == {chapter}


@pytest.mark.parametrize("text, chapter", [
    ("Globalisation", "X.ECO.GLOBALISATION"),
    ("Minerals", "X.GEO.MINERALSENERGY"),
    ("Print Culture", "X.HIST.PRINTCULTURE"),
    ("Lifelines", "X.GEO.LIFELINES"),
])
def test_a_short_name_resolves_only_through_its_alias(text, chapter):
    assert _chapters(text) == [chapter]
    assert resolve_text(text, SST).chapters == {}


def test_hindi_subject_words_resolve():
    assert set(resolve_text("खंड ख — भूगोल", SST).subjects) == {"X.GEO"}
    assert set(resolve_text("अर्थशास्त्र", SST).subjects) == {"X.ECO"}
    assert set(resolve_text("राजनीति विज्ञान", SST).subjects) == {"X.POL"}
    assert set(resolve_text("इतिहास / History", SST).subjects) == {"X.HIST"}


def test_a_syllabus_line_with_chapter_numbers_resolves_every_chapter_named():
    assert _chapters("History Ch 1-2, Geography Ch 1, 3") == [
        "X.GEO.RESOURCES", "X.GEO.WATER",
        "X.HIST.NATIONALISM_EUROPE", "X.HIST.NATIONALISM_INDIA",
    ]
    assert _chapters("Civics - Chapter II & IV") == ["X.POL.FEDERALISM", "X.POL.PARTIES"]
    assert _chapters("Economics Unit 2") == ["X.ECO.SECTORS"]


@pytest.mark.parametrize("text", [
    "Multiple Choice Questions",
    "SECTION A",
    "Case Based Questions",
    "Map Skill Based Question",
    "Ch 3",                 # a number with no book named: never guessed in a group paper
    "Print",                # one word of a title is below the threshold
    "Resources",            # three chapters share it; none is named
    "Chapter 9",            # out of range for every book
    "",
])
def test_unclear_text_resolves_to_nothing(text):
    out = resolve_text(text, SST, ALIASES)
    assert out.chapters == {}


def test_a_bare_chapter_number_needs_a_one_book_default():
    assert resolve_text("Ch 3", ["X.MATH"]).chapters == {}
    assert sorted(resolve_text("Ch 3", ["X.MATH"], default_subject="X.MATH").chapters) == [
        "X.MATH.LINEQ",
    ]


def test_a_subject_word_restricts_titles_to_its_own_book():
    """'Development' is an Economics chapter, and also inside Geography's 'Resources and
    Development'; the subject word decides, and a contained title never doubles up."""
    assert _chapters("Economics: Development") == ["X.ECO.DEVELOPMENT"]
    assert _chapters("Resources and Development") == ["X.GEO.RESOURCES"]


def test_a_subject_word_alone_names_the_subject_and_no_chapter():
    out = resolve_text("Geography", SST)
    assert set(out.subjects) == {"X.GEO"} and out.chapters == {}


def test_a_low_scoring_title_is_rejected_not_rounded_up():
    """Half of 'Minerals and Energy Resources' is below the threshold."""
    out = resolve_text("Energy", SST)
    assert out.chapters == {}
    out = resolve_text("Minerals and Energy Resources", SST, threshold=1.01)
    assert out.chapters == {}


def test_subjects_outside_the_group_are_never_resolved():
    assert resolve_text("Geography: Minerals and Energy Resources", ["X.HIST"]).empty


def test_normalise_reads_ampersand_and_punctuation_as_plain_words():
    assert normalise("Money & Credit!") == "money and credit"
    assert normalise("Power-sharing") == "power sharing"


# --- the alias seed script ---------------------------------------------------------------


@pytest.fixture
def sst_curricula(school):
    from app.curriculum import X_ECONOMICS, X_GEOGRAPHY, X_HISTORY, X_POLITICAL_SCIENCE
    from app.curriculum.apply import apply as apply_curriculum
    from app.db import SessionLocal

    db = SessionLocal()
    for curriculum in (X_HISTORY, X_GEOGRAPHY, X_POLITICAL_SCIENCE, X_ECONOMICS):
        apply_curriculum(db, curriculum)
    db.commit()
    db.close()


def _alias_count():
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import TaxonomyAlias

    db = SessionLocal()
    try:
        return db.scalar(select(func.count()).select_from(TaxonomyAlias))
    finally:
        db.close()


def test_the_seed_script_writes_nothing_without_apply(sst_curricula, capsys):
    from scripts import seed_sst_aliases

    before = _alias_count()
    assert seed_sst_aliases.main([]) == 0
    printed = capsys.readouterr().out
    assert "DRY RUN" in printed and "Globalisation" in printed
    assert _alias_count() == before


def test_the_seed_script_refuses_apply_without_a_backup(sst_curricula, capsys):
    from scripts import seed_sst_aliases

    before = _alias_count()
    with pytest.raises(SystemExit) as stop:
        seed_sst_aliases.main(["--apply"])
    assert stop.value.code == 2
    assert "pg_dump" in capsys.readouterr().err
    assert _alias_count() == before


def test_the_seed_script_applies_once_and_writes_an_undo_file(sst_curricula, tmp_path):
    from app.curriculum.resolve import load_chapter_aliases
    from app.db import SessionLocal
    from scripts import seed_sst_aliases

    undo = tmp_path / "undo.json"
    assert seed_sst_aliases.main(["--apply", "--i-have-a-backup", "--undo-file", str(undo)]) == 0
    entries = json.loads(undo.read_text())["entries"]
    assert entries and all(e["op"] == "insert" and e["table"] == "taxonomy_alias" for e in entries)
    # labels are never duplicated as aliases
    assert "Political Parties" not in {e["new"]["alias"] for e in entries}

    db = SessionLocal()
    aliases = load_chapter_aliases(db, SST)
    db.close()
    assert "Globalisation" in aliases["X.ECO.GLOBALISATION"]
    assert resolve_text("Globalisation", SST, aliases).chapter_codes() == {"X.ECO.GLOBALISATION"}

    # a second run finds everything already there
    count = _alias_count()
    assert seed_sst_aliases.main(["--apply", "--i-have-a-backup",
                                  "--undo-file", str(tmp_path / "u2.json")]) == 0
    assert _alias_count() == count


# --- spelling variants, cross-matches and the gold paper's headers -------------------------
# Resolved with the alias list the seed script installs, which is what production reads.

def _seeded():
    from scripts.seed_sst_aliases import SST_SHORT_NAMES

    return SST_SHORT_NAMES


@pytest.mark.parametrize("text, chapter", [
    ("Power Sharing", "X.POL.POWERSHARING"),
    ("Power-sharing", "X.POL.POWERSHARING"),
    ("Gender, Religion & Caste", "X.POL.GENDERRELIGIONCASTE"),
    ("Money & Credit", "X.ECO.MONEYCREDIT"),
    ("Sectors of Indian Economy", "X.ECO.SECTORS"),
    ("Consumer Rights", "X.ECO.CONSUMERRIGHTS"),
    ("Lifelines of National Economy", "X.GEO.LIFELINES"),
    ("The Rise of Nationalism in Europe", "X.HIST.NATIONALISM_EUROPE"),
])
def test_a_spelling_variant_resolves_to_exactly_one_chapter(text, chapter):
    assert set(resolve_text(text, SST, _seeded()).chapters) == {chapter}


@pytest.mark.parametrize("text, chapter", [
    ("Resources and Development", "X.GEO.RESOURCES"),
    ("Global World", "X.HIST.GLOBALWORLD"),
    ("Globalisation", "X.ECO.GLOBALISATION"),
])
def test_close_names_never_cross_match(text, chapter):
    assert set(resolve_text(text, SST, _seeded()).chapters) == {chapter}


def test_energy_resources_alone_resolves_to_minerals_and_energy(capsys):
    seeded = resolve_text("Energy Resources", SST, _seeded())
    bare = resolve_text("Energy Resources", SST)
    assert set(seeded.chapters) == {"X.GEO.MINERALSENERGY"}
    match = seeded.chapters["X.GEO.MINERALSENERGY"]
    with capsys.disabled():
        print(f"\n'Energy Resources' -> X.GEO.MINERALSENERGY score={match.score} via={match.via}"
              f" (without the alias the title alone scores below the {TITLE_THRESHOLD} "
              "threshold and nothing is returned)")
    assert match.score >= TITLE_THRESHOLD
    assert bare.chapters == {}


@pytest.mark.parametrize("text, subject, chapter", [
    ("SECTION A (History : Print Culture and the Modern World)", "X.HIST", "X.HIST.PRINTCULTURE"),
    ("(Geography : Minerals and Energy Resources)", "X.GEO", "X.GEO.MINERALSENERGY"),
    ("(Political Science : Political Parties)", "X.POL", "X.POL.PARTIES"),
    ("(Economics : Globalisation and the Indian Economy)", "X.ECO", "X.ECO.GLOBALISATION"),
])
def test_the_gold_papers_headers_resolve_to_their_one_chapter(text, subject, chapter):
    for aliases in (None, _seeded()):
        out = resolve_text(text, SST, aliases)
        assert set(out.chapters) == {chapter}
        assert set(out.subjects) == {subject}
