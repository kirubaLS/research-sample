"""Write a sentence of context for every book chunk (Anthropic's contextual retrieval).

A passage that says "the modal class is the one with the greatest frequency" never says
which chapter or topic it belongs to, so a question that names the topic cannot find it.
This asks a small model, once per chunk, for one or two sentences situating the chunk in its
chapter, and stores them in ``book_chunk.context``. The retrieval index then indexes
context + passage (``YAADHUM_RETRIEVAL_CONTEXTUAL_PREFIX``); the context is never shown.

The chapter's whole text is sent as a cached prompt prefix, so a chapter of 40 chunks pays
for its text once and reads it back at a tenth of the price for the other 39. Run once per
book, not per paper. Dry run by default: it prints the chunk count and a cost estimate and
writes nothing.

    python -m scripts.contextualize_chunks --subject X.MATH               # estimate only
    python -m scripts.contextualize_chunks --subject X.MATH --apply       # write

A book imported again (``import_book_map``) rewrites its chunks and loses their context;
run this again afterwards. Embeddings are left as they were: they were made from the
passage alone, and re-embedding is a separate step (``scripts/embed_kb.py``).
"""

from __future__ import annotations

import argparse

DEFAULT_MODEL = "claude-haiku-4-5"
#: the context sentence's ceiling, in characters (the column is 400)
MAX_CONTEXT_CHARS = 380

SYSTEM = (
    "You write retrieval context for a textbook passage. Given a whole chapter and one "
    "passage from it, write one or two sentences that situate the passage: the chapter's "
    "subject, the topic or section it belongs to, and what the passage is about, in words a "
    "student's exam question on that topic would use. No preamble, no quotation marks, under "
    "60 words."
)


def chapter_document(chunks: list) -> str:
    """The chapter, passage by passage, as the cached prefix."""
    return "\n\n".join(
        f"[{c.reference or c.section_number or ''}] {c.text}" for c in chunks if c.text
    )


def request_for(chapter_label: str, document: str, chunk) -> dict:
    """The messages request for one chunk. The chapter text is the cached block."""
    return {
        "system": [
            {"type": "text", "text": SYSTEM},
            {"type": "text", "text": f"CHAPTER: {chapter_label}\n\n{document}",
             "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{"role": "user", "content": (
            f"Passage to situate ({chunk.reference or chunk.section_number or 'unnumbered'}):\n"
            f"{chunk.text[:2000]}")}],
    }


def clean(text: str) -> str:
    text = " ".join((text or "").split()).strip().strip('"')
    return text[:MAX_CONTEXT_CHARS].rstrip()


def contextualize(client, model: str, chapter_label: str, chunks: list, *,
                  max_tokens: int = 150) -> dict[str, str]:
    """chunk id -> context, for every chunk of one chapter. A chunk the model fails on is
    left out, not guessed at."""
    document = chapter_document(chunks)
    out: dict[str, str] = {}
    for chunk in chunks:
        if not chunk.text or getattr(chunk, "context", None):
            continue
        try:
            reply = client.messages.create(
                model=model, max_tokens=max_tokens, **request_for(chapter_label, document, chunk))
            text = "".join(b.text for b in reply.content if getattr(b, "type", "") == "text")
        except Exception as exc:  # noqa: BLE001 -- one chunk must not sink the book
            print(f"  skipped {chunk.id}: {type(exc).__name__}")
            continue
        if clean(text):
            out[chunk.id] = clean(text)
    return out


def estimate(chunks_by_chapter: dict[str, list], model: str) -> dict:
    """Rough tokens and dollars at ~4 characters a token: each chapter written to the cache
    once, read back for its other chunks, plus ~100 output tokens a chunk."""
    from app.llm import PRICES_PER_MTOK

    price_in, price_out, price_cache = PRICES_PER_MTOK.get(model, PRICES_PER_MTOK["claude-haiku-4-5"])
    todo = cached = written = out_tokens = 0
    for chunks in chunks_by_chapter.values():
        pending = [c for c in chunks if c.text and not getattr(c, "context", None)]
        if not pending:
            continue
        doc_tokens = len(chapter_document(chunks)) // 4
        written += doc_tokens
        cached += doc_tokens * (len(pending) - 1)
        todo += len(pending)
        out_tokens += 100 * len(pending)
    usd = (written * price_in * 1.25 + cached * price_cache + out_tokens * price_out
           + todo * 300 * price_in) / 1_000_000
    return {"chunks": todo, "cache_write_tokens": written, "cache_read_tokens": cached,
            "output_tokens": out_tokens, "estimated_usd": round(usd, 2)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--subject", required=True, help="subject code, e.g. X.MATH")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--apply", action="store_true", help="call the model and write contexts")
    args = ap.parse_args(argv)

    from collections import defaultdict

    from sqlalchemy import select

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import BookChunk, TaxonomyNode

    db = SessionLocal()
    try:
        chunks = list(db.scalars(select(BookChunk).where(
            BookChunk.subject_code == args.subject, BookChunk.bucket == "T")))
        by_node: dict[str, list] = defaultdict(list)
        for c in chunks:
            if c.node_id:
                by_node[c.node_id].append(c)
        labels = {n.id: n.label for n in db.scalars(select(TaxonomyNode).where(
            TaxonomyNode.id.in_(list(by_node))))}
        plan = estimate(by_node, args.model)
        print(f"{args.subject}: {plan['chunks']} chunks without context across "
              f"{len(by_node)} chapters; estimated ${plan['estimated_usd']} on {args.model}")
        if not args.apply:
            print("dry run: nothing written (add --apply)")
            return 0
        settings = get_settings()
        if not settings.anthropic_api_key:
            print("no YAADHUM_ANTHROPIC_API_KEY")
            return 1
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        written = 0
        for node_id, rows in by_node.items():
            made = contextualize(client, args.model, labels.get(node_id, ""), rows)
            for c in rows:
                if c.id in made:
                    c.context = made[c.id]
                    written += 1
            db.commit()
            print(f"  {labels.get(node_id, node_id)}: {len(made)}/{len(rows)}")
        print(f"wrote {written} contexts")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
