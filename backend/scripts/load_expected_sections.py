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
  real file. Its list grew from 6 headings to 11 once app.ingest.book learned to combine
  more than one real heading size in a chapter (see below): "Meaning", "Functions",
  "Necessity", "Overview" and one truncated by a real PDF layout quirk ("Popular",
  short for "Popular participation in political parties") were real headings the first
  pass over this chapter never saw at all, not new content -- all five are named in the
  user's own topic list.

* Economics, chapters 1, 2, 3 and 5 ("Development", "Sectors of the Indian Economy",
  "Money and Credit", "Consumer Rights") -- these are the chapters that forced the fix
  above. None of them bolds ALL of its real headings uniformly, unlike every book tried
  before: "Money and Credit" prints its real headings at three different sizes in the
  same chapter (18pt for a named case study, 14pt for its major divisions, 12pt for a
  finer level), and the old "take only the single largest size" rule kept one of those
  three levels and silently discarded the other two -- not a smaller, incomplete list of
  headings, but a differently-shaped wrong one, since the one surviving level read as
  "the whole chapter" with nothing left to contradict it. Fixed generally in
  app.ingest.book's _sections_by_boldness (multi_size), with two more real fixes it
  needed along the way: a fake-bold heading drawn as several overlapping fragments
  ('HUMAN' / 'HUMAN DEVELOPMENT' / 'REPOR' / 'REPORT', all one real heading, "Human
  Development Report") had to be reassembled the same way _collapse_bold already does
  for the plain-text extraction path; and a running header/footer repeating the
  chapter's own title on every page had to be recognised and excluded once more than one
  heading level could let it through. All four chapters are proven against their real
  files in tests/test_sst_heading_detection.py, and each one's list below includes real
  content the user's own hand-typed list did not (a "Summing Up" closer, a small
  "Average Income" callout, a dialogue-style illustration named after its two
  characters) -- kept, not suppressed back to match the shorter original list, because
  the entire point of this fix was to stop missing real content.

UNVERIFIED_EXPECTED_SECTIONS, below, is the rest of what the user typed out for the whole
Social Science curriculum -- Geography's 7 chapters, Economics chapter 4
("Globalisation"), and Political Science chapters 1, 2, 3 and 5 -- none of it checked
against a real chapter file the way everything above was. Loaded anyway, on request:
these books number none of their own headings, so the list mixes chapter titles, major
headings and finer sub-points in one flat column with no marker for which is which, and
a wrong guess here does not fail silently -- `verify_against_toc` REJECTS the real
upload outright and names the exact section it expected but did not find, or found but
did not expect. That rejection is the point, not a bug to work around: it is the
loud, specific, checkable failure this whole exercise exists to produce instead of a
chapter that loads quietly wrong. Uploading these chapters and reading what comes back
(clean, or a named mismatch) is itself how the rest of Social Science gets verified --
send the mismatch (or the PDF, if the reason is not obvious from the error alone) and it
gets fixed and moved up into EXPECTED_SECTIONS above, the same way every chapter there
started out as somebody's typed list and ended up checked.
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
        "1": [  # jess401.pdf -- Power-sharing -- proven against the real file
            # This chapter's real headings ARE typographically detectable (bold pass,
            # not sparse), but two of its map captions -- "Communities and regions of
            # Belgium", "Ethnic Communities of Sri Lanka" -- are drawn bold at the same
            # size as a real heading and sit inline among them, exactly the class of
            # false positive Fig./Table/Graph captions are already excluded for, but
            # with no shared prefix to pattern-match against. Uploaded with
            # `?locate_known_sections=true` instead, which locates only these titles
            # directly and never considers the two captions at all.
            {"number": "1", "title": "Power-sharing"},
            {"number": "2", "title": "Belgium and Sri Lanka"},
            {"number": "3", "title": "Majoritarianism in Sri Lanka"},
            {"number": "4", "title": "Accommodation in Belgium"},
            {"number": "5", "title": "Why power sharing is desirable?"},
            {"number": "6", "title": "Khalil's dilemma"},
            {"number": "7", "title": "Forms of power-sharing"},
        ],
        "2": [  # jess402.pdf -- Federalism -- proven against the real file
            {"number": "1", "title": "Overview"},
            {"number": "2", "title": "What is federalism?"},
            {"number": "3", "title": "What makes India a federal country?"},
            {"number": "4", "title": "Linguistic States"},
            {"number": "5", "title": "How is federalism practised?"},
            {"number": "6", "title": "Language policy"},
            {"number": "7", "title": "Centre-State relations"},
            {"number": "8", "title": "Linguistic diversity of India"},
            {"number": "9", "title": "Scheduled Languages of India"},
            {"number": "10", "title": "Decentralisation in India"},
        ],
        "3": [  # jess403.pdf -- Gender, Religion and Caste -- proven against the real file
            # This chapter's bold pass finds only its 3 largest headings (sparse), so
            # the size-based fallback runs -- and that fallback also picks up two chart
            # captions, "Daily time use (hours: minutes)" and "Population of different
            # religious communities in India, 2011", each immediately followed by its
            # own "Source: ..." citation line rather than body prose. Uploaded with
            # `?locate_known_sections=true`, which never considers either caption.
            {"number": "1", "title": "Gender, Religion and Caste"},
            {"number": "2", "title": "Gender and politics"},
            {"number": "3", "title": "Public/private division"},
            {"number": "4", "title": "Women's political representation"},
            {"number": "5", "title": "Religion, communalism and politics"},
            {"number": "6", "title": "Communalism"},
            {"number": "7", "title": "Secular state"},
            {"number": "8", "title": "Caste and politics"},
            {"number": "9", "title": "Caste inequalities"},
            {"number": "10", "title": "Social and Religious Diversity of India"},
            {"number": "11", "title": "Caste in politics"},
            {"number": "12", "title": "Caste inequality today"},
            {"number": "13", "title": "Politics in caste"},
        ],
        "4": [  # jess404.pdf -- Political Parties -- proven against the real file
            {"number": "1", "title": "Overview"},
            {"number": "2", "title": "Why do we need political parties?"},
            # These four (3-7) were invisible to the first pass over this chapter, which
            # only ever found the bold path's largest single size cohort -- 6 major
            # headings. Once _sections_by_boldness could recognise more than one real
            # heading size in the same chapter (see its own docstring), these real,
            # finer-grained headings -- all named in the user's own topic list --
            # appeared too. Kept, not suppressed back down to 6: the point of the fix was
            # to stop missing real content, and an oracle that rejected this chapter for
            # finding MORE of its real structure than before would be exactly backwards.
            {"number": "3", "title": "Meaning"},
            {"number": "4", "title": "Functions"},
            {"number": "5", "title": "Necessity"},
            {"number": "6", "title": "How many parties should we have?"},
            # The real heading here is "Popular participation in political parties", laid
            # out across a narrow column in a word order pymupdf's text extraction does
            # not reassemble ('Popular / in / political parties / participation It is
            # often sai...') -- a real PDF layout quirk, not a bug introduced here. The
            # oracle has to match what the extractor actually produces, the same
            # accepted-truncation reasoning as History's own wrapped titles.
            {"number": "7", "title": "Popular"},
            {"number": "8", "title": "National parties"},
            {"number": "9", "title": "State parties"},
            {"number": "10", "title": "Challenges to political parties"},
            {"number": "11", "title": "How can parties be reformed?"},
        ],
        "5": [  # jess405.pdf -- Outcomes of Democracy -- proven against the real file
            # Same sparse-bold-pass-falls-back-to-size-based-pass issue as chapter 3:
            # one extra heading-shaped line, "Economic outcomes" (112 characters --
            # far too short to be its own section), gets pulled in alongside the real
            # headings. Uploaded with `?locate_known_sections=true`.
            {"number": "1", "title": "Outcomes of Democracy"},
            {"number": "2", "title": "How do we assess democracy's outcomes?"},
            {"number": "3", "title": "Accountable, responsive and legitimate government"},
            {"number": "4", "title": "Economic growth and development"},
            {"number": "5", "title": "Reduction of inequality and poverty"},
            {"number": "6", "title": "Accommodation of social diversity"},
            {"number": "7", "title": "Dignity and freedom of the citizens"},
        ],
    },
    "X.ECO": {
        "1": [  # jess201.pdf -- Development -- proven against the real file
            {"number": "1", "title": "WHAT DEVELOPMENT PROMISES — DIFFERENT PEOPLE, DIFFERENT GOALS"},
            {"number": "2", "title": "INCOME AND OTHER GOALS"},
            {"number": "3", "title": "NATIONAL DEVELOPMENT"},
            {"number": "4", "title": "HOW TO COMPARE DIFFERENT COUNTRIES OR STATES?"},
            {"number": "5", "title": "Average Income"},
            {"number": "6", "title": "INCOME AND OTHER CRITERIA"},
            {"number": "7", "title": "PUBLIC FACILITIES"},
            # Reassembled from four overlapping fake-bold draws ('HUMAN' x4, 'HUMAN
            # DEVELOPMENT' x1, 'REPOR' x4, 'REPORT' x1) -- one real heading, not four
            # fragments -- the same _collapse_bold-style merge the plain-text extraction
            # path already used, now applied to this per-span heading-detection view too.
            {"number": "8", "title": "HUMAN DEVELOPMENT REPORT"},
            {"number": "9", "title": "Example 1: Groundwater in India"},
            {"number": "10", "title": "SUSTAINABILITY OF DEVELOPMENT"},
            {"number": "11", "title": "Example 2: Exhaustion of Natural Resources"},
        ],
        "2": [  # jess202.pdf -- Sectors of the Indian Economy -- proven against the real file
            {"number": "1", "title": "SECTORS OF ECONOMIC ACTIVITIES"},
            {"number": "2", "title": "How do we count the various goods and services and know the total production in each sector?"},
            {"number": "3", "title": "COMPARING THE THREE SECTORS"},
            {"number": "4", "title": "Historical Change in Sectors"},
            {"number": "5", "title": "PRIMARY, SECONDARY AND TERTIARY SECTORS IN INDIA"},
            {"number": "6", "title": "Rising Importance of the Tertiary Sector in Production"},
            {"number": "7", "title": "Where are most of the people employed?"},
            {"number": "8", "title": "How to Create More Employment?"},
            {"number": "9", "title": "DIVISION OF SECTORS AS ORGANISED AND UNORGANISED"},
            # A real dialogue-style illustration, an unorganised-sector worker (Kanta)
            # contrasted with an organised-sector one (Kamal) -- not in the user's own
            # topic list for this chapter, but genuinely printed content under this
            # section, the same "kept, not suppressed" reasoning as Money and Credit's
            # own named case studies below.
            {"number": "10", "title": "Kanta"},
            {"number": "11", "title": "Kamal"},
            {"number": "12", "title": "How to Protect Workers in the Unorganised Sector?"},
            {"number": "13", "title": "SECTORS IN TERMS OF OWNERSHIP: PUBLIC AND PRIVATE SECTORS"},
            {"number": "14", "title": "SUMMING UP"},
        ],
        "3": [  # jess203.pdf -- Money and Credit -- proven against the real file
            {"number": "1", "title": "MONEY AS A MEDIUM OF EXCHANGE"},
            {"number": "2", "title": "Currency"},
            {"number": "3", "title": "Deposits with Banks"},
            {"number": "4", "title": "MODERN FORMS OF  MONEY"},
            {"number": "5", "title": "Cheque Payments"},
            {"number": "6", "title": "LOAN ACTIVITIES OF BANKS"},
            {"number": "7", "title": "(1) Festival Season"},
            {"number": "8", "title": "(2) Swapna’s Problem"},
            {"number": "9", "title": "TWO DIFFERENT CREDIT SITUATIONS"},
            {"number": "10", "title": "TERMS OF CREDIT"},
            {"number": "11", "title": "A House Loan"},
            {"number": "12", "title": "Variety of Credit Arrangements"},
            {"number": "13", "title": "Example of a Village"},
            {"number": "14", "title": "Loans from Cooperatives"},
            {"number": "15", "title": "FORMAL SECTOR CREDIT IN INDIA"},
            {"number": "16", "title": "Formal and Informal Credit: Who gets what?"},
            {"number": "17", "title": "SELF-HELP GROUPS FOR THE POOR"},
            {"number": "18", "title": "Grameen Bank of Bangladesh"},
            {"number": "19", "title": "SUMMING UP"},
        ],
        "5": [  # jess205.pdf -- Consumer Rights -- proven against the real file
            {"number": "1", "title": "THE CONSUMER IN THE MARKETPLACE"},
            {"number": "2", "title": "CONSUMER MOVEMENT"},
            {"number": "3", "title": "Consumers International"},
            {"number": "4", "title": "SAFETY IS EVERYONE’S RIGHT"},
            {"number": "5", "title": "Reji’s Suffering"},
            {"number": "6", "title": "Information about goods and services"},
            {"number": "7", "title": "Waiting..."},
            {"number": "8", "title": "When choice is denied"},
            {"number": "9", "title": "A Refund"},
            {"number": "10", "title": "Where should consumers go to get justice?"},
            {"number": "11", "title": "LEARNING TO BECOME WELL-INFORMED CONSUMERS"},
            {"number": "12", "title": "ISI and Agmark"},
            {"number": "13", "title": "TAKING THE CONSUMER MOVEMENT FORWARD"},
            {"number": "14", "title": "Books"},
            {"number": "15", "title": "Government Publications"},
        ],
        "4": [  # jess204.pdf -- Globalisation and the Indian Economy -- proven against the real file
            # This chapter's own boxed example ("Spreading of Production by an MNC") is
            # laid out by read_text's plain text extraction AHEAD of its own section
            # heading ("Production Across Countries"), even though it prints BELOW that
            # heading on the page -- a real PyMuPDF reading-order quirk for this page's
            # two-column-intro-then-full-width-box layout, not a transcription slip. Kept
            # in the order the extractor actually produces (see _pick_sections' own note
            # on why a shared search cursor can no longer assume list order matches text
            # order), the same "the oracle matches what the extractor produces"
            # reasoning as every truncated title elsewhere in this file.
            {"number": "1", "title": "Spreading  of Production by an MNC"},
            {"number": "2", "title": "PRODUCTION ACROSS COUNTRIES"},
            {"number": "3", "title": "INTERLINKING PRODUCTION ACROSS COUNTRIES"},
            {"number": "4", "title": "FOREIGN TRADE AND INTEGRATION OF MARKETS"},
            {"number": "5", "title": "Chinese Toys in India"},
            {"number": "6", "title": "WHAT IS GLOBALISATION?"},
            {"number": "7", "title": "Technology"},
            {"number": "8", "title": "Containers for transport of goods"},
            {"number": "9", "title": "FACTORS THAT HAVE ENABLED GLOBALISATION"},
            # Truncated at its real wrapped second line, the same accepted gap History's
            # own numbered headings have (see EXPECTED_SECTIONS["X.HIST"]'s own note):
            # the real heading is "Using IT in Globalisation".
            {"number": "10", "title": "Using IT in"},
            {"number": "11", "title": "Liberalisation of foreign trade and foreign investment policy"},
            {"number": "12", "title": "WORLD TRADE ORGANISATION"},
            {"number": "13", "title": "Debate on Trade Practices"},
            {"number": "14", "title": "IMPACT OF GLOBALISATION IN INDIA"},
            {"number": "15", "title": "Steps to Attract Foreign Investment"},
            {"number": "16", "title": "Small producers: Compete or perish"},
            {"number": "17", "title": "Rising Competition"},
            {"number": "18", "title": "Competition and Uncertain Employment"},
            {"number": "19", "title": "A Garment Worker"},
            {"number": "20", "title": "THE STRUGGLE FOR A FAIR GLOBALISATION"},
            {"number": "21", "title": "SUMMING UP"},
        ],
    },
    "X.GEO": {
        "1": [  # jess101.pdf -- Resources and Development -- proven against the real file
            # Geography publishes no section numbers of its own, and none of the usual
            # typographic signals (boldness, size-above-body, colour) reliably separate a
            # real heading from a diagram caption, a table cell or the chapter's own body
            # prose in this book -- see app.ingest.book's _locate_known_sections, which
            # this chapter is the reason for. Uploaded with `?locate_known_sections=true`,
            # which locates these titles directly in the chapter's own text instead of
            # guessing structure from typography, then renumbers by where each was
            # actually FOUND -- not the order given here, which is why this list's own
            # order (matching the user's original topic list) does not match the numbers
            # a real upload reports: "Land Resources" is typed before "Land Utilisation"
            # here, but genuinely printed after it in the book.
            {"number": "1", "title": "Resources and Development"},
            {"number": "2", "title": "Development of Resources"},
            {"number": "3", "title": "Sustainable development"},
            {"number": "4", "title": "Rio de Janeiro Earth Summit, 1992"},
            {"number": "5", "title": "Agenda 21"},
            {"number": "6", "title": "Resource Planning"},
            {"number": "7", "title": "Conservation of Resources"},
            {"number": "8", "title": "Resource Planning in India"},
            {"number": "9", "title": "Land Resources"},
            {"number": "10", "title": "Land Utilisation"},
            {"number": "11", "title": "Land Use Pattern in India"},
            {"number": "12", "title": "Land Degradation and Conservation Measures"},
            {"number": "13", "title": "Soil as a Resource"},
            {"number": "14", "title": "Classification of Soils"},
            {"number": "15", "title": "Alluvial Soils"},
            {"number": "16", "title": "Black Soil"},
            {"number": "17", "title": "Red and Yellow Soils"},
            {"number": "18", "title": "Laterite Soil"},
            {"number": "19", "title": "Arid Soils"},
            {"number": "20", "title": "Forest Soils"},
            {"number": "21", "title": "Soil Erosion and Soil Conservation"},
        ],
        "2": [  # jess102.pdf -- Forest and Wildlife Resources -- proven against the real file
            # "Joint Forest Management" was in the user's own topic list but does not
            # exist as a real heading anywhere in this chapter -- confirmed against the
            # real file: it appears only once, lower-case, inside an unrelated sentence
            # ("In India joint forest management (JFM) programme..."), with no bold or
            # larger-than-body styling anywhere near it. Left out rather than invented.
            {"number": "1", "title": "Flora and Fauna in India"},
            {"number": "2", "title": "Conservation of Forest and Wildlife in India"},
            {"number": "3", "title": "Project Tiger"},
            {"number": "4", "title": "Forest and Wildlife Resources"},
            {"number": "5", "title": "Reserved Forests"},
            {"number": "6", "title": "Types and Distribution of Forest and Wildlife Resources"},
            {"number": "7", "title": "Community and Conservation"},
            {"number": "8", "title": "Sacred groves - a wealth of diverse and rare species"},
            {"number": "9", "title": "Protected Forests"},
            {"number": "10", "title": "Unclassed Forests"},
        ],
        "3": [  # jess103.pdf -- Water Resources -- proven against the real file
            # "Multi-purpose River Projects and Integrated Water Resources Management"
            # was in the user's own topic list but does not exist as a real heading --
            # confirmed against the real file the same way as chapter 2's own omission.
            {"number": "1", "title": "Water Scarcity and the Need for Water Conservation and Management"},
            {"number": "2", "title": "Water Resources"},
            {"number": "3", "title": "Hydraulic Structures in Ancient India"},
            {"number": "4", "title": "Rainwater Harvesting"},
            {"number": "5", "title": "Bamboo Drip Irrigation System"},
        ],
        "4": [  # jess104.pdf -- Agriculture -- proven against the real file
            # "Horticulture Crops", "Non-Food Crops" and "Technological and
            # Institutional Reforms" were in the user's own topic list but do not exist
            # as real headings in this chapter -- confirmed the same way as chapter 2's
            # own omission. "Bhoodan - Gramdan" is a real heading, but printed with an en
            # dash ("Bhoodan – Gramdan") -- matched by _locate_known_sections' own dash
            # folding regardless of which is typed here.
            {"number": "1", "title": "Coffee"},
            {"number": "2", "title": "Types of Farming"},
            {"number": "3", "title": "Primitive Subsistence Farming"},
            {"number": "4", "title": "Jhumming: The 'slash and burn' agriculture"},
            {"number": "5", "title": "Intensive Subsistence Farming"},
            {"number": "6", "title": "Commercial Farming"},
            {"number": "7", "title": "Agriculture"},
            {"number": "8", "title": "Cropping Pattern"},
            {"number": "9", "title": "Major Crops"},
            {"number": "10", "title": "Rice"},
            {"number": "11", "title": "Wheat"},
            {"number": "12", "title": "Millets"},
            {"number": "13", "title": "Maize"},
            {"number": "14", "title": "Oil Seeds"},
            {"number": "15", "title": "Tea"},
            {"number": "16", "title": "Pulses"},
            {"number": "17", "title": "Food Crops other than Grains"},
            {"number": "18", "title": "Sugarcane"},
            {"number": "19", "title": "Rubber"},
            {"number": "20", "title": "Jute"},
            {"number": "21", "title": "Fibre Crops"},
            {"number": "22", "title": "Cotton"},
            {"number": "23", "title": "Bhoodan - Gramdan"},
        ],
        "5": [  # jess105.pdf -- Minerals and Energy Resources -- proven against the real file
            {"number": "1", "title": "A bright smile from toothpaste and minerals"},
            {"number": "2", "title": "All living things need minerals"},
            {"number": "3", "title": "What is a mineral?"},
            {"number": "4", "title": "Study of Minerals by Geographers and Geologists"},
            {"number": "5", "title": "Mode of Occurrence of Minerals"},
            {"number": "6", "title": "Minerals and Energy Resources"},
            {"number": "7", "title": "Rat-Hole Mining"},
            {"number": "8", "title": "Ferrous Minerals"},
            {"number": "9", "title": "Iron Ore"},
            {"number": "10", "title": "Manganese"},
            {"number": "11", "title": "Non-Ferrous Minerals"},
            {"number": "12", "title": "Copper"},
            {"number": "13", "title": "Bauxite"},
            {"number": "14", "title": "Non-Metallic Minerals"},
            {"number": "15", "title": "Mica"},
            {"number": "16", "title": "Rock Minerals"},
            {"number": "17", "title": "Hazards of Mining"},
            {"number": "18", "title": "Conservation of Minerals"},
            {"number": "19", "title": "Energy Resources"},
            {"number": "20", "title": "Conventional Sources of Energy"},
            {"number": "21", "title": "Coal"},
            {"number": "22", "title": "Petroleum"},
            {"number": "23", "title": "Natural Gas"},
            {"number": "24", "title": "Electricity"},
            {"number": "25", "title": "Non-Conventional Sources of Energy"},
            {"number": "26", "title": "Nuclear or Atomic Energy"},
            {"number": "27", "title": "Solar Energy"},
            {"number": "28", "title": "Wind power"},
            {"number": "29", "title": "Biogas"},
            {"number": "30", "title": "Conservation of Energy Resources"},
            {"number": "31", "title": "Tidal Energy"},
            {"number": "32", "title": "Geo Thermal Energy"},
        ],
        "6": [  # jess106.pdf -- Manufacturing Industries -- proven against the real file
            {"number": "1", "title": "Importance of Manufacturing"},
            {"number": "2", "title": "Manufacturing Industries"},
            {"number": "3", "title": "Classification of Industries"},
            {"number": "4", "title": "Agro-based Industries"},
            {"number": "5", "title": "Cotton Textiles"},
            {"number": "6", "title": "Jute Textiles"},
            {"number": "7", "title": "Textile Industry"},
            {"number": "8", "title": "Mineral-based Industries"},
            {"number": "9", "title": "Iron and Steel Industry"},
            {"number": "10", "title": "Sugar Industry"},
            {"number": "11", "title": "Aluminium Smelting"},
            {"number": "12", "title": "Chemical Industries"},
            {"number": "13", "title": "Fertilizer Industry"},
            {"number": "14", "title": "Cement Industry"},
            {"number": "15", "title": "Automobile Industry"},
            {"number": "16", "title": "Information Technology and Electronics Industry"},
            {"number": "17", "title": "Industrial Pollution and Environmental Degradation"},
            {"number": "18", "title": "Control of Environmental Degradation"},
            {"number": "19", "title": "NTPC shows the way"},
        ],
        "7": [  # jess107.pdf -- Lifelines of National Economy -- proven against the real file
            # "Airways" was in the user's own topic list but does not exist as its own
            # heading in this edition -- confirmed against the real file: the chapter
            # goes straight from "Major Sea Ports" to "International Trade", with no
            # standalone Airways/Air Transport section anywhere in between.
            {"number": "1", "title": "Transport"},
            {"number": "2", "title": "Roadways"},
            {"number": "3", "title": "Golden Quadrilateral Super Highways"},
            {"number": "4", "title": "National Highways"},
            {"number": "5", "title": "State Highways"},
            {"number": "6", "title": "District Roads"},
            {"number": "7", "title": "Other Roads"},
            {"number": "8", "title": "Border Roads"},
            {"number": "9", "title": "Lifelines of National Economy"},
            {"number": "10", "title": "Railways"},
            {"number": "11", "title": "Pipelines"},
            {"number": "12", "title": "Major Sea Ports"},
            {"number": "13", "title": "Regional Connectivity Scheme (RCS) - UDAN"},
            {"number": "14", "title": "Communication"},
            {"number": "15", "title": "Waterways"},
            {"number": "16", "title": "International Trade"},
            {"number": "17", "title": "Digital India"},
            {"number": "18", "title": "Tourism as a Trade"},
        ],
    },
    "X.SCI": {
        # Unlike every Social Science book above, Science genuinely numbers its own
        # headings two decimal levels deep (chapter.section AND chapter.section.
        # subsection, e.g. '1.1.1 Writing a Chemical Equation' under '1.1 Chemical
        # Equations') -- extract_sections used to match only the first level, silently
        # missing every real subsection a chapter has. Fixed to match both levels; see
        # extract_sections' own docstring. These numbers are exactly what the fixed
        # extractor finds, proven against the real files.
        "1": [  # jesc101.pdf -- Chemical Reactions and Equations
            {"number": "1.1", "title": "CHEMICAL EQUATIONS"},
            {"number": "1.1.1", "title": "Writing a Chemical Equation"},
            {"number": "1.1.2", "title": "Balanced Chemical Equations"},
            {"number": "1.2", "title": "TYPES OF CHEMICAL REACTIONS"},
            {"number": "1.2.1", "title": "Combination Reaction"},
            {"number": "1.2.2", "title": "Decomposition Reaction"},
            {"number": "1.2.3", "title": "Displacement Reaction"},
            {"number": "1.2.4", "title": "Double Displacement Reaction"},
            {"number": "1.2.5", "title": "Oxidation and Reduction"},
            {"number": "1.3", "title": "HAVE YOU OBSERVED THE EFFECTS OF OXIDATION REACTIONS IN EVERYDAY LIFE?"},
            {"number": "1.3.1", "title": "Corrosion"},
            {"number": "1.3.2", "title": "Rancidity"},
        ],
        "2": [  # jesc102.pdf -- Acids, Bases and Salts
            {"number": "2.1", "title": "UNDERSTANDING THE CHEMICAL PROPERTIES OF ACIDS AND BASES"},
            {"number": "2.1.1", "title": "Acids and Bases in the Laboratory"},
            {"number": "2.1.2", "title": "How do Acids and Bases React with Metals?"},
            # Real title wraps to a second physical line ("Hydrogencarbonates React with
            # Acids?") that a single-line pattern cannot reach -- the same accepted
            # truncation this project already keeps for other subjects' own wrapped
            # titles (History, Political Parties' "Popular") rather than a bug to chase.
            {"number": "2.1.3", "title": "How do Metal Carbonates and Metal"},
            # Printed out of numeric order in the book's own two-column layout: 2.1.5's
            # real text sits ahead of 2.1.4's in the plain-text extraction, the same
            # class of layout quirk Economics' "Spreading of Production" chapter has.
            # verify_against_toc compares by NUMBER, never by order, so this is harmless.
            {"number": "2.1.4", "title": "How do Acids and Bases React with each other?"},
            {"number": "2.1.5", "title": "Reaction of Metallic Oxides with Acids"},
            {"number": "2.1.6", "title": "Reaction of a Non-metallic Oxide with Base"},
            {"number": "2.2", "title": "WHAT DO ALL ACIDS AND ALL BASES HAVE IN COMMON?"},
            {"number": "2.2.1", "title": "What Happens to an Acid or a Base in a Water Solution?"},
            {"number": "2.3", "title": "HOW STRONG ARE ACID OR BASE SOLUTIONS?"},
            # This one heading is drawn on the page as four overlapping, truncated
            # "2.3.1 Impor" copies (a faux-bold rendering trick) plus one real, longer
            # line, itself wrapped -- extract_sections now keeps the longest candidate
            # for a repeated number rather than the first, but the real title still
            # wraps past what one line can reach; see extract_sections' own note.
            {"number": "2.3.1", "title": "Importance of pH in Ever"},
            {"number": "2.4", "title": "MORE ABOUT SALTS"},
            {"number": "2.4.1", "title": "Family of Salts"},
            # Real heading correctly starts with a lowercase 'p' -- 'pH' is the actual
            # chemistry notation, not a typo, and extract_sections now allows it as an
            # explicit exception to the usual capital-letter-first rule.
            {"number": "2.4.2", "title": "pH of Salts"},
            {"number": "2.4.3", "title": "Chemicals from Common Salt"},
            {"number": "2.4.4", "title": "Are the Crystals of Salts really Dry?"},
        ],
        "3": [  # jesc103.pdf -- Metals and Non-metals
            {"number": "3.1", "title": "PHYSICAL PROPERTIES"},
            {"number": "3.1.1", "title": "Metals"},
            {"number": "3.1.2", "title": "Non-metals"},
            {"number": "3.2", "title": "CHEMICAL PROPERTIES OF METALS"},
            {"number": "3.2.1", "title": "What happens when Metals are burnt in Air?"},
            {"number": "3.2.2", "title": "What happens when Metals react with Water?"},
            {"number": "3.2.3", "title": "What happens when Metals react with Acids?"},
            # Wraps to a second physical line ("Salts?") -- same accepted truncation as
            # 2.1.3 above.
            {"number": "3.2.4", "title": "How do Metals react with Solutions of other Metal"},
            {"number": "3.2.5", "title": "The Reactivity Series"},
            {"number": "3.3", "title": "HOW DO METALS AND NON-METALS REACT?"},
            {"number": "3.3.1", "title": "Properties of Ionic Compounds"},
            {"number": "3.4", "title": "OCCURRENCE OF METALS"},
            {"number": "3.4.1", "title": "Extraction of Metals"},
            {"number": "3.4.2", "title": "Enrichment of Ores"},
            {"number": "3.4.3", "title": "Extracting Metals Low in the Activity Series"},
            {"number": "3.4.4", "title": "Extracting Metals in the Middle of the Activity Series"},
            # Wraps to a second physical line ("Activity Series") -- same accepted
            # truncation as 2.1.3 above.
            {"number": "3.4.5", "title": "Extracting Metals towards the Top of the"},
            {"number": "3.4.6", "title": "Refining of Metals"},
            {"number": "3.5", "title": "CORROSION"},
            {"number": "3.5.1", "title": "Prevention of Corrosion"},
        ],
        "4": [  # jesc104.pdf -- Carbon and its Compounds
            {"number": "4.1", "title": "BONDING IN CARBON – THE COVALENT BOND"},
            {"number": "4.2", "title": "VERSATILE NATURE OF CARBON"},
            {"number": "4.2.1", "title": "Saturated and Unsaturated Carbon Compounds"},
            {"number": "4.2.2", "title": "Chains, Branches and Rings"},
            {"number": "4.2.3", "title": "Will you be my Friend?"},
            {"number": "4.2.4", "title": "Homologous Series"},
            {"number": "4.2.5", "title": "Nomenclature of Carbon Compounds"},
            {"number": "4.3", "title": "CHEMICAL PROPERTIES OF CARBON COMPOUNDS"},
            {"number": "4.3.1", "title": "Combustion"},
            {"number": "4.3.2", "title": "Oxidation"},
            {"number": "4.3.3", "title": "Addition Reaction"},
            {"number": "4.3.4", "title": "Substitution Reaction"},
            {"number": "4.4", "title": "SOME IMPORTANT CARBON COMPOUNDS – ETHANOL"},
            {"number": "4.4.1", "title": "Properties of Ethanol"},
            {"number": "4.4.2", "title": "Properties of Ethanoic Acid"},
            {"number": "4.5", "title": "SOAPS AND DETERGENTS"},
        ],
        "5": [  # jesc105.pdf -- Life Processes
            {"number": "5.1", "title": "WHAT ARE LIFE PROCESSES?"},
            {"number": "5.2", "title": "NUTRITION"},
            {"number": "5.2.1", "title": "Autotrophic Nutrition"},
            {"number": "5.2.2", "title": "Heterotrophic Nutrition"},
            {"number": "5.2.3", "title": "How do Organisms obtain their Nutrition?"},
            {"number": "5.2.4", "title": "Nutrition in Human Beings"},
            {"number": "5.3", "title": "RESPIRATION"},
            {"number": "5.4", "title": "TRANSPORTATION"},
            {"number": "5.4.1", "title": "Transportation in Human Beings"},
            {"number": "5.4.2", "title": "Transportation in Plants"},
            {"number": "5.5", "title": "EXCRETION"},
            {"number": "5.5.1", "title": "Excretion in Human Beings"},
            {"number": "5.5.2", "title": "Excretion in Plants"},
        ],
        "6": [  # jesc106.pdf -- Control and Coordination
            {"number": "6.1", "title": "ANIMALS – NERVOUS SYSTEM"},
            {"number": "6.1.1", "title": "What happens in Reflex Actions?"},
            {"number": "6.1.2", "title": "Human Brain"},
            {"number": "6.1.3", "title": "How are these Tissues protected?"},
            {"number": "6.1.4", "title": "How does the Nervous Tissue cause Action?"},
            {"number": "6.2", "title": "COORDINATION IN PLANTS"},
            {"number": "6.2.1", "title": "Immediate Response to Stimulus"},
            {"number": "6.2.2", "title": "Movement Due to Growth"},
            {"number": "6.3", "title": "HORMONES IN ANIMALS"},
        ],
        "7": [  # jesc107.pdf -- How do Organisms Reproduce?
            # A THIRD level under a two-decimal section switches from another digit to a
            # parenthesised letter instead ('7.3.3 (a)', '(b)', '(c)', '(d)') -- confirmed
            # necessary here: 4 real headings under "Reproduction in Human Beings" (7.3.3)
            # were invisible until extract_sections matched this convention as its own
            # alternative. See extract_sections' own docstring.
            {"number": "7.1", "title": "DO ORGANISMS CREATE EXACT COPIES OF THEMSELVES?"},
            {"number": "7.1.1", "title": "The Importance of Variation"},
            {"number": "7.2", "title": "MODES OF REPRODUCTION USED BY SINGLE ORGANISMS"},
            {"number": "7.2.1", "title": "Fission"},
            {"number": "7.2.2", "title": "Fragmentation"},
            {"number": "7.2.3", "title": "Regeneration"},
            {"number": "7.2.4", "title": "Budding"},
            {"number": "7.2.5", "title": "Vegetative Propagation"},
            {"number": "7.2.6", "title": "Spore Formation"},
            {"number": "7.3", "title": "SEXUAL REPRODUCTION"},
            {"number": "7.3.1", "title": "Why the Sexual Mode of Reproduction?"},
            {"number": "7.3.2", "title": "Sexual Reproduction in Flowering Plants"},
            {"number": "7.3.3", "title": "Reproduction in Human Beings"},
            {"number": "7.3.3 (a)", "title": "Male Reproductive System"},
            {"number": "7.3.3 (b)", "title": "Female Reproductive System"},
            {"number": "7.3.3 (c)", "title": "What happens when the Egg is not Fertilised?"},
            {"number": "7.3.3 (d)", "title": "Reproductive Health"},
        ],
        "8": [  # jesc108.pdf -- Heredity -- proven against the real file. Typed from
            # real page images rather than run through the extractor here directly (the
            # real file itself could not be uploaded to this session), but a real
            # production upload of the actual PDF verified clean against this exact
            # list -- no 422, so the extractor's own read of the real bytes agrees.
            {"number": "8.1", "title": "ACCUMULATION OF VARIATION DURING REPRODUCTION"},
            {"number": "8.2", "title": "HEREDITY"},
            {"number": "8.2.1", "title": "Inherited Traits"},
            {"number": "8.2.2", "title": "Rules for the Inheritance of Traits –"},
            {"number": "8.2.3", "title": "How do these Traits get Expressed?"},
            {"number": "8.2.4", "title": "Sex Determination"},
        ],
        "9": [  # jesc109.pdf -- Light -- Reflection and Refraction
            {"number": "9.1", "title": "REFLECTION OF LIGHT"},
            {"number": "9.2", "title": "SPHERICAL MIRRORS"},
            {"number": "9.2.1", "title": "Image Formation by Spherical Mirrors"},
            # Wraps to a second physical line ("Mirrors Using Ray Diagrams") -- same
            # accepted truncation as chapters 2 and 3's own wrapped titles.
            {"number": "9.2.2", "title": "Representation of Images Formed by Spherical"},
            {"number": "9.2.3", "title": "Sign Convention for Reflection by Spherical Mirrors"},
            {"number": "9.2.4", "title": "Mirror Formula and  Magnification"},
            {"number": "9.3", "title": "REFRACTION OF LIGHT"},
            {"number": "9.3.1", "title": "Refraction through a Rectangular Glass Slab"},
            {"number": "9.3.2", "title": "The Refractive Index"},
            {"number": "9.3.3", "title": "Refraction by Spherical Lenses"},
            {"number": "9.3.4", "title": "Image Formation by Lenses"},
            {"number": "9.3.5", "title": "Image Formation in Lenses Using Ray Diagrams"},
            {"number": "9.3.6", "title": "Sign Convention for Spherical Lenses"},
            {"number": "9.3.7", "title": "Lens Formula and Magnification"},
            {"number": "9.3.8", "title": "Power of a Lens"},
        ],
        "10": [  # jesc110.pdf -- The Human Eye and the Colourful World
            {"number": "10.1", "title": "THE HUMAN EYE"},
            {"number": "10.1.1", "title": "Power of Accommodation"},
            {"number": "10.2", "title": "DEFECTS OF VISION AND THEIR CORRECTION"},
            {"number": "10.3", "title": "REFRACTION OF LIGHT THROUGH A PRISM"},
            {"number": "10.4", "title": "DISPERSION OF WHITE LIGHT BY A GLASS PRISM"},
            {"number": "10.5", "title": "ATMOSPHERIC REFRACTION"},
            {"number": "10.6", "title": "SCATTERING OF LIGHT"},
            {"number": "10.6.1", "title": "Tyndall Effect"},
            {"number": "10.6.2", "title": "Why is the colour of the clear Sky Blue?"},
        ],
        "11": [  # jesc111.pdf -- Electricity
            {"number": "11.1", "title": "ELECTRIC CURRENT AND CIRCUIT"},
            {"number": "11.2", "title": "ELECTRIC POTENTIAL AND POTENTIAL DIFFERENCE"},
            {"number": "11.3", "title": "CIRCUIT DIAGRAM"},
            {"number": "11.4", "title": "OHM’S LAW"},
            {"number": "11.5", "title": "FACTORS ON WHICH THE RESISTANCE OF A CONDUCTOR DEPENDS"},
            {"number": "11.6", "title": "RESISTANCE OF A SYSTEM OF RESISTORS"},
            {"number": "11.6.1", "title": "Resistors in Series"},
            {"number": "11.6.2", "title": "Resistors in Parallel"},
            {"number": "11.7", "title": "HEATING EFFECT OF ELECTRIC CURRENT"},
            # Wraps to a second physical line ("Electric Current") -- same accepted
            # truncation as earlier chapters' own wrapped titles.
            {"number": "11.7.1", "title": "Practical Applications of Heating Effect of"},
            {"number": "11.8", "title": "ELECTRIC POWER"},
        ],
        "12": [  # jesc112.pdf -- Magnetic Effects of Electric Current
            {"number": "12.1", "title": "MAGNETIC FIELD AND FIELD LINES"},
            {"number": "12.2", "title": "MAGNETIC FIELD DUE TO A CURRENT-CARRYING CONDUCTOR"},
            # Wraps to a second physical line ("Conductor") -- same accepted truncation.
            {"number": "12.2.1", "title": "Magnetic Field due to a Current through a Straight"},
            {"number": "12.2.2", "title": "Right-Hand Thumb Rule"},
            # Wraps to a second physical line ("Circular Loop") -- same accepted
            # truncation.
            {"number": "12.2.3", "title": "Magnetic Field due to a Current through a"},
            {"number": "12.2.4", "title": "Magnetic Field due to a Current in a Solenoid"},
            {"number": "12.3", "title": "FORCE ON A CURRENT-CARRYING CONDUCTOR IN A MAGNETIC FIELD"},
            {"number": "12.4", "title": "DOMESTIC ELECTRIC CIRCUITS"},
        ],
        "13": [  # jesc113.pdf -- Our Environment
            {"number": "13.1", "title": "ECO-SYSTEM — WHAT ARE ITS COMPONENTS?"},
            {"number": "13.1.1", "title": "Food Chains and Webs"},
            {"number": "13.2", "title": "HOW DO OUR ACTIVITIES AFFECT THE ENVIRONMENT?"},
            {"number": "13.2.1", "title": "Ozone Layer and How it is Getting Depleted"},
            {"number": "13.2.2", "title": "Managing the Garbage we Produce"},
        ],
    },
    "X.MATH": {
        # Maths' own contents page lists every section of every chapter, so a real
        # upload already gets checked against it "for free" by parse_toc/verify_against_
        # toc without needing this oracle at all. Filled in anyway, the same as every
        # other subject, so the chapters that reach here are proven a second, independent
        # way and every future extraction fix has a real regression to run against.
        # Numbers here are exactly what the fixed extract_sections finds, proven against
        # the real files -- one decimal level ('1.1'), except chapter 3's own '3.3.1' /
        # '3.3.2', which the book itself numbers one level deeper under '3.3'.
        "1": [  # jemh101.pdf -- Real Numbers
            {"number": "1.1", "title": "Introduction"},
            {"number": "1.2", "title": "The Fundamental Theorem of Arithmetic"},
            {"number": "1.3", "title": "Revisiting Irrational Numbers"},
            {"number": "1.4", "title": "Summary"},
        ],
        "2": [  # jemh102.pdf -- Polynomials
            {"number": "2.1", "title": "Introduction"},
            {"number": "2.2", "title": "Geometrical Meaning of the Zeroes of a Polynomial"},
            {"number": "2.3", "title": "Relationship between Zeroes and Coefficients of a Polynomial"},
            {"number": "2.4", "title": "Summary"},
        ],
        "3": [  # jemh103.pdf -- Pair of Linear Equations in Two Variables
            {"number": "3.1", "title": "Introduction"},
            {"number": "3.2", "title": "Graphical Method of Solution of a Pair of Linear Equations"},
            {"number": "3.3", "title": "Algebraic Methods of Solving a Pair of Linear Equations"},
            # The PDF's own text layer runs this heading onto the same physical line as
            # its opening sentence ("Substitution Method : We shall explain the method of
            # substitution by taking") -- extract_sections used to keep the whole line as
            # the title. Fixed to truncate at NCERT's own ' : ' separator; see
            # extract_sections' own docstring.
            {"number": "3.3.1", "title": "Substitution Method"},
            {"number": "3.3.2", "title": "Elimination Method"},
            {"number": "3.4", "title": "Summary"},
        ],
        "4": [  # jemh104.pdf -- Quadratic Equations
            {"number": "4.1", "title": "Introduction"},
            {"number": "4.2", "title": "Quadratic Equations"},
            {"number": "4.3", "title": "Solution of a Quadratic Equation by Factorisation"},
            {"number": "4.4", "title": "Nature of Roots"},
            {"number": "4.5", "title": "Summary"},
        ],
        "5": [  # jemh105.pdf -- Arithmetic Progressions
            {"number": "5.1", "title": "Introduction"},
            {"number": "5.2", "title": "Arithmetic Progressions"},
            # 'nth' is standard mathematical notation, not a typo -- extract_sections
            # used to require a capital first letter and silently dropped this section
            # entirely, the same way Science's 'pH of Salts' did before its own
            # exception was added.
            {"number": "5.3", "title": "nth Term of an AP"},
            {"number": "5.4", "title": "Sum of First n Terms of an AP"},
            {"number": "5.5", "title": "Summary"},
        ],
    },
}


#: Every chapter typed in here starts life unverified against any real file -- see this
#: module's own docstring for exactly what that means and why it is loaded anyway. A real
#: upload against an unverified entry may well come back 422, naming the exact section it
#: expected but the book does not have (or has, but not by that exact name/position).
#: That is the intended, informative failure mode, not a bug: report it and the entry
#: gets corrected and moved up into EXPECTED_SECTIONS above, the same way every chapter
#: there started out.
#: Every X.SCI chapter has now been verified against a real file and moved up into
#: EXPECTED_SECTIONS -- nothing unverified remains for any subject at the moment.
UNVERIFIED_EXPECTED_SECTIONS: dict[str, dict[str, list[dict[str, str]]]] = {}


def _merged(*dicts: dict[str, dict[str, list[dict[str, str]]]]) -> dict[str, dict[str, list[dict[str, str]]]]:
    out: dict[str, dict[str, list[dict[str, str]]]] = {}
    for d in dicts:
        for subject, chapters in d.items():
            out.setdefault(subject, {}).update(chapters)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be set, without writing anything.",
    )
    parser.add_argument(
        "--verified-only", action="store_true",
        help=(
            "Load only the chapters already checked against a real file "
            "(EXPECTED_SECTIONS), skipping UNVERIFIED_EXPECTED_SECTIONS entirely."
        ),
    )
    args = parser.parse_args(argv)

    to_load = EXPECTED_SECTIONS if args.verified_only else _merged(
        EXPECTED_SECTIONS, UNVERIFIED_EXPECTED_SECTIONS,
    )
    verified_chapters = {
        (subject, chapter) for subject, chapters in EXPECTED_SECTIONS.items() for chapter in chapters
    }

    total_chapters = sum(len(v) for v in to_load.values())
    total_sections = sum(len(s) for chapters in to_load.values() for s in chapters.values())
    print(f"{len(to_load)} subjects, {total_chapters} chapters, {total_sections} sections total "
          f"({'verified only' if args.verified_only else 'verified + unverified'})")

    if args.dry_run:
        for subject, chapters in to_load.items():
            for chapter_number, sections in chapters.items():
                tag = "verified" if (subject, chapter_number) in verified_chapters else "UNVERIFIED"
                print(f"  {subject} chapter {chapter_number}: {len(sections)} sections [{tag}]")
        return

    db = SessionLocal()
    try:
        for subject, chapters in to_load.items():
            body = ExpectedSectionsIn(chapters=chapters)
            result = set_expected_sections(subject, body, db)
            unverified_here = [c for c in result["chapters_set"] if (subject, c) not in verified_chapters]
            print(f"{subject}: set chapters {result['chapters_set']}"
                  + (f" (unverified: {unverified_here})" if unverified_here else ""))
    finally:
        db.close()

    if not args.verified_only:
        print(
            "\nUnverified chapters above are a best-effort guess, not a checked fact -- "
            "upload their real PDFs next. A clean verify means it matched; a 422 means "
            "it didn't, and names the exact section it expected or didn't expect. Either "
            "way, report the result so it can be corrected and moved into "
            "EXPECTED_SECTIONS for good."
        )


if __name__ == "__main__":
    sys.exit(main())
