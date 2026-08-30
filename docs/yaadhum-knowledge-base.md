# Knowledge base — structure and build plan

How a subject's book becomes data the system can use. One pipeline, one profile per
subject, five stages, four tables.

---

## 1. The four layers, and where each comes from

The knowledge base is not one store. It is four, stacked, and they have different sources,
different owners and different lifetimes. Collapsing them into a single vector index is
the failure mode this structure exists to prevent.

| # | Layer | Source | Who authors it | Changes |
|---|---|---|---|---|
| 1 | **Board skeleton** — units and their weightage | CBSE syllabus PDF | Us, once per subject | When the board revises |
| 2 | **Book tree** — chapter → topic → sub-topic | NCERT book | Extracted | When the book revises |
| 3 | **Content** — T and E chunks, canonical procedures | NCERT book | Extracted | With the book |
| 4 | **Concept families** — the stable trend axis | Curated from layer 2 | Us, deliberately | **Never, once live** |

Layer 1 is not in the book. The book never says Algebra spans four chapters — that is a
syllabus fact. Layer 4 is not in the book either: it is a judgement about what should stay
comparable across test cycles, and renaming one after a class has been tested breaks every
trend that references it.

---

## 2. The tables (all exist today)

```
taxonomy_node          the tree: board_unit | chapter | subtopic | concept_family
board_unit_weight      weightage per board unit, with the syllabus URL as citation
chapter_board_unit     explicit chapter -> unit mapping, never inferred
book_chunk             T/E content, one row per passage, with stem_hash + embedding
canonical_procedure    theorems and worked examples, for exact-match familiarity
```

**Why `canonical_procedure` is separate from `book_chunk`.** Familiarity has to answer
"is this question literally Theorem 1.3?" — a hash comparison, yes or no. If that lived
only in the vector store it would become "is this similar enough to Theorem 1.3?", which
needs a threshold, and the threshold would be tuned per subject forever.

---

## 3. The two buckets

Every extracted passage lands in exactly one:

| Bucket | What goes in | Familiarity it supports |
|---|---|---|
| **T** | Theorems, definitions, worked/solved examples in the chapter body | `T_VERBATIM` — the method was taught as content |
| **E** | End-of-chapter exercises, past-paper items | `PRACTISED` — the method was drilled |

Anything the book does not contain is `ADAPTED` or `NOVEL`, decided by distance from these
two. So the book's job is to make "the student has seen this before" answerable, and
nothing else.

**The book cannot tell you the tier.** Tier is *action × familiarity*. The question's verb
gives the action; the book gives only familiarity. That split is the entire reason to
ingest a book rather than prompt a model about a chapter name.

---

## 4. The five stages

```
  syllabus PDF                    book PDF
       |                             |
       v                             v
 [1] board units            [2] structure pass
 weights + citation         bookmarks/TOC -> chapter tree
       |                             |
       +------ [3] mapping ----------+      chapter -> board unit, by hand, reviewed
                     |
                     v
              [4] content pass                T/E split, canonical procedures, embeddings
                     |
                     v
              [5] concept families            curated from the topic level
```

### Stage 1 — board units
Input: the CBSE syllabus document for the subject.
Output: `taxonomy_node(kind='board_unit')` + `board_unit_weight`, each carrying
`source_doc_url`. A principal will challenge these numbers, so the citation is not optional.

### Stage 2 — structure pass
Input: the book PDF.
Method: PDF bookmarks and the table of contents first; heading patterns only as a fallback.
**Never blind chunking** — NCERT numbers its own sections (`12.2 Volume of Combination of
Solids`), and those numbers are the `curriculum_section` field. Extracting them is what
makes that field verifiable rather than remembered.
Output: `taxonomy_node(kind='chapter'|'subtopic')`, each with its section number.

### Stage 3 — mapping
Input: stages 1 and 2.
Method: **by hand, reviewed once per subject.** Twelve rows for Maths. This is not inferred
from the tree, because the case that decides it is History map marks counting towards
Geography's unit — inference gets exactly that wrong.
Output: `chapter_board_unit`.

### Stage 4 — content pass
Method: split on the book's own labels — "Theorem", "Example", "EXERCISE". These are
conventions the book already follows, so this is pattern-matching, not judgement.
Output: `book_chunk` (bucket T or E, normalised text, `stem_hash`, embedding) and
`canonical_procedure` for each theorem and worked example.

### Stage 5 — concept families
Method: curated from the sub-topic level. **Not auto-generated.**
Output: `taxonomy_node(kind='concept_family')`.
This is the one stage to slow down on. Everything above can be re-run; a concept family is
a commitment, because it is held constant across cycles so that improvement is comparable.

---

## 5. The per-subject profile

One YAML per subject. Everything that differs between books lives here, so the pipeline
itself stays single.

```yaml
# profiles/x-maths.yaml
subject_code: X.MATH
curriculum_version: CBSE-2026-27
syllabus_url: https://cbseacademic.nic.in/...

structure:
  source: bookmarks          # bookmarks | toc | headings
  section_pattern: '^(\d+\.\d+)\s+(.+)$'

buckets:
  T:
    - '^Theorem\s+\d+\.\d+'
    - '^Example\s+\d+'
    - '^Activity\s+\d+'      # Science uses these; harmless where absent
  E:
    - '^EXERCISE\s+\d+\.\d+'

skill_anchored: false        # true for English Reading/Grammar: no chapter exists
```

### What each subject needs

| Subject | Bucket T labels | Notes |
|---|---|---|
| Mathematics | Theorem, Example | Cleanest case; build here first |
| Science | Activity, Example, Fig. captions | Activities are genuinely a third kind of "taught" |
| Social Science | Case study, Source, map plates | Map work is why the unit split matters |
| English — Literature | The text itself | Behaves like any other subject |
| English — Reading & Grammar | *none* | `skill_anchored: true`. No chapter, no chunks. Concept families are skill labels, authored directly |

---

## 6. Retrieval, once it is loaded

Two lookups, in this order, and **never a global search**:

1. **Exact** — `stem_hash` against `canonical_procedure`. Answers "is this the taught
   procedure?" with a yes or no.
2. **Scoped vector** — nearest chunks *within an already-narrowed chapter*.

A global vector search across every subject will return a Science paragraph for a Maths
question and it will look plausible. Scope is not an optimisation here; it is the thing
that keeps the answer right.

---

## 7. Build order

1. `scripts/ingest_syllabus.py` — stage 1. Small, and unblocks board impact.
2. `scripts/ingest_book.py --dry-run` — stages 2 and 4, printing the extracted tree and
   bucket counts **without writing**. Inspect before committing; a bad structure pass
   poisons everything downstream and is invisible once loaded.
3. Same script without `--dry-run`.
4. `scripts/map_chapters.py` — stage 3, an interactive confirm per chapter.
5. Concept families — reviewed, then loaded.

Do Maths end to end before starting a second subject. You have eight real papers to check
the extraction against, and the profile format will change once a real book has been
through it — better that it changes after one subject than after four.

---

## 8. What can go wrong, and where it shows

| Failure | Where it surfaces | Guard |
|---|---|---|
| Structure pass mis-reads the tree | Everywhere, silently | `--dry-run` inspection before writing |
| A chapter mapped to the wrong board unit | Board impact points at the wrong unit | Stage 3 is manual and reviewed |
| Concept family renamed after go-live | Every trend comparison breaks | Treat as immutable; add, never rename |
| Global vector search | A confident answer from the wrong subject | Scope every query to a chapter |
| Book edition drift | `curriculum_section` cites a section that moved | `verified_against` records the edition |
