"""app.ingest.tamil_text: the font's own glyph-repeat artifact, and what it should never
touch.

Every corrupted/clean word pair here is copied verbatim from the real CBSE Tamil Class X
book's own pymupdf extraction (not a synthetic example) -- see the module's own docstring
for how that was found and why the fix is safe.
"""

from __future__ import annotations

from app.ingest.tamil_text import clean_tamil_text, tamil_read_text, tamil_text_is_corrupted


def test_a_tripled_vowel_sign_collapses_to_one():
    # 'மனிதம் சாாார்ந்த கருத்துகள்' -> 'மனிதம் சார்ந்த கருத்துகள்' ("human-related ideas")
    assert clean_tamil_text("மனிதம் சாாார்ந்த கருத்துகள்") == "மனிதம் சார்ந்த கருத்துகள்"


def test_a_replacement_character_between_two_repeats_is_absorbed_too():
    # 'மொ�ொழியின்' -> 'மொழியின்' ("of language")
    assert clean_tamil_text("மொ�ொழியின் செழுமை") == "மொழியின் செழுமை"


def test_a_doubled_consonant_with_no_vowel_sign_also_collapses():
    # 'பாாடடல்கள்' -> 'பாடல்கள்' ("poems") -- both the doubled ா and the doubled ட
    assert clean_tamil_text("பாாடடல்கள்") == "பாடல்கள்"


def test_a_genuine_geminated_consonant_with_a_virama_is_left_alone():
    """Real Tamil gemination is written explicitly with a virama between the two
    consonants (க்க) -- that is not the bare-repeat shape this cleanup targets, and must
    survive unchanged or every genuinely doubled consonant in the language breaks."""
    assert clean_tamil_text("கத்தி") == "கத்தி"


def test_english_and_digits_are_never_touched():
    """The character-run pattern is scoped to the Tamil Unicode block specifically --
    repeated Latin letters or digits (a real 'CBSE 2025', a genuine '!!') must never be
    collapsed just because they happen to repeat."""
    assert clean_tamil_text("CBSE 2025!!") == "CBSE 2025!!"


def test_a_lone_unmapped_glyph_with_no_duplicate_is_left_as_is():
    """Not every replacement character is part of a doubling artifact -- some are a
    genuinely unmapped glyph the font's cmap has no entry for at all, and there is
    nothing to collapse it against. Left in place rather than silently dropped."""
    assert clean_tamil_text("கருத்துகளை�ப்") == "கருத்துகளை�ப்"


# --- tamil_text_is_corrupted: the second, unfixable font defect -----------------------
#
# Every corrupted sample below is copied verbatim from the real production book_chunk
# text for the chapter "கேட்கிறதா என் குரல்!" (a broken ToUnicode CMap, not the
# glyph-repeat artifact clean_tamil_text fixes -- see this module's docstring).


def test_a_pulli_dropped_production_sentence_is_flagged():
    # Every pulli is missing: 'காற்று' -> 'காறறு', 'பேசியதைப்' -> 'பேசியதைப', etc.
    corrupted = "காறறு பேசியதைப போல, நிலம பேசுவதாக எணணிககொணடு பேசுக"
    assert tamil_text_is_corrupted(corrupted) is True


def test_the_same_sentence_with_its_pullis_restored_is_not_flagged():
    clean = "காற்று பேசியதைப் போல, நிலம் பேசுவதாக எண்ணிக்கொண்டு பேசுக"
    assert tamil_text_is_corrupted(clean) is False


def test_a_latin_letter_spliced_into_a_tamil_word_is_flagged():
    # 'குளோNோரோ புளோNோரோ' -- a stray Latin 'N' standing in for a dropped Tamil glyph
    # inside a "Chloro Fluoro Carbon" transliteration.
    assert tamil_text_is_corrupted("குளோNோரோ புளோNோரோ") is True


def test_a_devanagari_splice_into_a_tamil_label_is_flagged():
    # The real corrupted X.TAM.CF.AIR_IN_ANCIENT_KNOWLEDGE_TRADITIONS concept-family
    # label -- pure Devanagari where a Tamil label was expected.
    assert tamil_text_is_corrupted("பராசீன ஞானம் பராமரா म वाय") is True


def test_ordinary_clean_tamil_prose_is_not_flagged():
    sample = (
        "தமிழ் மொழி திராவிட மொழிக் குடும்பத்தைச் சேர்ந்த ஒரு தொன்மையான "
        "மொழியாகும். இது தமிழ்நாடு மற்றும் புதுச்சேரியின் அரசு மொழியாகவும், "
        "இலங்கை மற்றும் சிங்கப்பூரின் அலுவல் மொழிகளுள் ஒன்றாகவும் திகழ்கிறது."
    )
    assert tamil_text_is_corrupted(sample) is False


def test_a_real_english_loanword_as_its_own_token_is_not_flagged():
    """Space-delimited code-mixing (a whole Latin word, not a letter fused into a Tamil
    one) is genuine and common in real chapters -- must not be flagged on its own."""
    assert tamil_text_is_corrupted("CBSE தேர்வுக்கு தயாராகுங்கள்") is False


def test_a_short_heading_with_no_pullis_is_not_flagged_on_ratio_alone():
    """Below _MIN_CONSONANTS_FOR_RATIO, the ratio signal is noise -- a short heading can
    legitimately have no pullis just by being short."""
    assert tamil_text_is_corrupted("பாடம் ஒன்று") is False


# --- tamil_read_text: OCR fallback wiring ----------------------------------------------


def test_a_corrupted_page_falls_back_to_ocr_and_a_clean_one_does_not(tmp_path, monkeypatch):
    """The actual ingest wiring: tamil_read_text extracts each page through the fast text
    layer, and only re-reads a page through OCR when tamil_text_is_corrupted flags it --
    OCR is not available in this sandbox, so app.ingest.tamil_ocr is stubbed the same way
    app.ingest.hindi_text's tests stub app.ingest.hindi_ocr."""
    import pymupdf

    # A default PDF font cannot render real Tamil glyphs at all (insert_text silently
    # drops them), so the fast text layer itself is stubbed here rather than relying on a
    # synthetic PDF to happen to contain the right Unicode when read back -- the point of
    # this test is the per-page OCR-fallback wiring, not pymupdf's own extraction.
    doc = pymupdf.open()
    doc.new_page(width=595, height=200)
    doc.new_page(width=595, height=200)
    path = tmp_path / "two-pages.pdf"
    doc.save(path)
    doc.close()

    page_texts = {
        0: "காற்று பேசியதைப் போல நிலம் பேசுவதாக எண்ணிக்கொண்டு",
        1: "காறறு பேசியதைப போல நிலம பேசுவதாக எணணிககொணடு",
    }
    monkeypatch.setattr(
        pymupdf.Page, "get_text", lambda self, *a, **kw: page_texts[self.number],
    )

    ocr_calls: list[int] = []

    def fake_ocr_read_page(page, **kwargs):
        ocr_calls.append(page.number)
        return "OCR-RECOVERED-TEXT"

    monkeypatch.setattr("app.ingest.tamil_ocr.ocr_available", lambda: True)
    monkeypatch.setattr("app.ingest.tamil_ocr.ocr_read_page", fake_ocr_read_page)

    result = tamil_read_text(str(path))

    assert ocr_calls == [1]  # only the second (corrupted) page, not the first
    assert "OCR-RECOVERED-TEXT" in result
    assert "காற்று" in result


def test_a_corrupted_page_with_no_ocr_backend_raises_clearly(tmp_path, monkeypatch):
    """Mirrors app.ingest.hindi_text's own guard when no backend is available -- a
    corrupted page must be surfaced loudly, never silently returned as if it were fine."""
    import pymupdf

    doc = pymupdf.open()
    doc.new_page(width=595, height=200)
    path = tmp_path / "one-page.pdf"
    doc.save(path)
    doc.close()

    monkeypatch.setattr(
        pymupdf.Page, "get_text",
        lambda self, *a, **kw: "காறறு பேசியதைப போல நிலம பேசுவதாக எணணிககொணடு",
    )
    monkeypatch.setattr("app.ingest.tamil_ocr.ocr_available", lambda: False)

    try:
        tamil_read_text(str(path))
        assert False, "expected a RuntimeError"
    except RuntimeError as exc:
        assert "tam" in str(exc)
