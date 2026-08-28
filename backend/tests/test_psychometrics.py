from __future__ import annotations

from app.psychometrics.instrument import SCALES, items, ordered_items, screens, stream_matrix
from app.psychometrics.scoring import hexagon_consistency, ipsative_centre, score
from app.psychometrics.validity import Response, screen


def test_bank_is_six_items_per_scale():
    assert len(items()) == 36
    for s in SCALES:
        assert sum(1 for i in items() if i.scale == s) == 6


def test_items_are_localised_in_three_languages():
    for item in items():
        assert item.text["en"] and item.text["ta"] and item.text["hi"]
        assert item.localised("ta") != item.localised("en")


def test_order_is_interleaved_and_reproducible():
    a = [i.id for i in ordered_items(42)]
    b = [i.id for i in ordered_items(42)]
    assert a == b                                   # fixed seed => auditable
    assert a != [i.id for i in ordered_items(43)]
    assert [len(s) for s in screens(42)] == [6] * 6
    # no three consecutive items from the same scale
    scales = [i.scale for i in ordered_items(42)]
    assert not any(scales[i] == scales[i + 1] == scales[i + 2] for i in range(len(scales) - 2))


def test_ipsative_centering_removes_elevation():
    high = {"R": 30, "I": 30, "A": 30, "S": 30, "E": 30, "C": 30}
    low = {"R": 6, "I": 6, "A": 6, "S": 6, "E": 6, "C": 6}
    assert ipsative_centre(high) == ipsative_centre(low)


def test_a_clear_profile_gets_a_code_and_a_stream():
    responses = {i.id: (5 if i.scale == "I" else 4 if i.scale == "R" else 2) for i in items()}
    out = score(responses)
    assert out.holland_code is not None and out.holland_code.startswith("I")
    assert not out.recommendation_withheld
    assert out.top_streams == ["Science"]


def test_a_flat_profile_withholds_the_recommendation():
    """A student who likes everything must not be told 'you could do anything'."""
    out = score({i.id: 5 for i in items()})
    assert out.recommendation_withheld
    assert out.holland_code is None
    assert out.top_streams == []
    assert "counselling" in (out.withheld_reason or "")


def test_hexagon_consistency():
    assert hexagon_consistency("RI") == 3      # adjacent
    assert hexagon_consistency("RA") == 2      # alternate
    assert hexagon_consistency("RS") == 1      # opposite


def test_stream_matrix_is_data_and_normalised():
    W = stream_matrix()
    assert set(W) == {"Science", "Commerce", "Humanities", "Vocational"}
    for weights in W.values():
        assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_validity_catches_straight_lining_and_speeding():
    fast = [Response(i.id, 3, 0.4) for i in items()]
    rep = screen(fast, 36)
    assert rep.status == "invalid"
    assert any("straight-lining" in r for r in rep.reasons)
    assert any("median item time" in r for r in rep.reasons)


def test_validity_marks_incomplete_sessions_invalid():
    partial = [Response(i.id, 3, 4.0) for i in items()[:10]]
    assert screen(partial, 36).status == "invalid"


def test_a_normal_session_is_valid():
    ok = [Response(item.id, 2 + (n % 4), 4.0) for n, item in enumerate(items())]
    assert screen(ok, 36).status == "valid"
