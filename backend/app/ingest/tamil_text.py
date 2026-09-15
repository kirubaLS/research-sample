"""Tamil books: a real Unicode text layer, unlike Hindi's (see app.ingest.hindi_ocr) --
no OCR backend needed at all -- but with its own font-level artifact to correct first.

Checked against the real CBSE Tamil Class X book (174 pages, pymupdf's own extraction,
not a third-party converter's): the font subsets used for chapter bodies repeat certain
glyphs -- a consonant, a vowel sign, sometimes with a stray U+FFFD between the repeats --
two or three times in a row where the printed page has it once. 'சாாார்ந்த' should read
'சார்ந்த' ("related to"); 'மொ�ொழியின்' should read 'மொழியின்' ("of language"). This is
never genuine Tamil orthography -- a real doubled consonant is written with an explicit
virama between the two (க்க​), not the same bare code point twice -- so collapsing any run
of an identical Tamil character (optionally separated by U+FFFD) is safe and verified to
turn corrupted words back into real ones across sampled pages spanning the whole book.

It does not recover everything: about 0.57% of characters book-wide are a bare U+FFFD with
no duplicate to collapse -- a genuinely unmapped glyph, not a formatting artifact, and no
regex fixes that. Left in place rather than silently dropped, the same way OCR noise
elsewhere in this codebase is surfaced rather than hidden.
"""

from __future__ import annotations

import re

import pymupdf

#: U+0B80-U+0BFF, the Tamil Unicode block. Restricting the match to it (rather than any
#: character) is what keeps this from ever touching an English word, a digit, or
#: punctuation that happens to repeat for a real reason (e.g. '!!' in body text).
_TAMIL_CHAR_RUN = re.compile(r"([஀-௿])(?:�?\1)+")


def clean_tamil_text(text: str) -> str:
    """Collapse the font's own glyph-repeat artifact -- see module docstring."""
    return _TAMIL_CHAR_RUN.sub(r"\1", text)


#: Every other Indic-script Unicode block (Devanagari through Sinhala), with the Tamil
#: block itself (U+0B80-U+0BFF) cut out of the middle of the otherwise-contiguous range.
#: Real Tamil-book prose never legitimately contains any of these -- a book that mixes
#: scripts mid-sentence (English loanwords, the odd digit) always does so in the Latin
#: block or in Tamil digits, never in Devanagari or Bengali, so any character in here is
#: itself proof the text layer is not reading what is actually printed on the page. This
#: is exactly what the corrupted "X.TAM.CF.AIR_IN_ANCIENT_KNOWLEDGE_TRADITIONS" concept-
#: family label ("पराचीन जञान परपरा म वाय", pure Devanagari on a Tamil chapter) trips.
_OTHER_INDIC_SCRIPT = re.compile(r"[ऀ-୿ఀ-෿]")

#: A Latin letter fused directly onto Tamil characters with no space between -- real
#: Tamil-book text sometimes carries a whole Latin word or acronym (a transliteration, a
#: unit like 'CFC'), but always as its own space-delimited token; nothing in real Tamil
#: typesetting glues a single Latin letter into the middle of a Tamil syllable run. This
#: is what the production splice 'குளோNோரோ' (an 'N' standing in for a dropped Tamil
#: glyph inside "Chloro Fluoro Carbon" transliterated) trips, and the pulli-ratio signal
#: below would not catch it on its own -- the word is too short for the ratio to be
#: meaningful, and the surrounding word ("புளோNோரோ") may still carry other pullis.
_LATIN_SPLICED_INTO_TAMIL = re.compile(r"[஀-௿][A-Za-z]+[஀-௿]|[஀-௿][A-Za-z]+$|^[A-Za-z]+[஀-௿]")

#: Tamil consonants (க-ஹ). Counting these, not every Tamil-block character, is what makes
#: the pulli ratio below meaningful: vowels, vowel signs and punctuation never carry a
#: pulli, only a consonant can, so the denominator has to be "characters that could
#: plausibly carry one" rather than "Tamil characters in general".
_TAMIL_CONSONANT = re.compile(r"[க-ஹ]")
_PULLI = "்"

#: Measured against known-clean text: the module docstring's own corrected examples
#: ('சார்ந்த', 'மொழியின்') are too short to be a stable baseline, but a real corrected
#: sentence pulled from the same production defect this module fixes --
#: 'காற்று பேசியதைப் போல, நிலம் பேசுவதாக எண்ணிக்கொண்டு பேசுக' -- carries a pulli for
#: roughly 1 consonant in 4.5 (6 pullis / 27 consonants, ratio 0.222), and a generic
#: multi-sentence Tamil prose sample (unrelated to this book, to check the baseline is not
#: an artifact of one sentence) comes in similar (26/92, ratio 0.283). The matching
#: *corrupted* production text -- 'காறறு பேசியதைப போல, நிலம பேசுவதாக எணணிககொணடு பேசுக',
#: the exact same sentence with every pulli dropped by the broken ToUnicode CMap -- has a
#: ratio of exactly 0.0, not merely a lower one. 0.10 sits well clear of both real samples
#: (>2x margin below either) while still comfortably above the total-dropout case a broken
#: CMap actually produces, so it is not a threshold tuned to one string; a real book page
#: would have to be missing the large majority of its pullis to land under it by chance.
_MIN_PULLI_RATIO = 0.10

#: Below this many consonants, the pulli ratio is noise -- a short heading or a two-word
#: caption can legitimately have zero consonants-with-pullis just by being short, and
#: flagging it would OCR pages that were never actually corrupted. The other-script and
#: Latin-splice signals still apply at any length; only the ratio signal is gated.
_MIN_CONSONANTS_FOR_RATIO = 20


def tamil_text_is_corrupted(
    text: str, *, min_pulli_ratio: float = _MIN_PULLI_RATIO,
    min_consonants: int = _MIN_CONSONANTS_FOR_RATIO,
) -> bool:
    """Whether ``text`` (already run through clean_tamil_text) shows the ToUnicode-CMap
    defect described in the module docstring -- font subsets used for some chapters map
    to entirely wrong or missing codepoints, which no regex on the resulting text can
    repair, unlike the glyph-repeat artifact clean_tamil_text does fix.

    Three independent signals, any one of which is conclusive on its own:

    1. Another Indic script's characters appear at all (_OTHER_INDIC_SCRIPT) -- a Tamil
       book chapter never legitimately contains Devanagari or Bengali.
    2. A Latin letter is fused directly into a run of Tamil characters
       (_LATIN_SPLICED_INTO_TAMIL) -- real Tamil/Latin code-mixing is always space
       delimited.
    3. The ratio of pullis to Tamil consonants is far below what real Tamil prose has
       (see _MIN_PULLI_RATIO's own reasoning), and there is enough text
       (_MIN_CONSONANTS_FOR_RATIO) for that ratio to mean anything.

    Used to decide, per page, whether app.ingest.tamil_text's fast text-layer path is
    trustworthy or whether the page needs to be re-read through app.ingest.tamil_ocr
    instead -- see _extract_tamil_page_text below.
    """
    if _OTHER_INDIC_SCRIPT.search(text):
        return True
    if _LATIN_SPLICED_INTO_TAMIL.search(text):
        return True
    consonants = len(_TAMIL_CONSONANT.findall(text))
    if consonants >= min_consonants:
        pullis = text.count(_PULLI)
        if pullis / consonants < min_pulli_ratio:
            return True
    return False


def _extract_tamil_page_text(page: "pymupdf.Page") -> str:
    """One page's text: the fast text-layer extraction, cleaned, falling back to OCR
    (app.ingest.tamil_ocr) only for the pages that need it -- see tamil_read_text.
    """
    text = clean_tamil_text(page.get_text())
    if not tamil_text_is_corrupted(text):
        return text
    from app.ingest.tamil_ocr import ocr_available, ocr_read_page

    if not ocr_available():
        # Surfaced, not silently swallowed -- the same reasoning as hindi_ocr's own
        # ocr_available() guard: a deployment either can recover this page or it cannot,
        # and returning the known-corrupted text as if it were fine would feed the exact
        # bug this module exists to prevent straight back into the pipeline.
        raise RuntimeError(
            f"page {page.number + 1} of a Tamil chapter has a broken font ToUnicode "
            f"mapping (see app.ingest.tamil_text's module docstring) and Tesseract's "
            f"Tamil language pack ('tam') is not installed here, so this page cannot be "
            f"read at all -- install Tesseract with the tam traineddata, or upload from a "
            f"deployment that has it."
        )
    return ocr_read_page(page)


def tamil_read_text(source: str | bytes) -> str:
    """A Tamil book's real text, page by page: pymupdf's own extraction, cleaned, with any
    page whose font subset has the broken-ToUnicode-CMap defect (see module docstring and
    tamil_text_is_corrupted) re-read through OCR instead of the (wrong) text layer.

    Accepts a path or raw bytes so a caller holding an upload in memory does not need a
    temp file just to read text from it -- the same shape app.ingest.hindi_text's OCR
    backends take. Only the pages that actually need it are OCR'd -- OCR is slow and most
    Tamil chapters extract cleanly (see module docstring), so paying that cost on every
    page of every chapter would undo the whole reason the fast path exists.
    """
    doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    try:
        pages = [_extract_tamil_page_text(page) for page in doc]
    finally:
        doc.close()
    return "\n".join(pages)
