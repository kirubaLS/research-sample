# Yaadhum — Complete Backend Logic

## Eight real CBSE 2026 papers, the full pipeline, and how tiers are decided

---

## 1. The consolidated corpus

Eight papers now measured. Every structural axis has at least two values, which is the argument for
discovering everything per paper rather than hardcoding per subject.

| # | Subject | Code | PDF pp | Logical pp | Text layer | Imposition | Rotation | Languages | Sections |
|---|---|---|---|---|---|---|---|---|---|
| 1 | English Lang. & Lit. | 2/7/3 | 19 | 19 | Yes, clean | 1-up | 0° | English | 3 |
| 2 | Science (V.I.) | 31(B) | 27 | 27 | Yes | 1-up | 0° | Bilingual | 3 = disciplines |
| 3 | Social Science | 32/7/1 | 27 | 27 | Partial | 1-up | 0° | Bilingual | 4 = sub-subjects |
| 4 | Mathematics Std | 30/7/1 | 7 | 27 | **None (vector)** | **4-up** | 0° | Bilingual | 5 |
| 5 | Mathematics Std | 30(B) | 6 | 23 | **None (vector)** | **4-up** | 0° | Bilingual | 5 |
| 6 | Hindi Course B | 4/8/3 | 16 | 16 | **None (vector)** | 1-up | 0° | Hindi | 4 |
| 7 | Hindi Course B | 4/7/2 | 11 | 11 | **None (vector)** | 1-up | 0° | Hindi | 4 |
| 8 | Tamil | 10 / Set 4 | 6 | 12 | **None (vector)** | **2-up** | **90°** | Tamil | 5 |

**Five of eight have no text layer** — but all five are *vector* PDFs with glyphs converted to
outlines, not scans. Rendered at 400 DPI the input is pristine.

### The bilingual rule the Maths papers gave us

In both Maths papers the tiles alternate by logical page: **odd logical pages are English, even
pages are the Hindi translation of the same questions.** Q26 appears on logical page 15 (English)
and again on page 16 (Hindi). That is a deterministic de-duplication rule for this family — no
language detection needed, just parity — with script detection as the fallback check.

### The section arithmetic the papers print for us

Maths 30(B) prints, per section:

```
SECTION B  This section has 5 Very Short Answer (VSA) type questions carrying 2 marks each.   5×2=10
SECTION C  This section has 6 Short Answer (SA) type questions carrying 3 marks each.         6×3=18
SECTION D  This section has 4 Long Answer (LA) type questions carrying 5 marks each.          4×5=20
```

Section A (20 MCQ/Assertion–Reason × 1) = 20, Section E (case-based 3 × 4) = 12.
**20 + 10 + 18 + 20 + 12 = 80.** The paper hands us the entire blueprint, verified, in printed text.

---

## 2. Backend logic — the twelve stages

Each stage is an idempotent job keyed by `(assessment_id, stage, input_hash)`. Re-running a stage
never duplicates rows; it writes a new version and the projection resolves by precedence.

### Stage 1 — Ingest and fingerprint
**In:** an uploaded PDF or a set of camera frames.
**Do:** SHA-256 the bytes; if seen before, short-circuit to the existing `assessment`. Count pages,
vector drawings, raster images and extractable characters per page.
**Decide the route:** `text_chars > 200/page` ⇒ text-assisted path; else ⇒ vision path.
**Stack:** PyMuPDF, FastAPI upload, S3.
**Writes:** `assessment(source_sha, page_count, route)`.

### Stage 2 — Detect orientation
**Do:** page metadata is not trustworthy (all eight report `rotation = 0`; Tamil is printed at 90°).
Render at 150 DPI, compute a horizontal projection profile at 0/90/180/270°, take the angle whose
profile variance is highest — text lines only produce sharp periodic peaks when horizontal.
**Stack:** PyMuPDF render, NumPy.
**Writes:** `assessment.rotation`.

### Stage 3 — Detect and undo imposition
**Do:** count matches of `Page\s+(\d+)\s+of\s+(\d+)` per PDF page ⇒ *k*-up. Cross-check
`ceil(M / k) == pdf_page_count`. Cluster the footer bounding boxes into a tile grid, crop on the
dashed cut lines, and **order tiles by the printed logical page number**, never by position.
**Observed:** 1-up (five papers), 2-up (Tamil), 4-up (both Maths).
**Stack:** OpenCV line detection, regex, NumPy.
**Writes:** `logical_page(assessment_id, index, bbox, source_pdf_page)`.

### Stage 4 — Render for reading
**Do:** vector PDFs render at **400 DPI** (no scanning noise, no resolution ceiling); scanned input
gets dewarp, illumination flattening and deskew first.
**Stack:** PyMuPDF, OpenCV.
**Writes:** page PNGs to S3, referenced by `logical_page`.

### Stage 5 — De-duplicate language
**Do:** Maths family ⇒ parity rule (odd = English, even = Hindi). Otherwise detect script per text
block by Unicode range (Latin / Devanagari / Tamil). Keep one canonical stream; attach the other as
a translation of the **same address**. Never create a second Q-matrix row.
**Why it matters:** naive mark sums we measured were 90 / 172 / 349 against a stated maximum of 80.
**Stack:** `unicodedata`, regex.
**Writes:** `logical_page.language`, `logical_page.is_canonical`.

### Stage 6 — Parse the General Instructions block
**Do:** extract the declared facts that every paper prints on page 1 — question count, section names
and marks, question types with their marks and word limits, and the paper total. These become
**verification equations**, not prose.
**Stack:** `claude-opus-5` with a strict output schema.
**Writes:** `assessment.declared(question_count, sections[], total_marks, type_rules[])`.

### Stage 7 — Extract addresses and marks
**Do:** per logical page, extract every question address with its marks.
- **Address** = `SECTION / QUESTION_NO / SUB_PART / CHOICE_ALT` — e.g. `C / 27 / – / b`.
- **Mark-label grammar**, three accepted forms:

| Form | Example | Take | Bonus |
|---|---|---|---|
| Bare integer, right-aligned at x ≈ 0.88 W | `3` | 3 | measured constant across all text-layer papers |
| Product | `6×3=18` | 18 | also gives sub-part count and per-part marks; `a×b=c` self-checks |
| Section header | `(Grammar) 12 Marks` | section total | another verification equation |

- **Page-furniture filter:** any numeral at the same normalised coordinates on ≥3 pages is furniture
  (Q.P. code, page number, set number), not a mark. The Tamil paper's Q.P. code is literally `10` —
  a plausible mark — printed on every page.
**Stack:** `claude-opus-5` vision with `strict: true` tools; two independent passes with a
field-level diff.
**Writes:** `question(address, max_marks, stem_text, choice_group_id, question_type)`.

### Stage 8 — Group internal choice
**Do:** an `OR` / `अथवा` / equivalent line between two alternatives at the same address level creates
a `choice_group_id`. The group contributes its marks **once** to every total.
**Observed:** 6 OR blocks in English, 9 in Science, 6 in Social Science, and both Maths papers use
choice in Sections B–E.
**Writes:** `question.choice_group_id`.

### Stage 9 — Verify (hard gate)
Four equations, all from the paper itself:
1. extracted question count == declared count
2. per-section marks, after de-duplication and choice-grouping == declared section marks
3. section arithmetic `a × b = c` holds where printed
4. sum over sections == `Maximum Marks : 80`

Any failure blocks the paper and shows the teacher **which equation broke and where**. It never
guesses.

### Stage 10 — Classify
Per address: **skill tags** and **cognitive tier**. Skills first (retrieval + constrained LLM +
conformal abstention, as designed earlier); tier by the four-signal ensemble in §3.
**Writes:** `question_skill(address, skill_id, weight)`, `question_tier(address, tier, confidence,
conformal_set)`.

### Stage 11 — Teacher confirmation → freeze
One screen. Each row shows the crop, the proposed skill and tier, and the rationale. On confirm the
**Q-matrix is frozen and versioned**; the `analysis_run` records the taxonomy version and every
model version used. Confirmed rows are written to the Question Library keyed by paper code, so the
next school using the same paper inherits them at confidence 1.0.

### Stage 12 — Answer-sheet mapping
Covered in §4.

---

## 3. How R&U / AP / AEC is decided

Tier is the hardest of the three labels because it is a judgement about cognitive demand, not a fact
printed on the page. So it is never one model asked once. **Four independent signals, fused and
calibrated, with an abstain option.**

![Figure C](FIGC)

*Figure C — the four-signal tier classification ensemble, with a worked example.*

### Signal 1 — Structural prior (free, deterministic)
Question type, marks, and section position. CBSE papers correlate these with tier strongly: 1-mark
MCQs skew R&U, 5-mark LAs skew AEC, 4-mark case-based questions skew AP/AEC. Output is a prior
distribution over the three tiers, never a label.

### Signal 2 — Bloom verb lexicon (a data table per language)

| Tier | English | Hindi | Tamil |
|---|---|---|---|
| **R&U** | state, define, name, list, identify, recall, choose the correct option, match, what is | बताइए, लिखिए, समझाइए | எழுதுக, விளக்குக |
| **AP** | calculate, find, solve, compute, prove, determine, construct, draw, apply, use | ज्ञात कीजिए, सिद्ध कीजिए, हल कीजिए | கண்டறிக, தீர்க்க |
| **AEC** | justify, evaluate, analyse, compare and contrast, comment, criticise, suggest, design, in your opinion, give reasons | मूल्यांकन कीजिए, समीक्षा कीजिए, अपने विचार | மதிப்பிடுக, ஆய்க |

Curated once per language, versioned as data. Not code, and not a model.

### Signal 3 — Novelty against NCERT (the differentiator)
Retrieve the item against the NCERT exercise corpus and the validated Question Library:

- near-verbatim match to an NCERT exercise ⇒ **reproduction** ⇒ R&U or routine AP
- known method in an unfamiliar context ⇒ **AP**
- unseen, or spanning ≥ 2 sub-topics in the Q-matrix ⇒ **AEC**

This is the signal that catches the trap the verb lexicon falls into. *"Prove that √5 is an
irrational number"* carries the verb **prove** — which reads as AP — but it is a standard NCERT
theorem that students memorise, so its real demand is reproduction. Only the retrieval signal knows
that.

### How signals 2 and 3 actually compose — the verb never outputs a tier

The verb lexicon on its own is wrong, and it is wrong in a predictable way. The fix is not a better
lexicon; it is to stop asking the lexicon for a tier at all.

**Bloom level = action × familiarity.** "Applying" means carrying out a known procedure in a *new*
situation. If the exact task was taught and memorised, the same action is Remembering. So the
lexicon outputs an **action class**, and only the combination with a familiarity score produces a
tier.

**Step 1 — the lexicon emits an action, not a tier**

| Action class | English triggers | Hindi | Tamil |
|---|---|---|---|
| RECALL | state, name, list, define, write the value of | बताइए, लिखिए | எழுதுக |
| EXPLAIN | explain, describe, what is meant by | समझाइए, वर्णन कीजिए | விளக்குக |
| EXECUTE | find, calculate, solve, determine, evaluate (numeric) | ज्ञात कीजिए, हल कीजिए | கண்டறிக, தீர்க்க |
| PROVE | prove, show that, verify | सिद्ध कीजिए | நிரூபிக்க |
| APPLY-IN-CONTEXT | a word problem, a real-world frame, a case study | — | — |
| ANALYSE / EVALUATE / CREATE | justify, compare, comment, criticise, suggest, design, in your opinion | मूल्यांकन कीजिए, अपने विचार | மதிப்பிடுக, ஆய்க |

**Step 2 — a familiarity score F, against two separate buckets**

Retrieve the normalised stem (numbers → `<NUM>`, names → `<NAME>`) against:

- **Bucket T — taught as content.** NCERT theorems, worked examples and solved examples *in the
  chapter body*. A match here means the student has seen the answer written out.
- **Bucket E — exercise practice.** NCERT end-of-chapter exercises and the school's past papers.

`F = max(cosine similarity)` per bucket, with an exact-hash channel on top. A Bucket T match is much
stronger evidence of reproduction than a Bucket E match.

**Step 3 — a 2-D table decides the tier**

|  | F ≥ 0.85 — verbatim or near | 0.55 ≤ F < 0.85 — same method, new numbers or frame | F < 0.55 — novel |
|---|---|---|---|
| RECALL · EXPLAIN | R&U | R&U | R&U |
| **EXECUTE · PROVE** | **R&U** ← *the √5 case* | **AP** | AEC |
| APPLY-IN-CONTEXT | AP | AP | AEC |
| ANALYSE · EVALUATE · CREATE | AP | AEC | AEC |

Worked through:

- *"Prove that √5 is an irrational number."* → action **PROVE**, and it matches **Bucket T** at
  F ≈ 0.94 — it is a named theorem in the NCERT chapter body. Table gives **R&U**. Correct: the
  student is reproducing a proof they were taught line by line.
- *"Prove that 3 + 2√5 is irrational."* → same action, F ≈ 0.70 against Bucket E. Table gives
  **AP**. Correct: the method is known, the object is new.
- *"Prove that the parallelogram circumscribing a circle is a rhombus."* → PROVE, F < 0.55 if it is
  not in the taught set. Table gives **AEC**.

The table is small, auditable, and a head of department can argue with it — which is exactly what you
want from a rule that assigns a contested label.

**Step 4 — for the taught-verbatim bucket, stop doing retrieval and just enumerate it**

This is the practical shortcut that makes the whole thing cheap. **For Class X Maths there are only
about 40–60 named theorems and standard proofs.** Enumerate them once into a table:

```sql
create table canonical_procedure (
  id            uuid primary key,
  curriculum_version text not null,      -- 'CBSE-2026-27'
  subject_id    uuid not null,
  chapter_id    uuid not null,
  name          text not null,           -- 'Irrationality of root 5'
  canonical_stem text not null,          -- for embedding + hashing
  taught_verbatim boolean not null,      -- true => Bucket T
  aliases       text[]                   -- common rewordings, incl. HI/TA
);
```

Seed rows for Class X Maths: irrationality of √2 / √3 / √5, Fundamental Theorem of Arithmetic,
relationship between zeroes and coefficients, Basic Proportionality Theorem and its converse,
Pythagoras and its converse, tangent ⟂ radius, equal tangents from an external point, area of a
sector, distance and section formulas, sin²θ + cos²θ = 1 and the derived identities, nth term and
sum of an AP.

That is **one day of work, once**, reusable across every school and every year the syllabus is
unchanged. For those items the familiarity signal is not fuzzy retrieval at all — it is an exact
lookup, deterministic and free.

**Step 5 — let response data falsify the label later**

Once a paper has been attempted, item difficulty gives you a free third opinion. Across a class,
R&U items should on average be easier than AP items, which should be easier than AEC items. An item
whose difficulty (p-value) sits two standard deviations out of place for its assigned tier is routed
back for re-review. This costs no human time and it catches exactly the systematic errors a lexicon
makes.

**Step 6 — and let the school win the argument**

Reasonable teachers genuinely disagree on tier. Overrides are stored per school in the taxonomy, not
patched into the model. If a school insists that proving √5 is Applying for their students, their
taxonomy says so, their reports follow it, and their Question Library records who decided and when.

### Signal 4 — LLM judgement, constrained
`claude-opus-5`, output restricted to the three tiers, with a required rationale. The prompt carries
the CBSE tier definitions, the school's own adjudicated exemplars, and signals 1–3 as stated
evidence. Self-consistency at k = 5; the vote spread is kept as an uncertainty measure.

### Fusion
- **Cold start** (under ~200 adjudicated items): fixed weights — LLM 0.45, verbs 0.25, novelty 0.20,
  structure 0.10.
- **Once the adjudicated set grows:** multinomial logistic regression over all four signal vectors
  plus marks, question type, section and sub-topic count. Fitted on your own adjudicated data.
- The dashboard always states which mode is active.

### Abstention
Split conformal prediction on a held-out adjudicated set, calibrated so the returned **set** contains
the truth with probability ≥ 1−α. Set size 1 ⇒ auto-accept. Set size > 1 ⇒ teacher review with the
candidates pre-selected. **Expect tier abstention at roughly three times the chapter rate.** That is
the honest cost of a label that is genuinely a judgement, and it should be budgeted, not engineered
away.

### The paper-level tie-breaker, and when not to use it
CBSE targets R&U 54% / AP 24% / AEC 22% of marks.

- **Board paper, blueprint declared:** nudge *only the abstained items* so the paper's tier
  mark-shares move toward the target. Confident items are never moved. A Sinkhorn-style adjustment,
  used strictly as a tie-break.
- **School unit test: never apply it.** A school paper deviating from 54/24/22 is not an error to
  correct — it is the single most valuable line in the paper-quality report ("this paper is
  recall-heavy: 71% R&U against a 54% target"). Applying the prior there would erase the finding we
  sell.

### Why four signals rather than one good prompt
Each fails differently. The verb lexicon is fooled by *prove* on a memorised theorem. Novelty
retrieval is fooled by a reworded stem. The structural prior is fooled by an unusual paper. The
model is fooled by its own plausible rationale. Fusing four uncorrelated failure modes, then
abstaining when they disagree, is what makes the label defensible to a head of department.

### Validation
Two independent reviewers on the pilot set; report **Cohen's κ** per level. Target κ ≥ 0.85 chapter,
≥ 0.75 sub-topic, ≥ 0.70 tier. Later, Q-matrix refinement from response data acts as a third,
tireless reviewer: items whose response patterns contradict their assigned tier are routed back for
review.

---

## 4. Mapping to the answer sheet

### 4.1 Locate
1. **Ink separation** — teacher red, student black/blue. Per-school hue centroids fitted by k-means
   on ink pixels from three unlabelled pages; long straight red structures removed first (the printed
   margin rule).
2. **Anchors from the student layer.** Every one of the eight papers instructs: *"Please write down
   the Serial Number of the question in the answer-book at the given place before attempting it."*
   The anchor is a field the board requires the student to fill in.
3. **Mark candidates from the teacher layer** — isolated and circled numerals; ticks, crosses and
   strikes excluded by shape; page and section totals detected separately as extra equations.

### 4.2 Resolve the address
1. Normalise: strip punctuation, map Devanagari and Tamil numerals, fold script variants
   (`16(b)` = `Q.16 b` = `16 (kha)`).
2. **Closed vocabulary** — the parsed address must exist in the frozen Q-matrix. `16(c)` does not
   exist on this paper, so it is rejected, never invented.
3. **Section prior** — a page inside the Geography block resolves an ambiguous `4` to `B/4`.
4. **Monotonicity** — addresses should advance down the script; a break is a flag, not a silent
   reorder.

### 4.3 Bind and reconcile
Cost matrix over vertical distance, answer-block containment, side consistency and value
plausibility ⇒ **Hungarian algorithm** (`scipy.optimize.linear_sum_assignment`). Then refit the
teacher's own layout convention from the confident bindings and solve again.

Then the constraint solver:

```
maximise    Σ log p_q(m_q)
subject to  Σ marks over the paper    = grand total
            Σ marks in each section   = section total     (one equation per section)
            Σ marks on each page      = page total        (where present)
            0 ≤ m_q ≤ max_marks(q),  on the legal step lattice
```

Exact dynamic programme. If nothing clears the likelihood floor the script is **flagged, not
guessed**.

### 4.4 Resolve choice — the rule that protects the diagnosis
For each `choice_group_id`, the attempted alternative takes the mark. The other is recorded
**`NOT OFFERED`** — a third state, distinct from zero and from absent.

Scoring an unattempted alternative as zero would systematically mark every student weak in whichever
topic they *chose to avoid*, which is the exact inverse of the truth. `NOT OFFERED` rows are excluded
from every denominator and surface as coverage gaps.

### 4.5 Roll up to the diagnosis
For each student:

```
earned[skill, tier]     = Σ marks on addresses tagged (skill, tier), NOT OFFERED excluded
available[skill, tier]  = Σ max_marks on those same addresses
mastery[skill]          = G-DINA posterior over the Q-matrix (later; deterministic rates first)
```

The **sub-topic × tier cross-tab** is the diagnosis. High R&U with low AP on the *same* sub-topic is
the "knows the formula, cannot apply it" signature — and it is only detectable when the paper
actually contains both tiers for that sub-topic. When it does not, the report says so rather than
asserting a diagnosis the paper cannot support.

The evidence floor still applies: under 2 marks or 2 questions on a skill, report
`insufficient_evidence`, never a percentage.

---

## 5. Stack, by stage

| Stage | Tools |
|---|---|
| Ingest, fingerprint, render | PyMuPDF · FastAPI · S3 (`ap-south-1`) |
| Orientation, imposition, dewarp, ink separation, blobs | OpenCV · NumPy · scikit-learn (k-means) |
| Text detection / printed recognition (assist) | PaddleOCR |
| Question paper understanding, instructions, addresses | `claude-opus-5`, structured outputs, `strict: true` tools, two passes |
| Skill + tier classification | `claude-opus-5` (k=5) + pgvector retrieval + verb lexicon tables + logistic-regression fusion |
| Handwritten mark crops | `claude-haiku-4-5`; escalate disagreements to `claude-opus-5`; Batches API overnight (−50%) |
| Association | `scipy.optimize.linear_sum_assignment` |
| Reconciliation | pure-Python exact DP |
| Storage | PostgreSQL 16 (+ `pgvector`, `ltree`, RLS) · Redis + arq · S3 |
| Analysis, reports | pandas · SciPy · dbt → DuckDB · Jinja2 → WeasyPrint |
| Training corpus | `ml_corpus` schema — every prediction with its full distribution, every human label |
| Frontend | Next.js 15 · TypeScript · Dexie · OpenCV.js · next-intl (EN/TA/HI) |
| Ops | AWS `ap-south-1` · Sentry · OpenTelemetry · GitHub Actions |

---

## 6. What to build first, given eight papers

1. **English and Science** exercise every mechanism — sections, sub-parts, internal choice, all eight
   question types, the verification equations — without imposition or non-Latin script. Prove the
   pipeline there.
2. **Then Maths 30(B)**, which adds 4-up de-imposition and the bilingual parity rule, and whose
   printed section arithmetic makes verification trivial to test.
3. **Then Tamil**, which adds 2-up plus 90° rotation plus Tamil script — three new axes at once, on a
   short 12-page paper.
4. **Hindi last** — 1-up and structurally simple, but Devanagari handwriting in the answer scripts is
   the hardest recognition case, so it benefits most from arriving after the constraint solver is
   proven.

Each step adds one front-end capability to a pipeline that is already working. None of them requires
a new pipeline.
