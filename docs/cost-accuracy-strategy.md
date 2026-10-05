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

- **Several questions per call.** Each question's evidence differs, so batching them changes what
  every question is shown. Not worth the accuracy risk without a live evaluation.
- **Self-consistency re-asks.** Thinking models expose no sampling temperature; a re-ask with the
  same prompt returns the same answer. The gate, memory and verification already abstain to a
  person where it matters.
- **Contextual chunk prefixes** (Anthropic's contextual retrieval): needs an LLM pass and a
  re-embed of every book at ingest. Worth doing once the gate's shadow numbers show where
  retrieval fails.
- **A trained distilled classifier.** The nearest-neighbour vote over confirmed questions does the
  same job without a model to retrain; revisit with a few hundred confirmations per subject.
- **Expanding the gold set and running `eval_dense_retrieval.py`.** Needs the production database.

## Reading the results honestly

The research figures above come from other tasks (general QA, FAQ traffic, math-question
tagging) and are an argument for trying a lever, not a prediction of the saving here. The
shadow runs are what measure it.
