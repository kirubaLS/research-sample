# Question Intelligence Schema — gap analysis against the built system

What the final schema requires, what the code already does, what has to change, and in
what order. Written against `backend/app/models/` as deployed.

---

## Summary judgement

Three of the schema's ideas are new *and load-bearing*, meaning code that exists today is
wrong rather than merely incomplete:

1. **Board Unit** replaces Chapter as the weight-bearing key. `ChapterWeight` is keyed on
   `chapter_id` and is the only weight source in the codebase. Every board-impact number
   the system can currently produce is computed off the wrong column.
2. **Chapter becomes optional.** The models assume a question always resolves to a chapter.
   A skill-anchored question has none, and forcing one is exactly the failure mode the
   rule exists to prevent.
3. **Concept Family / Variant** is the mechanism that makes "improved" mean learning rather
   than familiarity. Nothing in the code models it, and nothing enforces it.

Everything else is additive.

---

## Field-by-field status

| Schema field | In the code today | Verdict |
|---|---|---|
| Subject, Class | `TaxonomyNode` kinds `subject`, `grade` | Done |
| Chapter | `TaxonomyNode` kind `chapter`, assumed mandatory | **Must become optional** |
| Board Unit | *Absent* | **Must be added** |
| Curriculum Section | Approximated by `BookChunk.reference` | Must become a first-class field with a verification record |
| Concept Family | *Absent* | **Must be added** |
| Concept Variant | *Absent* | **Must be added, with a cross-cycle guard** |
| Prerequisite Concept | `Prerequisite` table exists and is wired | Table stays; **unwire from V1 reporting** |
| Marks, Question Type | `Question.max_marks`, `.question_type` | Done |
| Competency Tier | `QuestionTier` + `app/taxonomy/tier.py` | Done — see the naming and authority note below |
| Skill Required | *Absent* | Must be added (2B) |
| Complexity | *Absent* | Must be added (2B) |
| Dependency Level | *Absent* | Must be added (2B) |
| Difficulty | *Absent* | Correct as-is — **keep it absent** |
| Board Impact | *Absent* | Compute at analysis time, no storage |

---

## 1. Board Unit — the breaking change

The schema is precise: Board Unit is *"the only field the board-weight lookup ever reads
from"*, it may combine several chapters, and it may exist where no chapter does. That is a
different shape from a chapter, not a rename of one.

**Change:**

- Add `board_unit` to `NODE_KINDS`. It is a sibling of chapter under subject, not a parent
  of it — a chapter maps to a board unit, but the tree stays a tree.
- Add `BoardUnitWeight` (curriculum_version, board_unit_id, weight_pct, source_doc_url)
  and **delete `ChapterWeight`**. Two weight tables would guarantee two different answers
  to the same question; the citation column moves across unchanged, because a principal
  will challenge these numbers.
- Add `Question.board_unit_id`, **not null**. This is the one Layer 1 field with no
  conditional, and a null here silently removes the question from board-impact reporting.
- Add `chapter_to_board_unit` as an explicit many-to-one mapping table rather than
  inferring it from the tree — the Social Science case (History map marks belonging to
  Geography's unit) is exactly the case that inference gets wrong.

**Also change:** `app/analysis/paper_quality.py` reads chapter weights to judge blueprint
coverage. It has to read board-unit weights instead, or it will keep reporting a paper as
balanced against a scale the board does not use.

---

## 2. The conditional-Chapter rule

**Change:** make `chapter_id` and `curriculum_section` nullable together, and enforce the
pairing rather than trusting it:

```
CHECK ((chapter_id IS NULL) = (curriculum_section IS NULL))
CHECK (board_unit_id IS NOT NULL)
```

A half-filled row — chapter without section, or section without chapter — is the
force-fitting the rule forbids, and it is easier to reject at write time than to find in a
report later.

**Consequence for the diagnosis.** `app/analysis/diagnostics.py` aggregates mastery by
chapter. For skill-anchored questions there is no chapter to aggregate into, so it must
aggregate by **Concept Family** and treat chapter as one optional rollup among several.
This is the second-largest code change after Board Unit, and it is not cosmetic: a
diagnosis keyed on a nullable column silently drops every Reading and Grammar question.

---

## 3. Concept Family and Variant — the part with teeth

The schema states the contract plainly: Family is *held constant* across cycles, Variant
*must change*. The whole claim that a rising score means learning rests on this, and a
schema alone cannot keep it — the failure is silent and only appears as good news.

**Change:**

- `concept_family_id` on `Question`, **not null**, pointing at a stable node. This is the
  axis every trend report groups by.
- `concept_variant` as a per-question label plus a `variant_hash` over the normalised stem.
- **A cross-cycle guard, run when a paper is registered:** if a question's
  (family, variant_hash) has already been served to this section in a previous cycle, block
  the paper and name the repeated question. Not a warning — a warning gets clicked past,
  and the resulting score improvement is indistinguishable from real learning once it is
  in a report.

This is the single highest-value thing to build from this document, because it is the only
one whose absence produces a *confidently wrong* result rather than a missing one.

---

## 4. Curriculum Section, and "checked against the actual textbook"

The schema says these are verified against the current book, not written from memory. That
is a claim about provenance, so it needs a record, exactly as board weights have a citation.

**Change:** `curriculum_section` (e.g. `12.2`), `curriculum_section_title`, plus
`verified_against` (edition/print identifier) and `verified_at`. An unverified section
number is not an error, but it must be visibly unverified rather than indistinguishable
from a checked one. The open Geography Ch5/Ch6 item is precisely this state and should sit
in the data as such, not in a footnote.

---

## 5. Competency Tier — mostly built, two adjustments

`app/taxonomy/tier.py` already derives R&U / AP / AEC from action × familiarity, and
`QuestionTier` is append-only with abstention.

Two adjustments:

- **Naming.** The schema says one field, one name. The code emits `AP`; the schema writes
  `Applying`. Pick one at the storage layer and let the UI abbreviate. I suggest the
  schema's, since it is the board's own word.
- **Authority.** The schema places Tier in 2A: mechanical, checked against the blueprint,
  low disagreement. The code treats the derivation as authoritative and the blueprint as a
  tiebreak. Invert it: where the paper declares a blueprint, the blueprint *is* the answer
  and the derivation is a cross-check that raises a flag when it disagrees. The derivation
  keeps its real job — papers that declare nothing.

---

## 6. Layer 2B — the judgment fields and their gate

Skill Required, Complexity and Dependency Level are new, and the schema attaches a process
to them: two reviewers, disagreements resolved *before the question ships*.

**Change:** a `question_judgment` table (question_id, field, value, reviewer_id,
created_at), append-only, with more than one row per field being normal. A question is
shippable only when every 2B field has two independent judgments that agree, or a recorded
resolution. Report Cohen's κ per field per reviewer pair — a field that cannot reach
agreement is a badly defined field, and the schema already suspects this of Complexity.

**Carry the flagged item into the data:** Complexity does not map cleanly onto literary
interpretation. Until it does, allow Complexity to be explicitly `NOT_APPLICABLE` for those
questions rather than forcing single/multi-step. This mirrors `NOT_OFFERED` in the marks
engine, and for the same reason: a third state protects the analysis from a coerced value.

---

## 7. Difficulty — the correct behaviour is to keep not building it

The schema is right, and the code already complies by omission. Two things to make
deliberate:

- Never add a `difficulty` column. Derive it, from observed performance only.
- The threshold is **attempts AND schools > 1**. Note the consequence honestly: for the
  entire single-school pilot, difficulty is unavailable by definition. It should render as
  absent, never as a provisional number — a provisional difficulty is the number everyone
  will quote.

---

## 8. Board Impact — a join and a formula

```
Board Impact = (marks lost in board unit / marks available in board unit) × board weight
```

Computed at analysis time, stored nowhere. Two details the formula assumes and the code
must guarantee:

- "Marks available in this Board Unit, this test" is per-test, not per-syllabus, so it must
  respect choice groups and `NOT_OFFERED` — a question the student was never offered is not
  a mark available to them.
- Every question needs a board unit for the denominator to be true. Hence the not-null.

---

## What to do, in order

1. **Board Unit** — node kind, `BoardUnitWeight`, drop `ChapterWeight`, `Question.board_unit_id`,
   chapter→unit mapping. Repoint `paper_quality.py`. *Everything downstream depends on this.*
2. **Concept Family / Variant** and the cross-cycle repeat guard. Highest value: it is the
   only gap that produces a confidently wrong number.
3. **Conditional Chapter** — nullable pair, the two check constraints, and re-key
   `diagnostics.py` onto Concept Family.
4. **Layer 2B** — judgment table, two-reviewer gate, κ reporting, `NOT_APPLICABLE` complexity.
5. **Board Impact** — the computed overlay, once 1 is in place.
6. **Curriculum Section** with its verification record.
7. **Tier** — rename to the board's words, invert blueprint authority.
8. **Prerequisite** — leave the table, remove it from V1 reporting paths.

Items 1–3 are schema changes and want a single migration, before any real paper is tagged.
Retagging tagged papers is the expensive outcome this ordering avoids.

---

## Two things this schema does not cover

Neither is a criticism — they are the marks engine's layer, not the question's — but they
have to keep working alongside it:

- **Choice groups and `NOT_OFFERED`.** A question a student was never offered must not
  count as a mark lost, in Board Impact or anywhere else.
- **Mark association and the arithmetic oracle.** How a red mark on a page becomes a mark
  against an address is unchanged by any of this, and remains the accuracy-critical path.

## One open question for you

The pilot deployed today is the interest test; the marks engine's recognition backend is
not built. Items 1–3 change the database shape. Doing them now costs a migration against an
empty question table; doing them after the first real paper is tagged costs a retag. I would
do them now, before any question data exists, and I would not start the recognition backend
until Board Unit is settled — it writes into exactly these tables.
