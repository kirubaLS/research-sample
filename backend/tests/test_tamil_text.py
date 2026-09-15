"""app.ingest.tamil_text: the font's own glyph-repeat artifact, and what it should never
touch.

Every corrupted/clean word pair here is copied verbatim from the real CBSE Tamil Class X
book's own pymupdf extraction (not a synthetic example) -- see the module's own docstring
for how that was found and why the fix is safe.
"""

from __future__ import annotations

from app.ingest.tamil_text import clean_tamil_text


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
