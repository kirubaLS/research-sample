# Cutting the cost and raising the accuracy of question-to-chapter mapping

What the research says, what is built, what each switch does, and the order to turn them on.
Every lever is off by default; nothing here changes a run until a flag is set.

## Where the money goes

A 40-question paper makes roughly 150-250 judge calls: the chapter judge (1-2 per question),
the topic judge (2-8, typically 3-4, over the whole cached chapter), and, for a scanned paper,
one vision call per page on the strongest model. Cutting the *number of calls* is the largest
lever; thinking tokens are the next.

## Built

| Lever | Flag | What it does | Evidence |
|---|---|---|---|
| Cache-write pricing | always on | `estimate_usd` bills cache writes at 1.25x input; `cache_write_tokens` reported per job | Anthropic pricing |
| Tier 0 chapter gate | `YAADHUM_CHAPTER_GATE` (shadow), `_ENFORCE` | Both retrievers agree on a chapter with a clear relative lead: skip the chapter judge | cascade routing, [FrugalGPT](https://arxiv.org/pdf/2305.05176) |
| Reranker as third reader | `YAADHUM_CHAPTER_GATE_RERANKER` | Jina cross-encoder must not prefer another chapter | reranking cut retrieval failures by a further 49%→67% in [Anthropic's contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) |
| Confirmed-question memory | `YAADHUM_MEMORY_RECALL` / `_REUSE` | A near-identical question a teacher already confirmed takes that chapter, section and tier with no model call | semantic caching, [GPT Semantic Cache](https://arxiv.org/pdf/2402.01742) |
| Worked examples | `YAADHUM_MEMORY_DEMOS=n` | The nearest confirmed questions go in the chapter judge's prompt | retrieved demonstrations, [KnowTS](https://arxiv.org/pdf/2406.13885) |
| Nearest-neighbour vote | part of memory | A cheap classifier that improves with each confirmation, with no training step | distillation without a model to maintain |
| Adaptive topic reads | `YAADHUM_TOPIC_ADAPTIVE_READS` | Skip the second ("taught") read when the first is corroborated; answerability check still runs | |
| Vision cascade | `YAADHUM_VISION_CHEAP_MODEL` | Cheap model first; the strong one only if the paper's own total and count are not reproduced | cheap-first OCR cascades |
| Grouped chapter-judge calls | `YAADHUM_CHAPTER_JUDGE_GROUP_SIZE=n` | n questions per call via `classify_many`; a question the answer misses is asked alone | batch prompting, [routing with batch prompting](https://arxiv.org/pdf/2605.28268) |
| Reordered re-ask | `YAADHUM_CHAPTER_RECHECK` | A low-confidence answer is re-asked twice with the passages reordered; majority wins; an answer nobody repeats is capped at 0.4 for review | self-consistency and abstention ([survey](https://aclanthology.org/2025.tacl-1.26.pdf)); reordering stands in for sampling temperature |
| Contextual retrieval prefix | `YAADHUM_RETRIEVAL_CONTEXTUAL_PREFIX` | Each chunk is indexed with its chapter title and section reference; no LLM, no re-embed | [contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) (deterministic form) |
| Memory vote as a fourth reader | with memory + gate | Confirmed similar questions unanimous in another chapter veto the gate | kNN over confirmed labels |
| Trained classifier as a fifth reader | `YAADHUM_CHAPTER_GATE_CLASSIFIER` | Naive Bayes trained on the book's chunks and confirmed questions; confident about another chapter = the gate does not pass | a cheap model with a different inductive bias from retrieval |
| Model-written chunk context | `python -m scripts.contextualize_chunks --subject X.MATH --apply` | One model-written sentence per chunk (chapter cached, Haiku), stored in `book_chunk.context` and indexed with the chunk; dry run prints a cost estimate | [contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) proper; needs migration `b7d3e1f4a9c2` (additive, runs on boot) |
| Gold-set export | `python -m scripts.export_gold` | Turns a reviewed paper into a gold key for `eval_mapping` / `eval_dense_retrieval` | evaluation grows with the review queue |
| Chapter judge batched | `YAADHUM_BATCH_CHAPTER_JUDGE` | Existing flag; half price for an added batch wait | Batches API 50%, stacks with caching |

## Roll-out order

1. **Shadow.** Set `YAADHUM_CHAPTER_GATE=true` and `YAADHUM_MEMORY_RECALL=true`. Judges still run
   on everything. Each place job's result gains `chapter_gate` and `memory` blocks.
2. **Read the numbers.** `python -m scripts.tune_gate` sweeps the margin over the stored shadow data
   and recommends the loosest one whose agreement clears a bar (default 98% on 30+ questions).
   The `memory` block gives `reusable` and `agreed_with_judge` the same way.
3. **Enforce, one at a time.** `YAADHUM_MEMORY_REUSE=true` first (the safest: a person already
   confirmed it), then `YAADHUM_CHAPTER_GATE_ENFORCE=true` at the recommended margin. Compare the
   review queue before and after.
4. **Cheaper reads.** `YAADHUM_MEMORY_DEMOS=3`, `YAADHUM_TOPIC_ADAPTIVE_READS=true`, and the chapter
   judge in batch.
5. **Scanned papers.** `YAADHUM_VISION_CHEAP_MODEL=claude-haiku-4-5` only after reading a few papers
   both ways and comparing the *stems*: the checksums see marks and counts, not misread wording.

## Not built, and why

- **The vision cascade is built but unproven** and stays off; see its caution above.
- **Re-embedding with context.** The context sentence is indexed by the lexical index only. The
  stored vectors were made from the passage alone; re-embedding is a separate paid step.
- **Running the dense-retrieval eval and the context script.** Both need your database and API key;
  `export_gold` and `contextualize_chunks` (dry run first) are the tools.

## Reading the results honestly

The research figures above come from other tasks (general QA, FAQ traffic, math-question
tagging) and are an argument for trying a lever, not a prediction of the saving here. The
shadow runs are what measure it.
