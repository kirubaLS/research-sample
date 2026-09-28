"""Two real misses found auditing a Geography (Minerals and Energy Resources) paper
against the actual book map, both reproduced here with the book's own real text.

1. A bare state name lifted from a pie-chart legend ("Gujarat", one word, its own chunk --
   see import_book_map.py's per-caption chunking) out-scored the real Petroleum passage
   for "An oil field located in Gujarat", because TF-IDF's length normalization rewards a
   one-word "document" with almost its raw idf while a real paragraph is diluted by its own
   length. content_chunks() (app/ingest/probe.py) excludes fragments below
   MIN_CONTENT_TOKENS from the pool retrieval scores against, the same way bucket='E'
   exercise chunks already were.

2. "Explain the difference between ferrous and non-ferrous minerals" landed on the parent
   section "2 Mode of Occurrence of Minerals" instead of the child "2.2 Ferrous Minerals"
   where the actual distinction and examples live, because the parent's own intro paragraph
   mentions "non-ferrous" in passing and is split across several chunks, letting it
   out-accumulate the child's single, more specific, higher-scoring passage. locate()
   now prefers a section that is a dotted-prefix descendant of the leading section whenever
   that descendant is itself real, voted-for evidence -- never a contest between siblings
   (Coal vs Petroleum stays undisturbed by this).
"""

from __future__ import annotations

from app.classify.judge import Classification
from app.ingest.probe import (
    LexicalIndex,
    content_chunks,
    full_chapter_evidence,
    locate,
    retrieval_query_text,
)


class _Chunk:
    def __init__(self, chunk_id, reference, text, node_id, section_number, bucket="T"):
        self.id = chunk_id
        self.reference = reference
        self.text = text
        self.node_id = node_id
        self.section_number = section_number
        self.bucket = bucket
        self.embedding = None


MINERALS_CHAPTER = "minerals-and-energy-resources"

# Real book text (backend/reference/book_map/geography), trimmed only where marked.
PETROLEUM = _Chunk(
    "petroleum", "4.1.2 Petroleum",
    "Petroleum or mineral oil is the next major energy source in India after coal. It "
    "provides fuel for heat and lighting, lubricants for machinery and raw materials for a "
    "number of manufacturing industries. Most of the petroleum occurrences in India are "
    "associated with anticlines and fault traps in the rock formations of the tertiary age. "
    "Mumbai High, Gujarat and Assam are major petroleum production areas in India. "
    "Ankeleshwar is the most important field of Gujarat. Assam is the oldest oil producing "
    "state of India. Digboi, Naharkatiya and Moran-Hugrijan are the important oil fields in "
    "the state.",
    MINERALS_CHAPTER, "4.1.2",
)
COAL_CAPTION = _Chunk(
    "coal-caption", "4.1.1 Coal (caption)",
    "India: Distribution of Coal, Oil and Natural Gas",
    MINERALS_CHAPTER, "4.1.1",
)
# The real ingest artifact: a pie chart's per-slice legend, one chunk per slice (see
# import_book_map.py's _text_chunks, which turns every unit["captions"] entry into its own
# chunk regardless of how short).
BAUXITE_LEGEND_GUJARAT = _Chunk(
    "bauxite-legend-gujarat", "2.3.2 Bauxite (caption)", "Gujarat",
    MINERALS_CHAPTER, "2.3.2",
)
PADDING = [
    _Chunk(f"pad{i}", f"pad{i}", f"unrelated teaching text about topic {i} in this book", "pad", None)
    for i in range(20)
]


def test_bare_legend_fragment_does_not_beat_the_real_passage():
    stem = "An oil field located in Gujarat"

    # Before: the fragment is in the retrieval pool, as every bucket='T' chunk was.
    before = locate(
        retrieval_query_text(stem),
        [LexicalIndex([PETROLEUM, COAL_CAPTION, BAUXITE_LEGEND_GUJARAT] + PADDING)],
    )
    assert before.section == "2.3.2", "reproduces the real miss: the bare state name wins"

    # After: content_chunks excludes it from the pool that decides chapter/section.
    pool = content_chunks([PETROLEUM, COAL_CAPTION, BAUXITE_LEGEND_GUJARAT] + PADDING)
    assert BAUXITE_LEGEND_GUJARAT not in pool
    assert PETROLEUM in pool and COAL_CAPTION in pool

    after = locate(retrieval_query_text(stem), [LexicalIndex(pool)])
    assert after.node_id == MINERALS_CHAPTER
    assert after.section == "4.1.2", "the real Petroleum passage now wins on its own text"


MODE_OF_OCCURRENCE_INTRO_1 = _Chunk(
    "mode-intro-1", "2 Mode of Occurrence of Minerals",
    "Minerals are usually found in “ores”. The term ore is used to describe an "
    "accumulation of any mineral mixed with other elements. Major metallic minerals like "
    "tin, copper, zinc and lead etc. are obtained from veins and lodes.",
    MINERALS_CHAPTER, "2",
)
MODE_OF_OCCURRENCE_INTRO_2 = _Chunk(
    "mode-intro-2", "2 Mode of Occurrence of Minerals",
    "India is fortunate to have fairly rich and varied mineral resources. Rajasthan with "
    "the rock systems of the peninsula, has reserves of many non-ferrous minerals. Let us "
    "now study the distribution of a few major minerals in India.",
    MINERALS_CHAPTER, "2",
)
FERROUS = _Chunk(
    "ferrous", "2.2 Ferrous Minerals",
    "Ferrous minerals account for about three-fourths of the total value of production of "
    "metallic minerals. They provide a strong base for the development of metallurgical "
    "industries. India exports substantial quantities of ferrous minerals.",
    MINERALS_CHAPTER, "2.2",
)
NON_FERROUS = _Chunk(
    "non-ferrous", "2.3 Non-Ferrous Minerals",
    "India's reserves and production of non-ferrous minerals are not very satisfactory. "
    "These minerals provide raw material for metallurgical, engineering and electrical "
    "industries.",
    MINERALS_CHAPTER, "2.3",
)


def test_specific_child_section_preferred_over_its_own_parent_intro():
    stem = "Explain the difference between ferrous and non-ferrous minerals, giving one example of each."
    pool = [
        MODE_OF_OCCURRENCE_INTRO_1, MODE_OF_OCCURRENCE_INTRO_2, FERROUS, NON_FERROUS,
    ] + PADDING
    index = LexicalIndex(pool)

    verdict = locate(retrieval_query_text(stem), [index])
    assert verdict.node_id == MINERALS_CHAPTER
    assert verdict.section == "2.2", (
        "the parent section '2' must not win just because its intro paragraph is split "
        "into more chunks than its own, more specific child"
    )


def test_sibling_sections_are_still_decided_purely_by_evidence():
    """The specificity preference must never touch a contest between siblings -- only a
    genuine parent/child pair. Coal vs Petroleum stays a fair fight."""
    stem = "An oil field located in Gujarat"
    pool = content_chunks([PETROLEUM, COAL_CAPTION, BAUXITE_LEGEND_GUJARAT] + PADDING)
    verdict = locate(retrieval_query_text(stem), [LexicalIndex(pool)])
    assert verdict.section == "4.1.2"


# --- a third real miss: the right chapter, but the right PASSAGE pruned before the judge
# ever saw it -----------------------------------------------------------------------------

# Real book text (backend/yaadhum.db, subject X.GEO, chapter Minerals and Energy Resources).
# A 1-mark map-skill question naming a real-world fact ("a nuclear power plant") that is
# conceptually about 4.2.1 Nuclear or Atomic Energy, not 4.1.4 Electricity -- but the book's
# actual Nuclear prose never names a state (it names Jharkhand, Rajasthan, Kerala), while
# Electricity's own activity box happens to share far more literal vocabulary with the stem:
# "Locate the 6 nuclear power stations and find out the state in which they are located."
ELECTRICITY_BODY = _Chunk(
    "electricity-body", "4.1.4 Electricity",
    "Electricity has such a wide range of applications in today's world that, its percapita "
    "consumption is considered as an index of development. Electricity is generated mainly "
    "in two ways: by running water which drives hydro turbines to generate hydro "
    "electricity; and by burning other fuels such as coal, petroleum and natural gas to "
    "drive turbines to produce thermal power. Once generated the electricity is exactly the "
    "same.",
    MINERALS_CHAPTER, "4.1.4",
)
ELECTRICITY_ACTIVITY = _Chunk(
    "electricity-activity", "4.1.4 Electricity (activity)",
    "Collect information about thermal/hydel power plants located in your state. Show them "
    "on the map of India. Locate the 6 nuclear power stations and find out the state in "
    "which they are located. Collect information about newly established solar power "
    "plants in India.",
    MINERALS_CHAPTER, "4.1.4",
)
ELECTRICITY_CAPTION = _Chunk(
    "electricity-caption", "4.1.4 Electricity (caption)",
    "India: Distribution of Nuclear and Thermal Power Plants",
    MINERALS_CHAPTER, "4.1.4",
)
NUCLEAR = _Chunk(
    "nuclear", "4.2.1 Nuclear or Atomic Energy",
    "It is obtained by altering the structure of atoms. When such an alteration is made, "
    "much energy is released in the form of heat and this is used to generate electric "
    "power. Uranium and Thorium, which are available in Jharkhand and the Aravalli ranges "
    "of Rajasthan are used for generating atomic or nuclear power. The Monazite sands of "
    "Kerala is also rich in Thorium.",
    MINERALS_CHAPTER, "4.2.1",
)
WIND_POWER = _Chunk(
    "wind-power", "4.2.3 Wind Power",
    "India has great potential of wind power. The largest wind farm cluster is located in "
    "Tamil Nadu from Nagarcoil to Madurai. Apart from these, Andhra Pradesh, Karnataka, "
    "Gujarat, Kerala, Maharashtra and Lakshadweep have important wind farms.",
    MINERALS_CHAPTER, "4.2.3",
)
BIOGAS_CAPTION = _Chunk(
    "biogas-caption", "4.3 Conservation of Energy Resources (caption)",
    "Fig. 5.12: Biogas Plant",
    MINERALS_CHAPTER, "4.3",
)
# Real evidence from two unrelated chapters that out-score Nuclear's own passage on pure
# lexical overlap with "nuclear power plant", exactly as the real book map does (a different
# node_id each, the way real rival chapters are).
POLLUTION_THERMAL = _Chunk(
    "pollution-thermal", "4 Industrial Pollution and Environmental Degradation",
    "Thermal pollution of water occurs when hot water from factories and thermal plants is "
    "drained into rivers and ponds before cooling. What would be the effect on aquatic "
    "life? Wastes from nuclear power plants, nuclear and weapon production facilities cause "
    "cancers, birth defects and miscarriages. Soil and water pollution are closely related.",
    "environmental-degradation", "4",
)
RAMAGUNDAM_CAPTION = _Chunk(
    "ramagundam-caption", "5 Control of Environmental Degradation (caption)",
    "Fig. 6.8: Ramagundam plant",
    "environmental-degradation", "5",
)
COTTON = _Chunk(
    "cotton", "2.1.7.2.1 Cotton",
    "Maharashtra, Gujarat, Madhya Pradesh, Karnataka, Andhra Pradesh, Telangana, Tamil "
    "Nadu, Punjab, Haryana and Uttar Pradesh.",
    "agriculture", "2.1.7.2.1",
)

MINERALS_ENERGY_POOL = [
    ELECTRICITY_BODY, ELECTRICITY_ACTIVITY, ELECTRICITY_CAPTION, NUCLEAR, WIND_POWER,
    BIOGAS_CAPTION, POLLUTION_THERMAL, RAMAGUNDAM_CAPTION, COTTON,
] + PADDING


def test_nuclear_power_plant_in_tamil_nadu_reaches_the_right_chapter():
    """The chapter is not the problem: even with a bare activity-box quote and picture
    captions outscoring Nuclear's own prose on pure literal-word overlap, RRF's chapter
    voting still lands on the right chapter (Minerals and Energy Resources), because
    several of its passages vote for it and rivals only contribute one chunk each."""
    stem = "A nuclear power plant located in Tamil Nadu"
    pool = content_chunks(MINERALS_ENERGY_POOL)
    verdict = locate(retrieval_query_text(stem), [LexicalIndex(pool)], evidence_passages=8, evidence_chapters=3)
    assert verdict.node_id == MINERALS_CHAPTER


def test_default_evidence_passages_no_longer_starves_the_right_passage():
    """The real, fixable half of the "nuclear power plant in Tamil Nadu" miss: the chapter
    was already right, but locate()'s own pruning -- round-robining a fixed evidence budget
    across classifier_evidence_chapters candidate chapters, then taking each chapter's
    passages strictly by score -- dropped the one passage actually about nuclear energy
    before the judge ever got to read it, because an activity box and two picture captions
    outscored it on literal overlap with the stem. At the old default (6) it's gone; at the
    settings default this repo now ships (see app/config.py's
    classifier_evidence_passages) it survives."""
    from app.config import get_settings

    stem = "A nuclear power plant located in Tamil Nadu"
    pool = content_chunks(MINERALS_ENERGY_POOL)
    query = retrieval_query_text(stem)

    starved = locate(query, [LexicalIndex(pool)], evidence_passages=6, evidence_chapters=3)
    assert not any(c.reference == "4.2.1 Nuclear or Atomic Energy" for c in starved.evidence), (
        "this must reproduce the real miss -- if it stops reproducing, the fixture text or "
        "the scoring changed and the test below is no longer testing anything"
    )

    settings = get_settings()
    assert settings.classifier_evidence_passages >= 8, (
        "the fix is a config default, not a one-off call-site override -- pipeline._pass() "
        "reads settings.classifier_evidence_passages, so the fix has to live there"
    )
    fixed = locate(
        query, [LexicalIndex(pool)],
        evidence_passages=settings.classifier_evidence_passages, evidence_chapters=3,
    )
    assert any(c.reference == "4.2.1 Nuclear or Atomic Energy" for c in fixed.evidence), (
        "the judge must actually be shown the Nuclear passage to have any chance of "
        "reasoning its way to it -- retrieval must not silently drop real, "
        "correctly-chaptered evidence before the judge ever sees it"
    )


# --- the structural fix: no scored top-K can be correct for every paper -----------------
#
# The Tamil Nadu nuclear case above is fixed by raising classifier_evidence_passages to 8,
# but that is a stopgap: no fixed K is right for every question, because scoring is
# fundamentally approximate. Here Nuclear's own passage is pushed to 12th of 14 sections in
# its own chapter -- the same shape of miss (activity boxes and captions that happen to
# share literal words with the stem out-scoring the real teaching passage), just one rank
# further down than the original bug -- to prove the fix is structural: full section
# coverage, not a bigger number.

MINERALS_14_SECTIONS = {
    # section number -> (reference, text). Every entry below except 4.2.1 (Nuclear, the
    # real book passage already used above) is written in the same "activity box / picture
    # caption" style the real misses in this file were caused by: literal overlap with the
    # stem's words without being what the stem is actually about.
    "1": ("4 Energy Resources", "Locate on the map of India the nuclear power plant sites "
          "and find out the state in which each is located."),
    "2": ("2 Mode of Occurrence of Minerals", "Collect a picture of a nuclear power plant "
          "located near your state and paste it in your notebook."),
    "2.2": ("2.2 Ferrous Minerals", "Nuclear power plant located at Kalpakkam is one such "
            "site students often visit on an excursion."),
    "2.3": ("2.3 Non-Ferrous Minerals", "The nearest nuclear power plant located to a "
            "non-ferrous mineral belt is often asked in map work."),
    "4.1.1": ("4.1.1 Coal", "A thermal power plant located near a coalfield, unlike a "
              "nuclear power plant located near a river, needs constant rail supply."),
    "4.1.2": ("4.1.2 Petroleum", PETROLEUM.text),
    "4.1.3": ("4.1.3 Natural Gas", "Natural gas is found with or without petroleum and is "
              "used as fuel as well as an industrial raw material."),
    "4.1.4": ("4.1.4 Electricity", ELECTRICITY_ACTIVITY.text),
    "4.2.1": ("4.2.1 Nuclear or Atomic Energy", NUCLEAR.text),
    "4.2.2": ("4.2.2 Solar Energy", "A solar power plant located in a desert state is far "
              "more efficient than one located in a cloudy region."),
    "4.2.3": ("4.2.3 Wind Power", WIND_POWER.text),
    "4.2.4": ("4.2.4 Biogas", "A biogas plant located in a village in Tamil Nadu can meet "
              "most of a household's cooking fuel needs."),
    "4.2.5": ("4.2.5 Tidal Energy", "A tidal power plant located at the mouth of a Gujarat "
              "estuary was India's first such project."),
    "4.3": ("4.3 Conservation of Energy Resources (caption)", "Fig 4.9 A power plant "
            "located in Tamil Nadu, seen from the coast."),
}


def _fourteen_section_pool():
    return content_chunks([
        _Chunk(section, reference, text, MINERALS_CHAPTER, section)
        for section, (reference, text) in MINERALS_14_SECTIONS.items()
    ])


def test_no_fixed_top_k_survives_this_case_but_full_coverage_does():
    """Reproduces the class of bug, not just the one instance: pick ANY fixed K and a paper
    can push the right section past it. Here Nuclear ranks 12th of 14 -- past even the
    just-bumped default of 8 -- yet full_chapter_evidence() still returns it, because
    inclusion depends on being a real section of the identified chapter, not on rank."""
    stem = "A nuclear power plant located in Tamil Nadu"
    query = retrieval_query_text(stem)
    pool = _fourteen_section_pool()
    assert len(pool) == 14

    index = LexicalIndex(pool)
    ranked = index.search(query, k=len(pool))
    nuclear_rank = next(
        i for i, c in enumerate(ranked, 1) if c.reference.startswith("4.2.1")
    )
    assert nuclear_rank >= 12, (
        "the fixture must reproduce Nuclear ranking below any plausible fixed K -- if this "
        "no longer holds, the fixture stopped testing the structural claim"
    )

    # The old mechanism: locate()'s own scored top-K, at the current (already-bumped)
    # default of 8. It still drops Nuclear -- proving the constant itself cannot be the
    # fix, only ever a temporary, paper-specific patch.
    starved = locate(query, [index], evidence_passages=8, evidence_chapters=1)
    assert not any(c.reference.startswith("4.2.1") for c in starved.evidence), (
        "reproduces the bug this test exists to catch a structural fix for -- if this "
        "assertion starts failing, raise the fixture's difficulty, don't delete the test"
    )

    # The new mechanism: every real section of the identified chapter, regardless of score.
    covered = full_chapter_evidence(MINERALS_CHAPTER, pool, query)
    assert len(covered) == 14, "one representative passage per real section, no pruning"
    assert any(c.reference.startswith("4.2.1") for c in covered), (
        "the correct section must reach the judge because it is a real section of the "
        "identified chapter, not because it happened to score well"
    )


def test_pipeline_end_to_end_hands_the_judge_the_low_ranking_correct_section():
    """place_paper()'s own evidence-building, not just full_chapter_evidence() in
    isolation: a stub judge captures exactly what it was shown, and Nuclear's real passage
    must be in it even though it ranks 12th of 14 against the stem."""
    from app.classify.pipeline import place_paper

    pool = _fourteen_section_pool()
    seen_evidence = {}

    class RecordingJudge:
        def classify(self, question, evidence):
            seen_evidence[question] = evidence
            return Classification(
                chapter="Minerals and Energy Resources", tier="Remembering & Understanding",
                skill_required="locate a fact on a map", reasoning="map-skill question",
                confidence=0.8,
            )

    stem = "A nuclear power plant located in Tamil Nadu"
    place_paper(
        [("q1", stem, 1.0)],
        [LexicalIndex(pool)],
        RecordingJudge(),
        chapter_of=lambda n: "Minerals and Energy Resources" if n == MINERALS_CHAPTER else None,
        unit_of=lambda c: "GEO",
        section_of=lambda r: None,
        infer_scope_when_undeclared=False,
    )

    [evidence] = seen_evidence.values()
    references = [e.reference for e in evidence]
    assert len(references) == 14, "the judge must see all 14 real sections, not a shortlist"
    assert any(r.startswith("4.2.1") for r in references), (
        "the judge must actually be shown the Nuclear passage -- it reaches the evidence "
        "list for a structural reason (full section coverage), not because it scored well"
    )


def test_scope_restricted_chapter_still_never_leaks_its_sections():
    """The flip side that must not regress: full chapter coverage only ever fetches
    sections of the chapter locate() itself already chose, and locate() enforces scope
    before it ever picks a winner -- so a chapter ruled out of scope must still be
    completely unreachable, not merely deprioritised."""
    from app.classify.pipeline import place_paper

    pool = _fourteen_section_pool()
    # Must share enough vocabulary with the stem to score above zero within scope --
    # otherwise locate() finds nothing in scope at all and (correctly, by existing
    # design) retries unscoped rather than lose the question, which would make this test
    # exercise that retry path instead of the one it means to check.
    other_chapter_pool = content_chunks([
        _Chunk("other1", "1.1 Other Chapter", "A power plant located somewhere is "
               "mentioned here only in passing, nuclear or otherwise, Tamil Nadu included.",
               "other-chapter", "1.1"),
    ])
    full_pool = pool + other_chapter_pool

    class RecordingJudge:
        def __init__(self):
            self.calls = []

        def classify(self, question, evidence):
            self.calls.append(evidence)
            chapters = {e.chapter for e in evidence}
            [chapter] = chapters if len(chapters) == 1 else [next(iter(chapters))]
            return Classification(
                chapter=chapter, tier="Remembering & Understanding",
                skill_required="x", reasoning="x", confidence=0.8,
            )

    stem = "A nuclear power plant located in Tamil Nadu"
    chapter_of = lambda n: {
        MINERALS_CHAPTER: "Minerals and Energy Resources",
        "other-chapter": "Other Chapter",
    }.get(n)

    judge = RecordingJudge()
    place_paper(
        [("q1", stem, 1.0)],
        [LexicalIndex(full_pool)],
        judge,
        chapter_of=chapter_of,
        unit_of=lambda c: "GEO",
        section_of=lambda r: None,
        scope={"Other Chapter"},          # Minerals and Energy Resources is ruled out
        infer_scope_when_undeclared=False,
    )

    [evidence] = judge.calls
    assert all(e.chapter != "Minerals and Energy Resources" for e in evidence), (
        "an out-of-scope chapter's sections must never reach the judge, however "
        "complete the in-scope coverage is meant to be"
    )
