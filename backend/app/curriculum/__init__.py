"""Board units and their weightage: the layer that does not come from the book.

CBSE publishes weightage per *unit*, and a unit may span several chapters (Algebra covers
four) or exist where no chapter does (English's Reading section). The book never states
this -- it is a syllabus fact -- so it is defined here with a citation and applied before
any book is loaded.

One source, used by both `scripts.seed` and the operator console, so a deployment that
cannot run a shell is not a second-class one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SYLLABUS_URL = "https://cbseacademic.nic.in/"


@dataclass(frozen=True)
class BoardUnit:
    code: str
    label: str
    weight_pct: float


@dataclass(frozen=True)
class Chapter:
    code: str
    label: str
    board_unit: str


@dataclass(frozen=True)
class Curriculum:
    subject_code: str
    subject_label: str
    grade: int
    units: list[BoardUnit]
    chapters: list[Chapter]
    #: stable trend axes, curated rather than extracted -- renaming one after a class has
    #: been tested breaks every comparison that references it
    concept_families: list[tuple[str, str, str]] = field(default_factory=list)
    source_doc_url: str = SYLLABUS_URL


X_MATH = Curriculum(
    subject_code="X.MATH",
    subject_label="Class X Mathematics",
    grade=10,
    units=[
        BoardUnit("X.MATH.U.NUMBER", "Number Systems", 6.0),
        BoardUnit("X.MATH.U.ALGEBRA", "Algebra", 20.0),
        BoardUnit("X.MATH.U.COORD", "Coordinate Geometry", 6.0),
        BoardUnit("X.MATH.U.GEOMETRY", "Geometry", 15.0),
        BoardUnit("X.MATH.U.TRIG", "Trigonometry", 12.0),
        BoardUnit("X.MATH.U.MENSURATION", "Mensuration", 10.0),
        BoardUnit("X.MATH.U.STATSPROB", "Statistics & Probability", 11.0),
    ],
    chapters=[
        Chapter("X.MATH.REAL", "Real Numbers", "X.MATH.U.NUMBER"),
        Chapter("X.MATH.POLY", "Polynomials", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.LINEQ", "Pair of Linear Equations", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.QUAD", "Quadratic Equations", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.AP", "Arithmetic Progressions", "X.MATH.U.ALGEBRA"),
        Chapter("X.MATH.TRIANGLE", "Triangles", "X.MATH.U.GEOMETRY"),
        Chapter("X.MATH.COORD", "Coordinate Geometry", "X.MATH.U.COORD"),
        Chapter("X.MATH.TRIG", "Introduction to Trigonometry", "X.MATH.U.TRIG"),
        Chapter("X.MATH.APPTRIG", "Applications of Trigonometry", "X.MATH.U.TRIG"),
        Chapter("X.MATH.CIRCLE", "Circles", "X.MATH.U.GEOMETRY"),
        Chapter("X.MATH.AREAS", "Areas Related to Circles", "X.MATH.U.MENSURATION"),
        Chapter("X.MATH.SAV", "Surface Areas and Volumes", "X.MATH.U.MENSURATION"),
        Chapter("X.MATH.STATS", "Statistics", "X.MATH.U.STATSPROB"),
        Chapter("X.MATH.PROB", "Probability", "X.MATH.U.STATSPROB"),
    ],
    concept_families=[
        ("X.MATH.CF.VOLUME_COMPOSITE", "Volume of Composite Solids", "X.MATH.SAV"),
        ("X.MATH.CF.IRRATIONALITY", "Irrationality Proofs", "X.MATH.REAL"),
        ("X.MATH.CF.TRIG_IDENTITIES", "Trigonometric Identities", "X.MATH.TRIG"),
    ],
)

#: CBSE Class X Science: five units, 80 theory marks, 13 NCERT chapters.
#:
#: The unit weightage is the board's and is verified. The chapter list is deliberately
#: EMPTY: the rationalised syllabus renumbered the book, secondary sources disagree, and a
#: chapter mapped to the wrong unit sends a student's marks to the wrong place in the
#: report. The contents page of the book is the oracle for that -- as it already is for
#: sections -- so chapters are added from it rather than from recollection.
#:
#: Until they are, `scripts.ingest_book` will create the chapters and name them as
#: unmapped to a board unit, which is visible rather than silent.
X_SCIENCE = Curriculum(
    subject_code="X.SCI",
    subject_label="Class X Science",
    grade=10,
    units=[
        BoardUnit("X.SCI.U.CHEMICAL", "Chemical Substances -- Nature and Behaviour", 25.0),
        BoardUnit("X.SCI.U.LIVING", "World of Living", 25.0),
        BoardUnit("X.SCI.U.CURRENT", "Effects of Current", 13.0),
        BoardUnit("X.SCI.U.PHENOMENA", "Natural Phenomena", 12.0),
        BoardUnit("X.SCI.U.RESOURCES", "Natural Resources", 5.0),
    ],
    # Read off the contents page of the NCERT Class X Science textbook, Reprint 2026-27
    # (jesc1ps.pdf, page xi): thirteen chapters, in book order. Order is load-bearing --
    # chapter_title() resolves an NCERT filename like jesc108.pdf by position, so an
    # inserted or reordered row silently retitles a chapter.
    chapters=[
        Chapter("X.SCI.CHEMRXN", "Chemical Reactions and Equations", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.ACIDS", "Acids, Bases and Salts", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.METALS", "Metals and Non-metals", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.CARBON", "Carbon and its Compounds", "X.SCI.U.CHEMICAL"),
        Chapter("X.SCI.LIFEPROC", "Life Processes", "X.SCI.U.LIVING"),
        Chapter("X.SCI.CONTROL", "Control and Coordination", "X.SCI.U.LIVING"),
        Chapter("X.SCI.REPRO", "How do Organisms Reproduce?", "X.SCI.U.LIVING"),
        Chapter("X.SCI.HEREDITY", "Heredity", "X.SCI.U.LIVING"),
        Chapter("X.SCI.LIGHT", "Light \u2013 Reflection and Refraction", "X.SCI.U.PHENOMENA"),
        Chapter("X.SCI.EYE", "The Human Eye and the Colourful World", "X.SCI.U.PHENOMENA"),
        Chapter("X.SCI.ELECTRICITY", "Electricity", "X.SCI.U.CURRENT"),
        Chapter("X.SCI.MAGNETIC", "Magnetic Effects of Electric Current", "X.SCI.U.CURRENT"),
        Chapter("X.SCI.ENVIRONMENT", "Our Environment", "X.SCI.U.RESOURCES"),
    ],
    # Deliberately empty. The Maths families were proposed from the book's own section
    # headings once the chapters were embedded, then reviewed; Science gets the same
    # treatment and not a set invented ahead of the text.
    concept_families=[],
)

#: CBSE Class X Social Science is four separate NCERT books, not one: each book's own
#: chapter numbering restarts at 1, and `chapter_number()` reads that number off the
#: filename alone (jess101.pdf -> chapter 1). One subject code per book, the same way
#: X.MATH and X.SCI are each exactly one book, so two different books' "chapter 1" can
#: never collide under a shared code.
#:
#: Board-unit weightage is a placeholder (0.0) pending the official CBSE blueprint --
#: `apply()` only ever creates a BoardUnitWeight once, so setting a guessed number now
#: would need a second write path to correct later, not just a re-run. The chapter list
#: itself is real: read off each book's own contents page (Reprint 2026-27), not recalled.
X_HISTORY = Curriculum(
    subject_code="X.HIST",
    subject_label="Class X History (India and the Contemporary World – II)",
    grade=10,
    units=[
        BoardUnit("X.HIST.U.WHOLE", "India and the Contemporary World – II", 0.0),
    ],
    # jess3ps.pdf, page xi. Three named sections in the book; kept as one board unit
    # until the blueprint says otherwise.
    chapters=[
        Chapter("X.HIST.NATIONALISM_EUROPE", "The Rise of Nationalism in Europe", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.NATIONALISM_INDIA", "Nationalism in India", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.GLOBALWORLD", "The Making of a Global World", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.INDUSTRIALISATION", "The Age of Industrialisation", "X.HIST.U.WHOLE"),
        Chapter("X.HIST.PRINTCULTURE", "Print Culture and the Modern World", "X.HIST.U.WHOLE"),
    ],
    concept_families=[],
)

X_GEOGRAPHY = Curriculum(
    subject_code="X.GEO",
    subject_label="Class X Geography (Contemporary India – II)",
    grade=10,
    units=[
        BoardUnit("X.GEO.U.WHOLE", "Contemporary India – II", 0.0),
    ],
    # jess1ps.pdf, Contents page.
    chapters=[
        Chapter("X.GEO.RESOURCES", "Resources and Development", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.FORESTWILDLIFE", "Forest and Wildlife Resources", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.WATER", "Water Resources", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.AGRICULTURE", "Agriculture", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.MINERALSENERGY", "Minerals and Energy Resources", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.MANUFACTURING", "Manufacturing Industries", "X.GEO.U.WHOLE"),
        Chapter("X.GEO.LIFELINES", "Lifelines of National Economy", "X.GEO.U.WHOLE"),
    ],
    concept_families=[],
)

X_POLITICAL_SCIENCE = Curriculum(
    subject_code="X.POL",
    subject_label="Class X Political Science (Democratic Politics – II)",
    grade=10,
    units=[
        BoardUnit("X.POL.U.WHOLE", "Democratic Politics – II", 0.0),
    ],
    # jess4ps.pdf, Contents page. The book itself labels these Unit I-IV; kept as one
    # board unit here for the same reason as History's sections, until the blueprint
    # says whether the board scores them separately.
    chapters=[
        Chapter("X.POL.POWERSHARING", "Power-sharing", "X.POL.U.WHOLE"),
        Chapter("X.POL.FEDERALISM", "Federalism", "X.POL.U.WHOLE"),
        Chapter("X.POL.GENDERRELIGIONCASTE", "Gender, Religion and Caste", "X.POL.U.WHOLE"),
        Chapter("X.POL.PARTIES", "Political Parties", "X.POL.U.WHOLE"),
        Chapter("X.POL.OUTCOMES", "Outcomes of Democracy", "X.POL.U.WHOLE"),
    ],
    concept_families=[],
)

X_ECONOMICS = Curriculum(
    subject_code="X.ECO",
    subject_label="Class X Economics (Understanding Economic Development)",
    grade=10,
    units=[
        BoardUnit("X.ECO.U.WHOLE", "Understanding Economic Development", 0.0),
    ],
    # jess2ps.pdf, Contents page.
    chapters=[
        Chapter("X.ECO.DEVELOPMENT", "Development", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.SECTORS", "Sectors of the Indian Economy", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.MONEYCREDIT", "Money and Credit", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.GLOBALISATION", "Globalisation and the Indian Economy", "X.ECO.U.WHOLE"),
        Chapter("X.ECO.CONSUMERRIGHTS", "Consumer Rights", "X.ECO.U.WHOLE"),
    ],
    concept_families=[],
)

#: CBSE Class X English is three separate NCERT books, same reasoning as Social Science's
#: four -- one subject code per physical book, since each book's own chapter numbering
#: restarts at 1.
#:
#: First Flight is the *current, rationalised* edition (Reprint 2026-27), read off the
#: book's own contents page (jeff1ps.pdf) -- a first, incomplete upload of that prelims
#: file cut off after chapter 4, and an earlier version of this comment wrongly took that
#: as the whole book; the fuller upload lists nine chapters, matching the Workbook
#: exactly, so there is no book-to-book mismatch after all. Each chapter file bundles its
#: accompanying poem(s) in the same PDF (e.g. jeff101.pdf is "A Letter to God" together
#: with "Dust of Snow" and "Fire and Ice"), so the poems are not separate chapters here.
X_ENGLISH_FIRST_FLIGHT = Curriculum(
    subject_code="X.ENG.FF",
    subject_label="Class X English (First Flight)",
    grade=10,
    units=[
        BoardUnit("X.ENG.FF.U.WHOLE", "First Flight", 0.0),
    ],
    # jeff1ps.pdf, Contents page (rationalised edition, Reprint 2026-27).
    chapters=[
        Chapter("X.ENG.FF.LETTERTOGOD", "A Letter to God", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.MANDELA", "Nelson Mandela: Long Walk to Freedom", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.FLYING", "Two Stories about Flying", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.ANNEFRANK", "From the Diary of Anne Frank", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.GLIMPSESINDIA", "Glimpses of India", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.MIJBIL", "Mijbil the Otter", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.MADAMBUS", "Madam Rides the Bus", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.SERMON", "The Sermon at Benares", "X.ENG.FF.U.WHOLE"),
        Chapter("X.ENG.FF.PROPOSAL", "The Proposal", "X.ENG.FF.U.WHOLE"),
    ],
    concept_families=[],
)

X_ENGLISH_FOOTPRINTS = Curriculum(
    subject_code="X.ENG.FWF",
    subject_label="Class X English (Footprints without Feet)",
    grade=10,
    units=[
        BoardUnit("X.ENG.FWF.U.WHOLE", "Footprints without Feet", 0.0),
    ],
    # jefp1ps.pdf, Contents page.
    chapters=[
        Chapter("X.ENG.FWF.SURGERY", "A Triumph of Surgery", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.THIEF", "The Thief's Story", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.MIDNIGHTVISITOR", "The Midnight Visitor", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.TRUST", "A Question of Trust", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.FOOTPRINTS", "Footprints without Feet", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.SCIENTIST", "The Making of a Scientist", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.NECKLACE", "The Necklace", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.BHOLI", "Bholi", "X.ENG.FWF.U.WHOLE"),
        Chapter("X.ENG.FWF.SAVEDTHEEARTH", "The Book That Saved the Earth", "X.ENG.FWF.U.WHOLE"),
    ],
    concept_families=[],
)

X_ENGLISH_WORKBOOK = Curriculum(
    subject_code="X.ENG.WB",
    subject_label="Class X English (Words and Expressions -- Workbook)",
    grade=10,
    units=[
        BoardUnit("X.ENG.WB.U.WHOLE", "Words and Expressions", 0.0),
    ],
    # jewe2ps.pdf, Contents page. Its nine units match First Flight's nine chapters
    # one-to-one, same order.
    chapters=[
        Chapter("X.ENG.WB.LETTERTOGOD", "A Letter to God", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.MANDELA", "Nelson Mandela: Long Walk to Freedom", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.FLYING", "Two Stories about Flying", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.ANNEFRANK", "From the Diary of Anne Frank", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.GLIMPSESINDIA", "Glimpses of India", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.MIJBIL", "Mijbil the Otter", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.MADAMBUS", "Madam Rides the Bus", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.SERMON", "The Sermon at Benaras", "X.ENG.WB.U.WHOLE"),
        Chapter("X.ENG.WB.PROPOSAL", "The Proposal", "X.ENG.WB.U.WHOLE"),
    ],
    concept_families=[],
)

#: Class X Hindi is four separate NCERT books too (Kshitij and Kritika for Course A,
#: Sparsh and Sanchayan for Course B), same one-subject-code-per-physical-book reasoning
#: as Social Science and English. All four now registered -- every contents page below was
#: actually read (via OCR, since the text layer decodes as mojibake -- see
#: app.ingest.hindi_ocr / app.ingest.gemini_ocr / app.ingest.hindi_text) and verified
#: against the real prelims file, Kshitij's काव्य खंड page confirmed by direct visual read
#: of the rendered page after Tesseract OCR'd it as unreadable decorative-background noise.
X_HINDI_KRITIKA = Curriculum(
    subject_code="X.HIN.KR",
    subject_label="Class X Hindi (कृतिका)",
    grade=10,
    units=[
        BoardUnit("X.HIN.KR.U.WHOLE", "कृतिका", 0.0),
    ],
    # jhkr1ps.pdf, विषय सूची (contents page), read via OCR.
    chapters=[
        Chapter("X.HIN.KR.MATA_KA_ANCHAL", "माता का अँचल", "X.HIN.KR.U.WHOLE"),
        Chapter("X.HIN.KR.SANA_SANA_HATH", "साना-साना हाथ जोड़ि...", "X.HIN.KR.U.WHOLE"),
        Chapter("X.HIN.KR.MAIN_KYON_LIKHTA", "मैं क्यों लिखता हूँ?", "X.HIN.KR.U.WHOLE"),
    ],
    concept_families=[],
)

X_HINDI_KSHITIJ = Curriculum(
    subject_code="X.HIN.KS",
    subject_label="Class X Hindi (क्षितिज, भाग 2)",
    grade=10,
    units=[
        BoardUnit("X.HIN.KS.U.WHOLE", "क्षितिज", 0.0),
    ],
    # jhks1ps.pdf, विषय-क्रम (contents page). Twelve chapters -- काव्य खंड (poetry, 1-6)
    # then गद्य खंड (prose, 7-12) -- read by directly viewing the rendered contents pages
    # after Tesseract's own OCR came back as decorative-background noise on the poetry
    # page specifically (page images, not the prose page, which OCR'd cleanly).
    #
    # The poetry chapters were typed here as "Author (poem title)" -- this session's own
    # convention for naming a poem, not the book's. Confirmed wrong TWICE against real
    # files, both times the same way: chapter 2 (jhks102.pdf) called "तुलसीदास", not
    # "तुलसीदास (राम-लक्ष्मण-परशुराम संवाद)"; chapter 5 (jhks105.pdf) called "नागार्जुन",
    # not "नागार्जुन (यह दंतुरित मुसकान, फसल)". difflib's fuzzy match (verify_against_toc,
    # ratio >= 0.6) is for OCR noise around the same title, not a title carrying extra real
    # words the book's own contents page does not have, so it correctly rejected both
    # rather than papering over them. Two real chapters agreeing is the book's own
    # contents-page convention (poet name alone), not a coincidence worth re-litigating
    # chapter by chapter -- the remaining poetry titles are trimmed to match on the same
    # basis, still to be confirmed individually as each chapter file actually uploads.
    chapters=[
        Chapter("X.HIN.KS.SURDAS", "सूरदास", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.TULSIDAS", "तुलसीदास", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.JAISHANKAR_PRASAD", "जयशंकर प्रसाद", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.NIRALA", "सूर्यकांत त्रिपाठी 'निराला'", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.NAGARJUN", "नागार्जुन", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.MANGLESH_DABRAL", "मंगलेश डबराल", "X.HIN.KS.U.WHOLE"),
        # गद्य खंड (7-12): the opposite mismatch from the poetry section above, not the
        # same one -- the contents page gives the AUTHOR's name, not the story's own
        # title (which this session had typed here instead). Confirmed four times now:
        # chapter 7 (jhks107.pdf) is "स्वयं प्रकाश", not "नेताजी का चश्मा"; chapter 8
        # (jhks108.pdf) is "रामवृक्ष बेनीपुरी", not "बालगोबिन भगत"; chapter 9 (jhks109.pdf)
        # is "यशपाल", not "लखनवी अंदाज़"; chapter 10 (jhks110.pdf) is "मन्नू भंडारी", not
        # "एक कहानी यह भी". The remaining two prose titles (Naubatkhane, Sanskriti) are
        # STILL left as story titles rather than guessed authors -- knowing the convention
        # is not the same as knowing which name each one's own page actually prints, and
        # every other marker in this module was confirmed against its real file before
        # being trusted, not assumed from a pattern plus outside knowledge.
        Chapter("X.HIN.KS.NETAJI_KA_CHASHMA", "स्वयं प्रकाश", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.BALGOBIN_BHAGAT", "रामवृक्ष बेनीपुरी", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.LAKHNAVI_ANDAZ", "यशपाल", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.EK_KAHANI_YEH_BHI", "मन्नू भंडारी", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.NAUBATKHANE", "नौबतखाने में इबादत", "X.HIN.KS.U.WHOLE"),
        Chapter("X.HIN.KS.SANSKRITI", "संस्कृति", "X.HIN.KS.U.WHOLE"),
    ],
    concept_families=[],
)

X_HINDI_SPARSH = Curriculum(
    subject_code="X.HIN.SP",
    subject_label="Class X Hindi (स्पर्श)",
    grade=10,
    units=[
        BoardUnit("X.HIN.SP.U.WHOLE", "स्पर्श", 0.0),
    ],
    # jhsp1ps.pdf, पाठ सूची (contents page), read via OCR. Fourteen chapters -- पद्य खंड
    # (poetry, 1-7) then गद्य खंड (prose, 8-14, the last of which -- कारतूस -- is a
    # one-act play rather than prose proper, but the book's own contents page places it
    # under गद्य खंड, not as a separate section).
    chapters=[
        Chapter("X.HIN.SP.KABIR", "कबीर (साखी)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.MEERA", "मीरा (पद)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.MAITHILISHARAN_GUPT", "मैथिलीशरण गुप्त (मनुष्यता)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.SUMITRANANDAN_PANT", "सुमित्रानंदन पंत (पर्वत प्रदेश में पावस)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.VEEREN_DANGWAL", "वीरेन डंगवाल (तोप)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.KAIFI_AZMI", "कैफ़ी आज़मी (कर चले हम फ़िदा)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.TAGORE", "रवींद्रनाथ ठाकुर (आत्मत्राण)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.PREMCHAND", "प्रेमचंद (बड़े भाई साहब)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.SITARAM_SEKSARIA", "सीताराम सेकसरिया (डायरी का एक पन्ना)", "X.HIN.SP.U.WHOLE"),
        Chapter("X.HIN.SP.LEELADHAR_MANDLOI", "लीलाधर मंडलोई (तताँरा-वामीरो कथा)", "X.HIN.SP.U.WHOLE"),
        Chapter(
            "X.HIN.SP.PRAHLAD_AGRAWAL",
            "प्रहलाद अग्रवाल (तीसरी कसम के शिल्पकार शैलेंद्र)", "X.HIN.SP.U.WHOLE",
        ),
        Chapter(
            "X.HIN.SP.NIDA_FAZLI",
            "निदा फ़ाज़ली (अब कहाँ दूसरे के दुख से दुखी होने वाले)", "X.HIN.SP.U.WHOLE",
        ),
        Chapter(
            "X.HIN.SP.RAVINDRA_KELEKAR",
            "रवींद्र केलेकर (पतझर में टूटी पत्तियाँ)", "X.HIN.SP.U.WHOLE",
        ),
        Chapter("X.HIN.SP.HABIB_TANVIR", "हबीब तनवीर (कारतूस, एकांकी)", "X.HIN.SP.U.WHOLE"),
    ],
    concept_families=[],
)

X_HINDI_SANCHAYAN = Curriculum(
    subject_code="X.HIN.SY",
    subject_label="Class X Hindi (संचयन, भाग 2)",
    grade=10,
    units=[
        BoardUnit("X.HIN.SY.U.WHOLE", "संचयन", 0.0),
    ],
    # jhsy1ps.pdf, contents page, read via OCR.
    chapters=[
        Chapter("X.HIN.SY.HARIHAR_KAKA", "हरिहर काका (मिथिलेश्वर)", "X.HIN.SY.U.WHOLE"),
        Chapter("X.HIN.SY.SAPNON_KE_SE_DIN", "सपनों के-से दिन (गुरदयाल सिंह)", "X.HIN.SY.U.WHOLE"),
        Chapter("X.HIN.SY.TOPI_SHUKLA", "टोपी शुक्ला (राही मासूम रज़ा)", "X.HIN.SY.U.WHOLE"),
    ],
    concept_families=[],
)

CURRICULA: dict[str, Curriculum] = {
    X_MATH.subject_code: X_MATH,
    X_SCIENCE.subject_code: X_SCIENCE,
    X_HISTORY.subject_code: X_HISTORY,
    X_GEOGRAPHY.subject_code: X_GEOGRAPHY,
    X_POLITICAL_SCIENCE.subject_code: X_POLITICAL_SCIENCE,
    X_ECONOMICS.subject_code: X_ECONOMICS,
    X_ENGLISH_FIRST_FLIGHT.subject_code: X_ENGLISH_FIRST_FLIGHT,
    X_ENGLISH_FOOTPRINTS.subject_code: X_ENGLISH_FOOTPRINTS,
    X_ENGLISH_WORKBOOK.subject_code: X_ENGLISH_WORKBOOK,
    X_HINDI_KRITIKA.subject_code: X_HINDI_KRITIKA,
    X_HINDI_KSHITIJ.subject_code: X_HINDI_KSHITIJ,
    X_HINDI_SPARSH.subject_code: X_HINDI_SPARSH,
    X_HINDI_SANCHAYAN.subject_code: X_HINDI_SANCHAYAN,
}


def chapter_title(subject_code: str, number: int) -> str | None:
    """The book's chapter N, by the name the syllabus gives it.

    An NCERT filename (jemh101.pdf) carries a number and no title, and the title on the
    page is a running header that only appears on odd pages -- six of fourteen chapters do
    not show it before their first section. The curriculum lists chapters in book order and
    is already the authority for chapter identity, since it carries the board-unit mapping.
    """
    curriculum = CURRICULA.get(subject_code)
    if curriculum is None or not (1 <= number <= len(curriculum.chapters)):
        return None
    return curriculum.chapters[number - 1].label
