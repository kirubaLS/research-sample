"""Load a hand-typed section oracle for Social Science chapters, from the real book's own
section list -- see POST /platform/books/{subject}/expected-sections for what this does
and why (verify_against_toc instead of the weaker verify_structure heuristics).

    python -m scripts.load_expected_sections
    python -m scripts.load_expected_sections --dry-run

Scoped deliberately to what has actually been checked against a real chapter file, not
everything a topic list could contain:

* History (X.HIST), all five chapters -- confirmed loadable straight from the given list
  with no PDF needed for MOST of it, because History numbers its own headings IN THE TEXT
  ITSELF (a bare '1', or a decimal subsection under it -- see
  app.ingest.book.BOOK_NUMBERED_SECTION). The number is not something this script invents
  from position; it is read off the same string the book prints. All five chapters have
  since been checked against their real files (tests/test_sst_heading_detection.py and
  tests/test_expected_sections.py) and each caught something real: chapter 4 was missing
  a heading the original list omitted ("2.1 Life of the Workers"); chapter 3 named '2.4'
  twice for two different real headings, both genuinely printed in the book, not a
  transcription slip -- kept as two entries, the second disambiguated to '2.4-2'; chapter
  3 also exposed a running page-banner bug (a section's own number and title, printed
  once as page furniture at a page break, was mistaken for a real heading and split real
  content in two) fixed in app.ingest.book directly, not just worked around here.

* Political Science chapter 4 ("Political Parties", jess404.pdf) -- proven against the
  real file in tests/test_sst_heading_detection.py.

Deliberately NOT included: Geography, Economics, and Political Science chapters 1-3/5.
Those books number NONE of their own headings -- _sections_by_boldness assigns plain
reading-order numbers ('1', '2', '3'...) to whatever it finds -- and the topic list given
for them flattens every level of the book's outline (chapter title, major heading, and
sub-point) into one column with no marker saying which is which. Three of them (Economics
jess202/203/205) have been checked against their real files already, and each turned up a
DIFFERENT real gap in _sections_by_boldness itself (a chapter that bolds only some of its
headings and not others, which used to make the bold pass's sparse-but-non-empty result
look trustworthy on its own -- fixed in app.ingest.book, see test_sst_heading_detection.py)
but none of the three is complete enough yet to safely become a hard oracle: a chapter
that mixes bold and plain headings needs both signals merged, not one chosen over the
other, and that merge is not built yet. Loading a partial or wrong list here would not
silently do nothing, it would PERMANENTLY reject every future upload of that chapter
(verify_against_toc rejects a mismatch), which is worse than the weaker heuristic check
it would replace. Add a chapter here only once its real PDF extraction is complete and
checked, the same way every chapter above was.
"""

from __future__ import annotations

import argparse
import sys

from app.api.books import ExpectedSectionsIn, set_expected_sections
from app.db import SessionLocal

#: subject_code -> {chapter_number: [{"number", "title"}, ...]}
#: History's own numbering, transcribed directly from the book's real headings as given --
#: bare major numbers restart at 1 in every chapter, independent of the chapter's own
#: number (see extract_chapter's bare_headings docstring).
EXPECTED_SECTIONS: dict[str, dict[str, list[dict[str, str]]]] = {
    "X.HIST": {
        "1": [  # jess301.pdf -- The Rise of Nationalism in Europe
            {"number": "1", "title": "The French Revolution and the Idea of the Nation"},
            {"number": "2", "title": "The Making of Nationalism in Europe"},
            {"number": "2.1", "title": "The Aristocracy and the New Middle Class"},
            {"number": "2.2", "title": "What did Liberal Nationalism Stand for?"},
            {"number": "2.3", "title": "A New Conservatism after 1815"},
            {"number": "2.4", "title": "The Revolutionaries"},
            {"number": "3", "title": "The Age of Revolutions: 1830-1848"},
            {"number": "3.1", "title": "The Romantic Imagination and National Feeling"},
            {"number": "3.2", "title": "Hunger, Hardship and Popular Revolt"},
            {"number": "3.3", "title": "1848: The Revolution of the Liberals"},
            {"number": "4", "title": "The Making of Germany and Italy"},
            {"number": "4.1", "title": "Germany – Can the Army be the Architect of a Nation?"},
            {"number": "4.2", "title": "Italy Unified"},
            {"number": "4.3", "title": "The Strange Case of Britain"},
            {"number": "5", "title": "Visualising the Nation"},
            {"number": "6", "title": "Nationalism and Imperialism"},
        ],
        "2": [  # jess302.pdf -- Nationalism in India
            {"number": "1", "title": "The First World War, Khilafat and Non-Cooperation"},
            {"number": "1.1", "title": "The Idea of Satyagraha"},
            {"number": "1.2", "title": "The Rowlatt Act"},
            {"number": "1.3", "title": "Why Non-cooperation?"},
            {"number": "2", "title": "Differing Strands within the Movement"},
            {"number": "2.1", "title": "The Movement in the Towns"},
            {"number": "2.2", "title": "Rebellion in the Countryside"},
            {"number": "2.3", "title": "Swaraj in the Plantations"},
            {"number": "3", "title": "Towards Civil Disobedience"},
            {"number": "3.1", "title": "The Salt March and the Civil Disobedience Movement"},
            {"number": "3.2", "title": "How Participants saw the Movement"},
            {"number": "3.3", "title": "The Limits of Civil Disobedience"},
            {"number": "4", "title": "The Sense of Collective Belonging"},
        ],
        "3": [  # jess303.pdf -- The Making of a Global World -- proven against the real file
            {"number": "1", "title": "The Pre-modern World"},
            {"number": "1.1", "title": "Silk Routes Link the World"},
            {"number": "1.2", "title": "Food Travels: Spaghetti and Potato"},
            {"number": "1.3", "title": "Conquest, Disease and Trade"},
            {"number": "2.1", "title": "A World Economy Takes Shape"},
            {"number": "2.2", "title": "Role of Technology"},
            {"number": "2.3", "title": "Late nineteenth-century Colonialism"},
            {"number": "2.4", "title": "Rinderpest, or the Cattle Plague"},
            # The given list names '2.4' twice -- confirmed a real duplicate IN THE BOOK
            # ITSELF, not a transcription slip: both titles appear verbatim in the real
            # PDF's own text, under the same printed number. Kept as two entries, the
            # second disambiguated to '2.4-2' -- the same disambiguation
            # _pick_sections's own numbered-heading dedup now applies for exactly this
            # case (see BOOK_NUMBERED_SECTION's dedup comment), so both keep their real
            # content instead of the second silently vanishing into the first's span.
            {"number": "2.4-2", "title": "Indentured Labour Migration from India"},
            {"number": "2.5", "title": "Indian Entrepreneurs Abroad"},
            {"number": "2.6", "title": "Indian Trade, Colonialism and the Global System"},
            {"number": "3", "title": "The Inter-war Economy"},
            {"number": "3.1", "title": "Wartime Transformations"},
            {"number": "3.2", "title": "Post-war Recovery"},
            {"number": "3.3", "title": "Rise of Mass Production and Consumption"},
            {"number": "3.4", "title": "The Great Depression"},
            {"number": "3.5", "title": "India and the Great Depression"},
            {"number": "4", "title": "Rebuilding a World Economy: The Post-war Era"},
            # Titles truncated at their real wrapped second line -- a known, accepted gap:
            # _pick_sections merges a wrapped title back together for the SIZE-based path
            # only, not the NUMBERED one History uses (see extract_sections' own note on
            # why merging there is unsafe: this same chapter also has bold map-legend
            # labels and multi-line photo captions stacked just as close together, and a
            # naive merge glued entire legends onto the nearest heading and corrupted the
            # text search that locates it -- silently dropping OTHER real headings
            # entirely, which is worse than one truncated title). The oracle has to match
            # what the extractor actually produces, not the book's own full-length title,
            # or a correct upload would be rejected over a cosmetic mismatch.
            {"number": "4.1", "title": "Post-war Settlement and the"},
            {"number": "4.2", "title": "The Early Post-war Years"},
            {"number": "4.3", "title": "Decolonisation and Independence"},
            {"number": "4.4", "title": "End of Bretton Woods and the Beginning of"},
        ],
        "4": [  # jess304.pdf -- The Age of Industrialisation -- proven against the real file
            {"number": "1", "title": "Before the Industrial Revolution"},
            {"number": "1.1", "title": "The Coming Up of the Factory"},
            {"number": "1.2", "title": "The Pace of Industrial Change"},
            {"number": "2", "title": "Hand Labour and Steam Power"},
            # Not in the originally given list -- found only by running extraction against
            # the real file (see tests/test_expected_sections.py). Kept here rather than
            # silently corrected: this is exactly the class of gap a hand-typed list can
            # have, and the file it was missing from is the only chapter checked so far.
            {"number": "2.1", "title": "Life of the Workers"},
            {"number": "3", "title": "Industrialisation in the Colonies"},
            {"number": "3.1", "title": "The Age of Indian Textiles"},
            {"number": "3.2", "title": "What Happened to Weavers?"},
            {"number": "3.3", "title": "Manchester Comes to India"},
            {"number": "4", "title": "Factories Come Up"},
            {"number": "4.1", "title": "The Early Entrepreneurs"},
            {"number": "4.2", "title": "Where Did the Workers Come From?"},
            {"number": "5", "title": "The Peculiarities of Industrial Growth"},
            {"number": "5.1", "title": "Small-scale Industries Predominate"},
            {"number": "6", "title": "Market for Goods"},
        ],
        "5": [  # jess305.pdf -- Print Culture and the Modern World
            {"number": "1", "title": "The First Printed Books"},
            {"number": "1.1", "title": "Print in Japan"},
            {"number": "2", "title": "Print Comes to Europe"},
            {"number": "2.1", "title": "Gutenberg and the Printing Press"},
            {"number": "3", "title": "The Print Revolution and Its Impact"},
            {"number": "3.1", "title": "A New Reading Public"},
            {"number": "3.2", "title": "Religious Debates and the Fear of Print"},
            {"number": "3.3", "title": "Print and Dissent"},
            {"number": "4", "title": "The Reading Mania"},
            {"number": "4.1", "title": "'Tremble, therefore, tyrants of the world!'"},
            {"number": "4.2", "title": "Print Culture and the French Revolution"},
            {"number": "5", "title": "The Nineteenth Century"},
            {"number": "5.1", "title": "Children, Women and Workers"},
            {"number": "5.2", "title": "Further Innovations"},
            {"number": "6", "title": "India and the World of Print"},
            {"number": "6.1", "title": "Manuscripts Before the Age of Print"},
            {"number": "6.2", "title": "Print Comes to India"},
            {"number": "7", "title": "Religious Reform and Public Debates"},
            {"number": "8", "title": "New Forms of Publication"},
            {"number": "8.1", "title": "Women and Print"},
            {"number": "8.2", "title": "Print and the Poor People"},
            {"number": "9", "title": "Print and Censorship"},
        ],
    },
    "X.POL": {
        "4": [  # jess404.pdf -- Political Parties -- proven against the real file
            {"number": "1", "title": "Why do we need political parties?"},
            {"number": "2", "title": "How many parties should we have?"},
            {"number": "3", "title": "National parties"},
            {"number": "4", "title": "State parties"},
            {"number": "5", "title": "Challenges to political parties"},
            {"number": "6", "title": "How can parties be reformed?"},
        ],
    },
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be set, without writing anything.",
    )
    args = parser.parse_args(argv)

    total_chapters = sum(len(v) for v in EXPECTED_SECTIONS.values())
    total_sections = sum(
        len(sections) for chapters in EXPECTED_SECTIONS.values() for sections in chapters.values()
    )
    print(f"{len(EXPECTED_SECTIONS)} subjects, {total_chapters} chapters, "
          f"{total_sections} sections total")

    if args.dry_run:
        for subject, chapters in EXPECTED_SECTIONS.items():
            for chapter_number, sections in chapters.items():
                print(f"  {subject} chapter {chapter_number}: {len(sections)} sections")
        return

    db = SessionLocal()
    try:
        for subject, chapters in EXPECTED_SECTIONS.items():
            body = ExpectedSectionsIn(chapters=chapters)
            result = set_expected_sections(subject, body, db)
            print(f"{subject}: set chapters {result['chapters_set']}")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
