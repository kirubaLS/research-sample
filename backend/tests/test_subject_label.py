"""_subject_label must decode both a single book's own subject_code (e.g. "X.MATH") and
a multi-book group's group_code (e.g. "X.SST", "X.ENG", "X.HIN") -- an assessment is
often recorded under the group code directly (one Social Science paper spans History,
Geography, Political Science and Economics), and CURRICULA is keyed by each individual
book's own subject_code, never by a bare group_code. Before this fix a group code fell
through untouched and printed straight to a principal/teacher/student as e.g. "X.SST"."""

from __future__ import annotations

# Imported inside each test, not at module level: app.api.academics pulls in app.db,
# whose engine is built from YAADHUM_DATABASE_URL -- the conftest _tmp_db fixture sets
# that env var, but only once a test actually runs, after collection has already
# imported every test module top to bottom.


def test_a_single_book_subject_code_decodes_to_its_label(_tmp_db):
    from app.api.academics import _subject_label

    assert _subject_label("X.MATH") == "Class X Mathematics"


def test_a_group_code_decodes_to_the_groups_own_label(_tmp_db):
    from app.api.academics import _subject_label

    assert _subject_label("X.SST") == "Class X Social Science"


def test_an_unknown_code_falls_back_to_itself_rather_than_erroring(_tmp_db):
    from app.api.academics import _subject_label

    assert _subject_label("X.NOPE") == "X.NOPE"
