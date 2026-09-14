from __future__ import annotations

from app.extraction.address import Address, AddressResolver, check_monotonic
from app.extraction.choice import effective_total, group_choices, is_or_marker
from app.extraction.mark_grammar import TextSpan, extract_marks, parse_label
from app.extraction.verification import verify_paper


def test_mark_grammar_three_forms():
    assert parse_label("3").value == 3
    p = parse_label("6×3=18")
    assert (p.value, p.sub_parts, p.per_part) == (18, 6, 3.0)
    assert parse_label("5 x 2 = 10").value == 10
    assert parse_label("(Grammar) 12 Marks").form == "section_total"
    assert parse_label("banana") is None


def test_product_form_self_checks():
    good = parse_label("6×3=18")
    assert good.is_self_consistent
    bad = parse_label("6×3=20")
    assert not bad.is_self_consistent


def test_page_furniture_filter_rejects_the_qp_code():
    """The Tamil paper's Q.P. code is literally '10' — a plausible mark — on every page."""
    spans = [TextSpan("10", page, (40, 700, 55, 712), 612.0) for page in range(1, 13)]
    spans.append(TextSpan("3", 4, (520, 300, 540, 312), 612.0))
    out = extract_marks(spans)
    assert out.furniture_rejected == 12
    assert [label.value for label in out.labels] == [3.0]


def test_marks_must_sit_in_the_measured_right_hand_band():
    body = TextSpan("3", 1, (100, 300, 118, 312), 612.0)       # mid-page prose
    margin = TextSpan("3", 1, (520, 300, 538, 312), 612.0)
    out = extract_marks([body, margin], min_pages_for_furniture=99)
    assert out.band_rejected == 1
    assert len(out.labels) == 1


def test_address_parsing_across_scripts():
    assert Address.parse("Q.16 b").choice_alt == "b"
    assert Address.parse("16(ख)").choice_alt == "b"        # Hindi
    assert Address.parse("16(ஆ)").choice_alt == "b"        # Tamil
    assert Address.parse("१६").question_no == "16"          # Devanagari numerals
    assert Address.parse("15 (iii) a").sub_part == "iii"


def test_closed_vocabulary_rejects_invented_addresses():
    r = AddressResolver(["A/16//a", "A/16//b", "B/4//"])
    assert r.resolve("16(a)")[0] is not None
    assert r.resolve("16(c)") == (None, "no_such_address")
    assert r.resolve("47") == (None, "no_such_question")


def test_section_prior_disambiguates():
    r = AddressResolver(["A/4//", "B/4//"])
    addr, reason = r.resolve("4", section_hint="B")
    assert addr is not None and addr.section == "B" and reason == "section_prior"


def test_monotonicity_break_is_reported():
    seq = [Address("A", "1"), Address("A", "2"), Address("A", "9"), Address("A", "3")]
    assert check_monotonic(seq) == [3]


def test_or_markers_in_three_scripts():
    assert is_or_marker("OR") and is_or_marker("अथवा")
    assert not is_or_marker("ORDER")


def test_choice_group_counts_marks_once():
    rows = [
        (Address("C", "27", None, "a"), 3.0),
        (Address("C", "27", None, "b"), 3.0),
        (Address("B", "4", None, None), 2.0),
    ]
    _, groups = group_choices(rows)
    assert len(groups) == 1
    assert sum(m for _, m in rows) == 8.0        # naive
    assert effective_total(rows, groups) == 5.0  # correct


def test_attempt_n_of_m_group_counts_marks_once():
    """A group with no OR marker and no choice_alt: five 1-mark sub-items, only three
    required. Naive summing (what shipped before this fix) counts all five; the correct
    total is N x per-item-mark, once."""
    rows = [
        (Address("A", "5", "i", None), 1.0),
        (Address("A", "5", "ii", None), 1.0),
        (Address("A", "5", "iii", None), 1.0),
        (Address("A", "5", "iv", None), 1.0),
        (Address("A", "5", "v", None), 1.0),
        (Address("B", "4", None, None), 2.0),
    ]
    attempt_required = {
        Address("A", "5", "i", None).key: 3,
        Address("A", "5", "ii", None).key: 3,
        Address("A", "5", "iii", None).key: 3,
        Address("A", "5", "iv", None).key: 3,
        Address("A", "5", "v", None).key: 3,
    }
    mapping, groups = group_choices(rows, attempt_required)
    assert len(groups) == 1
    group = groups[0]
    assert group.size == 5
    assert group.required_count == 3
    assert group.marks == 3.0                              # 3 required x 1 mark each
    assert sum(m for _, m in rows) == 7.0                   # naive: 5 + 2
    assert effective_total(rows, groups) == 5.0             # correct: 3 + 2
    assert all(mapping[a.key] == group.group_id for a in group.addresses)


def test_attempt_n_of_m_group_uses_max_when_members_disagree_on_n():
    """The paper states one N; a stray misread member should never silently shrink the
    group below what another member of the same group claims."""
    rows = [
        (Address("A", "5", "i", None), 1.0),
        (Address("A", "5", "ii", None), 1.0),
        (Address("A", "5", "iii", None), 1.0),
    ]
    attempt_required = {
        Address("A", "5", "i", None).key: 3,
        Address("A", "5", "ii", None).key: 2,   # misread
        Address("A", "5", "iii", None).key: 3,
    }
    _, groups = group_choices(rows, attempt_required)
    assert groups[0].required_count == 3


def test_attempt_n_of_m_does_not_disturb_binary_or_grouping():
    """The two choice shapes coexist on one paper without interfering with each other."""
    rows = [
        (Address("C", "27", None, "a"), 3.0),
        (Address("C", "27", None, "b"), 3.0),
        (Address("A", "5", "i", None), 1.0),
        (Address("A", "5", "ii", None), 1.0),
        (Address("A", "5", "iii", None), 1.0),
    ]
    attempt_required = {
        Address("A", "5", "i", None).key: 2,
        Address("A", "5", "ii", None).key: 2,
        Address("A", "5", "iii", None).key: 2,
    }
    mapping, groups = group_choices(rows, attempt_required)
    assert len(groups) == 2
    assert effective_total(rows, groups) == 3.0 + 2.0        # OR group once, 2 of 3 items


def test_a_single_attempt_required_row_is_not_grouped():
    """One row alone carrying attempt_required is not a group -- nothing to dedupe."""
    rows = [(Address("A", "5", "i", None), 1.0)]
    mapping, groups = group_choices(rows, {Address("A", "5", "i", None).key: 3})
    assert groups == []
    assert mapping == {}


def test_a_hallucinated_n_larger_than_the_group_is_clamped_not_trusted():
    """A paper cannot require more attempts than it printed sub-items for. If the model
    reads N=5 for a group that only has 3 rows, that N is physically impossible -- it is
    clamped to the group's real size (3) so a downstream total can never be inflated
    past what the paper could actually be worth, and the original misread is kept on the
    group (required_as_read) so it can still be flagged rather than silently vanish."""
    rows = [
        (Address("A", "5", "i", None), 1.0),
        (Address("A", "5", "ii", None), 1.0),
        (Address("A", "5", "iii", None), 1.0),
    ]
    attempt_required = {
        Address("A", "5", "i", None).key: 5,
        Address("A", "5", "ii", None).key: 5,
        Address("A", "5", "iii", None).key: 5,
    }
    _, groups = group_choices(rows, attempt_required)
    group = groups[0]
    assert group.size == 3
    assert group.required_count == 3          # clamped: cannot exceed what was printed
    assert group.required_as_read == 5        # the misread itself is not thrown away
    assert group.marks == 3.0                 # never 5.0 -- that would be invented marks
    assert effective_total(rows, groups) == 3.0


def test_all_four_gates_pass_on_maths_30b_section_b():
    """5 VSA x 2 marks = 10, with Q22 offering (a)/(b) — a faithful reconstruction."""
    rows = [(Address("B", str(20 + i), None, None), 2.0) for i in range(1, 6) if 20 + i != 22]
    rows += [(Address("B", "22", None, "a"), 2.0), (Address("B", "22", None, "b"), 2.0)]
    _, groups = group_choices(rows)
    report = verify_paper(
        rows, groups,
        {"question_count": 5, "total_marks": 10, "sections": {"B": 10}},
        section_arithmetic={"B": (5, 2.0, 10.0)},
    )
    assert report.passed, report.as_dict()
    assert len(report.results) == 4


def test_gate_failure_names_the_broken_equation():
    rows = [(Address("B", "21", None, None), 2.0)]
    _, groups = group_choices(rows)
    report = verify_paper(rows, groups, {"question_count": 5, "total_marks": 10, "sections": {"B": 10}})
    assert not report.passed
    names = {f.gate for f in report.failures}
    assert "G1_question_count" in names and "G4_paper_total" in names


def test_g5_flags_a_hallucinated_n_even_though_the_clamp_kept_the_total_sound():
    """G2/G4 use the already-clamped total, so they can pass even when a group's N was
    misread -- G5 exists precisely so that disagreement is still visible to a human,
    not silently absorbed by the clamp."""
    rows = [
        (Address("A", "5", "i", None), 1.0),
        (Address("A", "5", "ii", None), 1.0),
        (Address("A", "5", "iii", None), 1.0),
    ]
    attempt_required = {
        Address("A", "5", "i", None).key: 5,
        Address("A", "5", "ii", None).key: 5,
        Address("A", "5", "iii", None).key: 5,
    }
    _, groups = group_choices(rows, attempt_required)
    report = verify_paper(
        rows, groups, {"question_count": 1, "total_marks": 3, "sections": {"A": 3}},
    )
    g2, g4 = report.results[1], report.results[-1]
    assert g2.passed and g4.passed, "the clamp already made the totals correct"
    g5 = next(f for f in report.results if f.gate.startswith("G5_"))
    assert not g5.passed
    assert g5.expected == 3 and g5.actual == 5
    assert not report.passed, "a G5 failure must still block the paper"
