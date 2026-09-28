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

from app.ingest.probe import LexicalIndex, content_chunks, locate, retrieval_query_text


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
