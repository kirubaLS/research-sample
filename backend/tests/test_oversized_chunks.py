"""extract_chunks: no single Chunk can exceed Jina's per-item token budget.

Real production bug: /platform/books/X.HIN.KR/embed 502'd with Jina's own "Input text
exceeds the model's maximum of 32768 tokens". A single_section Hindi chapter has no
subheadings to split its body on the way a numbered-section book's does, so an entire
OCR'd chapter became one Chunk -- and Devanagari's conjunct clusters tokenize dense enough
that even a chapter well under a "normal" character count can still blow the token
ceiling. MAX_CHUNK_CHARS/_split_oversized_body is the fix: split on paragraph boundaries
before a chunk is ever created, never after.
"""

from __future__ import annotations

from app.ingest.book import MAX_CHUNK_CHARS, Section, extract_chunks


def test_a_body_under_the_budget_stays_a_single_chunk():
    text = "पर हमने मइयाँ के आँचल की-प्रेम और शांति के चँँदोवे की-छाया न छोड़ी। " * 5
    chunks = extract_chunks(text, 1, sections=[Section("1", "t", 0, len(text))])
    assert len(chunks) == 1
    assert chunks[0].reference == "Section 1"


def test_a_body_over_the_budget_is_split_on_paragraph_boundaries_not_lost():
    paragraph = "पर हमने मइयाँ के आँचल की-प्रेम और शांति के चँँदोवे की-छाया न छोड़ी। " * 50
    text = "\n\n".join([paragraph] * 5)
    assert len(text) > MAX_CHUNK_CHARS * 2

    chunks = extract_chunks(text, 1, sections=[Section("1", "t", 0, len(text))])

    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
    assert [c.reference for c in chunks] == [f"Section 1 (part {i})" for i in range(1, len(chunks) + 1)]
    # nothing lost in the split, modulo the whitespace strip/join at each boundary
    assert "".join(c.text for c in chunks).replace("\n\n", "").replace(" ", "") == \
        text.replace("\n\n", "").replace(" ", "")


def test_a_single_paragraph_bigger_than_the_budget_is_hard_split():
    """No paragraph break to split on at all -- OCR sometimes runs a whole page together
    with no blank line. Still has to stay under budget rather than pass a giant chunk
    through untouched."""
    text = "अ" * (MAX_CHUNK_CHARS * 2 + 500)
    chunks = extract_chunks(text, 1, sections=[Section("1", "t", 0, len(text))])
    assert len(chunks) == 3
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
    assert sum(len(c.text) for c in chunks) == len(text)
