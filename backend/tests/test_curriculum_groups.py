"""One real exam paper can draw on several books (English: 3, Hindi: 4). group_subjects()
is the lookup that turns an assessment's subject_code -- a book or a group -- into the
full set of book-level subject_codes a paper actually needs, and subject_groups()/
list_subjects group them for the admin screen. See app/curriculum/__init__.py.
"""

from __future__ import annotations

from app.curriculum import CURRICULA, group_subjects, subject_groups


def test_group_code_resolves_every_book_in_registration_order():
    assert group_subjects("X.ENG") == ["X.ENG.FF", "X.ENG.FWF", "X.ENG.WB"]


def test_hindi_group_resolves_all_four_books_in_registration_order():
    assert group_subjects("X.HIN") == [
        "X.HIN.KR", "X.HIN.KS", "X.HIN.SP", "X.HIN.SY",
    ]


def test_a_book_level_code_also_resolves_the_full_group():
    assert group_subjects("X.ENG.FF") == ["X.ENG.FF", "X.ENG.FWF", "X.ENG.WB"]


def test_a_single_book_subject_is_unaffected():
    assert group_subjects("X.MATH") == ["X.MATH"]


def test_an_unrecognised_code_comes_back_unchanged():
    assert group_subjects("nonsense") == ["nonsense"]


#: Class X Social Science is the same real-world shape as English/Hindi: four separate
#: NCERT books (History, Geography, Political Science, Economics), one real exam paper.
SOCIAL_SCIENCE_CODES = ("X.HIST", "X.GEO", "X.POL", "X.ECO")


def test_social_science_group_resolves_all_four_books_in_registration_order():
    assert group_subjects("X.SST") == ["X.HIST", "X.GEO", "X.POL", "X.ECO"]


def test_a_social_science_book_level_code_also_resolves_the_full_group():
    assert group_subjects("X.HIST") == ["X.HIST", "X.GEO", "X.POL", "X.ECO"]


def test_every_curriculum_defaults_its_group_to_itself_unless_set_explicitly():
    grouped_prefixes = ("X.ENG", "X.HIN") + SOCIAL_SCIENCE_CODES
    for code, curriculum in CURRICULA.items():
        if code in grouped_prefixes or code.startswith("X.ENG") or code.startswith("X.HIN"):
            continue
        assert curriculum.group_code == code
        assert curriculum.group_label == curriculum.subject_label


def test_subject_groups_clusters_english_hindi_social_science_and_leaves_others_alone():
    groups = {g.group_code: g for g in subject_groups()}
    assert [c.subject_code for c in groups["X.ENG"].members] == [
        "X.ENG.FF", "X.ENG.FWF", "X.ENG.WB",
    ]
    assert [c.subject_code for c in groups["X.HIN"].members] == [
        "X.HIN.KR", "X.HIN.KS", "X.HIN.SP", "X.HIN.SY",
    ]
    assert [c.subject_code for c in groups["X.SST"].members] == [
        "X.HIST", "X.GEO", "X.POL", "X.ECO",
    ]
    assert [c.subject_code for c in groups["X.MATH"].members] == ["X.MATH"]
    assert [c.subject_code for c in groups["X.TAM"].members] == ["X.TAM"]
