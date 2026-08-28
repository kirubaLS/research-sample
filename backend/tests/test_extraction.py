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
