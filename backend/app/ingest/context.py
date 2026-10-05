"""The context a chunk is indexed with: where in the book it sits.

A passage is findable by the words it uses, but a question names its subject by the words
the CHAPTER uses. "The mode is found from the frequencies either side of the modal class"
never says "grouped data" or "Statistics"; the chapter it sits in does. Prefixing every
chunk, for the retrieval index only, with its chapter's title and its own section reference
closes that gap at no model cost -- the deterministic form of contextual retrieval, which
had a model write a sentence of context per chunk (Anthropic, "Contextual Retrieval").

Used by the lexical index. Embeddings are left alone: re-embedding the book is a separate,
paid step, and the chunk's stored vectors would no longer match what they were made from.
"""

from __future__ import annotations


def chunk_context(chunk, chapter_label_of) -> str:
    """``chapter_label_of(node_id)`` -> the chapter's title (None when unknown)."""
    parts = [chapter_label_of(chunk.node_id) or "", getattr(chunk, "reference", "") or ""]
    return " ".join(p for p in parts if p)
