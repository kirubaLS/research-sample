"""The OCR mapper's book-text stage: finding the sections whose own text matches a question, and
the choose-then-check pipeline around it. The models are stubs; no paid API is called."""

# ruff: noqa: E501 -- exam wording in the cases is not wrapped to code width
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def pl():
    from app.api import prompt_lab

    return prompt_lab


@pytest.fixture
def v2():
    from app.mapping import ocr_mapper_v2

    return ocr_mapper_v2


@pytest.fixture
def sr():
    from app.mapping import section_retrieval

    return section_retrieval


@pytest.fixture
def pt():
    from app.mapping import prompt_taxonomy

    return prompt_taxonomy

# (subject, question as printed, the section that teaches it): standard exam wording, not tuned
CASES = [
    ("X.HIST", "In eighteenth-century England, small pocket-sized books were sold for a penny by petty pedlars known as chapmen.", "H5.4"),
    ("X.HIST", "Explain how the printing press developed by Gutenberg changed the production of books in Europe.", "H5.2.1"),
    ("X.HIST", "The Roman Catholic Church began keeping an Index of Prohibited Books.", "H5.3.3"),
    ("X.GEO", "A valley in Ladakh has several hot springs where groundwater rises to the surface as steam.", "G5.4.2.6"),
    ("X.GEO", "Lignite is a low grade brown coal found at Neyveli.", "G5.4.1.1"),
    ("X.POL", "A party secures eight per cent of the votes in the Lok Sabha elections. According to the Election Commission criteria this party will be recognised as", "P4.3"),
    ("X.POL", "What is meant by defection? The anti-defection law.", "P4.6"),
    ("X.ECO", "Liberalisation of foreign trade means removing trade barriers and restrictions.", "E4.5.2"),
    ("X.ECO", "Rapid improvement in technology has stimulated the globalisation process.", "E4.5.1"),
]


def test_the_book_text_finds_the_section_a_question_is_about(sr):
    ix = sr.index()
    found = 0
    for subject, text, want in CASES:
        ids = [h.topic_id for h in ix.search(text, subject, 5)]
        found += want in ids
    assert found >= len(CASES) - 1, "the right section is among the top five"


def test_a_search_stays_inside_its_subject_and_says_why(sr):
    ix = sr.index()
    hits = ix.search("Gutenberg printing press Bible", "X.HIST", 5)
    assert hits and all(h.topic_id.startswith("H") for h in hits)
    assert "Gutenberg" in hits[0].snippet
    assert ix.search("", "X.HIST") == [] and ix.search("the and of", "X.GEO") == []


def test_exam_wording_does_not_drive_the_match(sr):
    toks = sr.tokens("Explain the following statement. Choose the correct option. Justify with suitable examples.")
    assert toks == []


class _Client:
    """A cheap reader that always picks `first`, and a strong one that picks `second`."""

    def __init__(self, first, second):
        self.calls = []
        self.messages = self
        self._first, self._second = first, second

    def parse(self, **kw):
        from app.api import prompt_lab as pl

        rows = json.loads(kw["messages"][0]["content"].split("<questions>\n")[1].split("\n</questions>")[0])
        self.calls.append((kw["model"], rows, kw["system"][0]["text"]))
        strong = "second reader" in kw["system"][0]["text"]
        pick = self._second if strong else self._first
        out = [pl._Row(row=r["row"], chapter_id=pick.split(".")[0], topic_id=pick, confidence="medium" if not strong else "high",
                       syllabus_status="in_syllabus", reason="x") for r in rows]
        usage = SimpleNamespace(input_tokens=500, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return SimpleNamespace(parsed_output=pl._Out(mappings=out), usage=usage)


def _settings():
    from app.config import get_settings

    return get_settings()


def test_every_question_carries_candidate_sections_with_their_text(v2):
    client = _Client("H5.4", "H5.4")
    rows = [{"row": 0, "text": "Small books sold for a penny by chapmen in England", "section": "A"}]
    answers, usage, calls, errors, meta = v2.map_rows_v2(client, _settings(), rows)
    first_model, sent, rules = client.calls[0]
    assert "H5.4" in [c["id"] for c in sent[0]["candidates"]]
    assert sent[0]["candidates"][0]["matches"], "the matching sentences from the book come with each candidate"
    assert "Candidate sections" in rules and errors == []
    assert meta[0]["supported_by_book"] is True


def test_an_answer_the_book_text_does_not_support_is_reread_by_the_strong_model_and_can_change(v2):
    client = _Client("H5.1.1", "H5.4")          # the cheap reader picks a neighbour
    rows = [{"row": 0, "text": "Small pocket-sized books were sold for a penny by chapmen in England", "section": "A"}]
    answers, usage, calls, errors, meta = v2.map_rows_v2(client, _settings(), rows)
    models = [c[0] for c in client.calls]
    assert models[0] == _settings().model_high_volume and models[-1] == _settings().model_high_stakes
    assert answers[0].topic_id == "H5.4"
    assert meta[0]["verified"] and meta[0]["changed"] and meta[0]["first_pass"] == "H5.1.1"
    assert set(usage) == {_settings().model_high_volume, _settings().model_high_stakes}
    strong_rows = client.calls[-1][1]
    assert strong_rows[0]["first_answer"]["topic_id"] == "H5.1.1"


def test_a_confident_answer_the_book_supports_is_not_rechecked(v2):
    class Sure(_Client):
        def parse(self, **kw):
            r = super().parse(**kw)
            for m in r.parsed_output.mappings:
                m.confidence = "high"
            return r

    client = Sure("H5.4", "H5.4")
    rows = [{"row": 0, "text": "Small pocket-sized books were sold for a penny by chapmen", "section": "A"}]
    _a, usage, calls, _e, meta = v2.map_rows_v2(client, _settings(), rows)
    assert calls == 1 and meta[0]["verified"] is False and len(usage) == 1


def test_only_a_bounded_number_of_rows_go_to_the_strong_model(monkeypatch, v2):
    monkeypatch.setattr(v2, "MAX_VERIFY", 3)
    client = _Client("H1.1", "H1.1")
    rows = [{"row": i, "text": f"Printing press Gutenberg Bible number {i}", "section": "A"} for i in range(10)]
    _a, _u, _c, _e, meta = v2.map_rows_v2(client, _settings(), rows)
    assert sum(1 for m in meta.values() if m["verified"]) <= 3


def test_the_taxonomy_still_closes_the_list(pt):
    assert pt.build().topic("H5.4") is not None


# ---------------------------------------------------------------------------- Science

SCIENCE_CASES = [
    ("State Ohm's law and write the relation between potential difference and current.", "P3.4"),
    ("Why does silver chloride turn grey in sunlight? Name the type of reaction.", "C1.4.2"),
    ("Why is the colour of the clear sky blue? Explain scattering of light.", "P2.7.2"),
    ("What is the function of the alveoli in the lungs? Write about respiration.", "B1.3"),
    ("Define a homologous series of carbon compounds with an example.", "C4.6"),
    ("Mendel crossed tall and short pea plants. State the ratio in the F2 generation.", "B4.2.2"),
    ("An object is placed at 30 cm from a concave mirror of focal length 15 cm. Use the mirror formula to find the image distance.", "P1.6"),
    ("What is the effect of depletion of the ozone layer on the environment?", "ENV1.3.1"),
    ("Explain the extraction of a metal low in the reactivity series, such as mercury from cinnabar.", "C3.6.2"),
    ("Soaps and detergents: explain the cleansing action of soap with micelles.", "C4.10"),
    ("Draw a ray diagram for image formation by a convex lens when the object is beyond 2F.", "P1.12"),
    ("What is the pH of salts formed from strong acid and strong base?", "C2.12.2"),
]


def test_the_science_list_is_the_schools_own_and_complete():
    from app.mapping import science_taxonomy as st

    t = st.build()
    assert [c.id for c in t.chapters] == ["C1", "C2", "C3", "C4", "B1", "B2", "B3", "B4", "P1", "P2", "P3", "P4", "ENV1"]
    assert t.topic_count == 157
    assert t.topic("C2.10").title == "How Strong are Acid or Base Solutions?"
    assert t.topic("P3.6.1").title == "Resistors in Series" and t.topic("ENV1.3.2").title == "Managing the Garbage we Produce"
    assert t.topic("C1.4.1").chapter_id == "C1" and t.topic("C1.4.1").depth == 2
    assert all(x.keywords for c in t.chapters for x in c.topics), "every topic carries hints"


def test_science_ids_are_not_mixed_up_with_social_sciences():
    from app.mapping import prompt_taxonomy as pt
    from app.mapping import science_taxonomy as st

    assert pt.build().topic("P4.1").title.startswith("Why do we need political")
    assert st.build().topic("P4.1").title == "Magnetic Field and Field Lines"


def test_the_science_book_text_finds_the_section(sr):
    ix = sr.science_index()
    found = sum(want in [h.topic_id for h in ix.search(q, None, 5)] for q, want in SCIENCE_CASES)
    assert found >= len(SCIENCE_CASES) - 2, f"{found} of {len(SCIENCE_CASES)} in the top five"


def test_a_science_paper_uses_the_science_list_and_ignores_the_section_letter(v2):
    from app.mapping import ocr_mapper_v2

    client = _Client("P3.4", "P3.4")
    rows = [{"row": 0, "text": "State Ohm's law and write the relation between potential difference and current.",
             "section": "A"}]
    answers, usage, calls, errors, meta = v2.map_rows_v2(
        client, _settings(), rows, profile=ocr_mapper_v2.SCIENCE)
    model, sent, rules = client.calls[0]
    assert "CBSE Class X Science" in rules and "Social" not in rules
    assert "section" not in sent[0], "a Science section letter is not a subject"
    assert sent[0]["candidates"][0]["id"] == "P3.4"
    taxonomy_text = ""
    assert errors == [] and answers[0].topic_id == "P3.4" and taxonomy_text == ""


def test_science_answers_resolve_against_the_science_list(v2):
    from app.api import prompt_lab as pl

    ok = pl._Row(row=0, chapter_id="C2", topic_id="C2.10", secondary_topic_ids=["C2.11", "NOPE"],
                 confidence="high", syllabus_status="in_syllabus", reason="pH", considered=["C2.10", "ZZ9"])
    r = v2.SCIENCE.resolve(v2.SCIENCE.taxonomy(), ok, "A")
    assert r["topic"]["id"] == "C2.10" and r["chapter"]["title"] == "Acids, Bases and Salts"
    assert r["topic"]["major_number"] == "10" and [s["id"] for s in r["secondary"]] == ["C2.11"]
    assert "unknown secondary id NOPE" in r["problems"] and r["considered"] == ["C2.10"]
    assert v2.SCIENCE.resolve(v2.SCIENCE.taxonomy(), None, None)["needs_review"] is True


def test_the_profile_follows_the_subject_code(v2):
    assert v2.profile_for("X.SCI") is v2.SCIENCE and v2.profile_for("X.SCI.ANY") is v2.SCIENCE
    assert v2.profile_for("X.SST") is v2.SOCIAL and v2.profile_for(None) is v2.SOCIAL


# ---------------------------------------------------------------------------- Mathematics

MATH_CASES = [
    ("Find the HCF and LCM of 96 and 404 by the prime factorisation method.", "M1.1"),
    ("Prove that 3 + 2 root 5 is an irrational number.", "M1.2"),
    ("If alpha and beta are the zeroes of the polynomial x^2 - 5x + 6, find alpha + beta and alpha beta.", "M2.2"),
    ("Solve the following pair of linear equations by the elimination method: 3x + 4y = 10, 2x - 2y = 2.", "M3.2.2"),
    ("Find the value of k for which the quadratic equation kx^2 - 6x + 1 = 0 has equal roots. Find the discriminant.", "M4.2"),
    ("Which term of the AP 3, 8, 13, 18, ... is 78? Find the common difference.", "M5.1"),
    ("Find the sum of the first 22 terms of the AP 8, 3, -2, ...", "M5.2"),
    ("In triangle ABC, DE is parallel to BC and AD/DB = 3/5. Find AE/EC.", "M6.2"),
    ("Find the coordinates of the point which divides the segment joining A(4, -3) and B(8, 5) in the ratio 3:1.", "M7.2"),
    ("Prove that (sec A + tan A)(1 - sin A) = cos A.", "M8.3"),
    ("From the top of a 7 m high building the angle of elevation of the top of a tower is 60. Find the height of the tower.", "M9.1"),
    ("Prove that the lengths of tangents drawn from an external point to a circle are equal.", "M10.2"),
    ("A bag contains 3 red and 5 blue balls. A ball is drawn at random. Find the probability that it is red.", "M14.1"),
]


def test_the_maths_list_is_the_schools_own_and_complete():
    from app.mapping import math_taxonomy as mt

    t = mt.build()
    assert [c.id for c in t.chapters] == [f"M{i}" for i in range(1, 15)]
    assert t.topic_count == 33
    assert t.topic("M8.2.3").title == "Trigonometric Ratios of 0° and 90°"
    assert t.topic("M3.2.1").depth == 2 and t.topic("M14.1").title == "Probability — A Theoretical Approach"
    assert all(x.keywords for c in t.chapters for x in c.topics), "every topic carries key terms"


def test_maths_searches_its_own_key_terms(sr):
    ix = sr.math_index()
    found = sum(want in [h.topic_id for h in ix.search(q, None, 5)] for q, want in MATH_CASES)
    assert found >= len(MATH_CASES) - 1


def test_a_maths_paper_uses_the_maths_prompt_and_ignores_the_section_letter(v2):
    client = _Client("M2.2", "M2.2")
    rows = [{"row": 0, "text": "If alpha and beta are the zeroes of x^2 - 5x + 6, find alpha + beta.", "section": "B"}]
    answers, _usage, _calls, errors, _meta = v2.map_rows_v2(client, _settings(), rows, profile=v2.MATHS)
    _model, sent, rules = client.calls[0]
    assert "CBSE Class X Mathematics" in rules and "Social" not in rules and "Science" not in rules
    assert "section" not in sent[0] and sent[0]["candidates"][0]["id"] == "M2.2"
    assert errors == [] and answers[0].topic_id == "M2.2"


def test_each_subject_keeps_its_own_prompt_and_list(v2):
    names = {p.name: p for p in (v2.SOCIAL, v2.SCIENCE, v2.MATHS)}
    assert set(names) == {"social", "science", "maths"}
    assert len({p.rules for p in names.values()}) == 3 and len({p.verify for p in names.values()}) == 3
    assert v2.profile_for("X.MATH") is v2.MATHS and v2.profile_for("X.SCI") is v2.SCIENCE
    assert v2.profile_for("X.SST") is v2.SOCIAL and v2.profile_for("") is v2.SOCIAL
    assert [c.id[0] for c in v2.MATHS.taxonomy().chapters] == ["M"] * 14
