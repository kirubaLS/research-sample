# Yaadhum Marks Engine — Pilot-Ready Design

## Zero training required on day one, with a path to a fully open-source system

---

## 1. What your three answers changed

You told me three things that materially change the design, so I want to state the consequences
before the detail.

**1. Teachers mark in red; students write in black or blue.**
This is the single most useful fact in the whole project. Colour is now a *primary, reliable
channel*, not a heuristic. It means the system can cleanly separate two things that every generic
OCR pipeline confuses: the student's own arithmetic working and the teacher's awarded mark. It also
gives us something better — the question numbers the student writes are in the *student* layer,
while the marks are in the *teacher* layer, so localisation and association become two searches over
two different images rather than one ambiguous search over one.

**2. Most schools will not upload a spreadsheet.**
So the CSV path is a convenience, not the fallback. Features 1 and 2 — the cover-page capture and
the full-script scan — carry the entire product. They must work without a safety net.

**3. You need a pilot now and have no time to train models.**
This settles the open-source-versus-paid question, and it settles it in a way that is *not* a
compromise:

> **The paid multimodal model is the pilot. The open-source model is the destination.
> The data-capture layer is the bridge between them, and it must be built on day one.**

Starting with open-source models means labelling several hundred crops by hand *before you can ship
anything*. Starting with the paid model means you ship in two weeks, and every page it processes
generates exactly the labelled data you need to train the free one. Within one term of normal use
you will have enough data to train the open recogniser, at which point you swap one component and
your marginal cost goes to zero.

That is why Section 5 — the training data store — is the most important section in this document,
even though it is not the most interesting one.

---

## 2. Layer segregation: seven layers, one replaceable

You asked how the layers are separated. The organising principle is this:

> **Exactly one layer contains a model. Every other layer is deterministic code that cannot
> hallucinate, cannot drift, and cannot be wrong in a way you did not write yourself.**

That is what makes the whole system swappable between the free plan and the paid plan by changing a
configuration value, and it is what makes the accuracy claims defensible.

| Layer | Name | What it produces | Model? | Replaceable? |
|---|---|---|---|---|
| **L0** | Capture | `PageImage` + quality metrics | No | No — browser code |
| **L1** | Restoration | `NormalizedPage` (dewarped, flattened, deskewed) | No | No |
| **L2** | Ink separation | `InkLayers {teacher, student, printed}` | No | No |
| **L3** | Localisation | `Anchor[]`, `MarkCandidate[]`, `TotalCandidate[]` | No | No |
| **L4** | **Recognition** | `Distribution` over legal values per candidate | **Yes** | **Yes — this is the swap point** |
| **L5** | Association | `Binding[]` (mark ↔ question) | No | No |
| **L6** | Reconciliation | verified `MarkFact[]` | No | No |
| **L7** | Adjudication | `GroundTruth[]` + training rows | Human | No |

Six of the seven layers are OpenCV, SciPy and plain Python. They are identical in both plans, they
run on a cheap CPU, they are unit-testable against fixed images, and their output is byte-identical
every time. Only L4 differs.

### Why this matters commercially

A competitor who wires a general-purpose vision model to "read the marks off this page" has one
layer doing all seven jobs. When it is wrong, they cannot tell you which part was wrong, they cannot
fix it without changing the prompt and re-testing everything, and they cannot ever remove the
per-page cost. Your architecture localises every failure to a named layer with its own test suite.

---

## 3. The intelligence: how the system adapts without being trained

You asked for something dynamic and intelligent rather than a fixed rule set. Here is where the
adaptation actually lives. **None of these require a training run.** They all fit parameters at
runtime from the data in front of them.

### 3.1 Per-school ink calibration — unsupervised, no labels

Do not hardcode a red hue range. On the first three pages from a new school:

1. Extract ink pixels (everything darker than a local background estimate).
2. Convert to HSV and run **k-means with k = 3** on the (hue, saturation) pairs.
3. Identify clusters by their properties, not by fixed thresholds:
   - the cluster with the highest saturation and the smallest pixel count is the **teacher's pen**
   - the largest low-saturation dark cluster is the **student's black**
   - a mid-saturation cluster in the blue hue band is the **student's blue**
4. Store the fitted centroids as a `school_ink_profile`, and re-fit automatically if the
   classification confidence on a new batch drops.

This handles a school where a teacher uses green, a faded red pen, or a page photographed under a
yellow tube light — none of which a hardcoded threshold survives. It is fitted from three unlabelled
pages in under a second.

### 3.2 Per-teacher layout convention fitting

Teachers are extremely consistent within a script and usually within a whole batch. After the first
association pass, fit the convention that the high-confidence bindings imply — the modal offset from
question anchor to mark, the modal side (left margin, right margin, above the answer), the typical
distance. Then re-solve the ambiguous bindings with that convention as a prior.

This is the step that turns coin-flips into correct answers, and it is the piece a competitor
building on a generic OCR API will not have. Details in Section 4.5.

### 3.3 Per-school threshold auto-tuning

The auto-accept confidence threshold is not a constant. It is derived from the audit sample: choose
the lowest threshold at which the measured error rate on audited cells stays under the school's
target (default 0.5%). As the recogniser improves on that school's handwriting, the threshold
automatically loosens and the teacher's review burden falls — without anyone changing a setting.

### 3.4 Template memory

The first script of a batch teaches the system the sheet format — which column is question number,
which is marks, where the total sits. Stored as a `sheet_template` and reused for every subsequent
script. First script costs the teacher thirty seconds; scripts 2 through 40 cost nothing.

### 3.5 Active learning on the review queue

The review queue is not first-in-first-out. It is ordered by *expected value of the label*:
uncertainty × downstream impact (marks at stake, board weight of the chapter, number of students
affected). A teacher with five minutes reviews the five cells that matter most, not the five that
happened to arrive first.

---

## 4. The pipeline, layer by layer

### L0 — Capture

Runs entirely in the browser, before anything is uploaded.

- Live camera preview with a quad overlay showing the detected page boundary.
- Four quality metrics computed at ~10 fps on a downscaled frame:
  - **blur** — variance of the Laplacian, normalised by frame area
  - **glare** — fraction of pixels above a luminance threshold, measured on connected blobs so a
    bright window in the corner does not fail a good page
  - **coverage** — the detected quad must fill at least 60% of the frame
  - **skew** — angle of the quad's top edge
- The shutter enables only when all four pass. This single control removes the majority of
  downstream failures at zero model cost — a bad photo caught here costs five seconds; caught later
  it costs a wrong report.
- Captured at full sensor resolution, not preview resolution.
- Two modes share this component:
  - **Feature 1** — single frame of the cover page carrying question numbers and marks
  - **Feature 2** — multi-page scan of the whole script, with per-page retake, reorder and delete,
    then an explicit Complete

### L1 — Restoration

Deterministic OpenCV. No model, no randomness.

1. **Corner detection** — adaptive threshold, morphological close, largest four-point contour via
   `findContours` + `approxPolyDP`; Hough-line fallback when the page edge is against a dark desk.
2. **Perspective correction** — homography to a fixed A4 aspect at ~300 DPI equivalent.
3. **Illumination flattening** — divide the image by a heavily Gaussian-blurred copy of itself.
   This is a cheap flat-field correction and it is remarkably effective on phone photos under the
   uneven tube lighting of an Indian staffroom.
4. **White balance** — grey-world or a white-patch estimate on the page margin. **This runs before
   any colour work** and is what makes the red separation robust across lighting.
5. **Residual deskew** — minimise the entropy of the horizontal projection profile.

### L2 — Ink separation (the layer your red-pen answer unlocked)

Produce three binary masks from one page.

```python
# after white balance in L1
hsv = cv2.cvtColor(page, cv2.COLOR_BGR2HSV)

teacher = in_hue_band(hsv, profile.teacher)   # red wraps 0/180 → two bands, plus a saturation floor
student = in_hue_band(hsv, profile.student_blue) | dark_low_saturation(hsv)
printed = high_contrast_regular_stroke(page) & ~teacher & ~student
```

Then three refinements that matter in practice:

**The printed red margin line.** Many Indian answer books have a printed red or pink margin rule.
It lands squarely in the teacher mask and destroys naive blob detection. Remove long straight
structures from the teacher mask *before* anything else: morphological opening with a long thin
kernel, plus a Hough-line pass, subtracting anything with high linearity and low curvature.

**Bleed-through.** Ink from the reverse of a thin page appears as a faint mirrored ghost. Filter by
saturation and stroke intensity; ghosts are consistently fainter than the true stroke.

**Overwrites.** A teacher correcting their own mark writes red over red. Detect stacked components
with high overlap and route them straight to human review — never guess between two candidate
values written on top of each other.

**Why this layer is worth so much:** it converts one hard problem into two easy ones. Question
numbers are searched for in the *student* mask. Marks are searched for in the *teacher* mask. The
student's own working — which is the single largest source of false positives in every generic OCR
pipeline — is simply not present in the image the mark detector looks at.

### L3 — Localisation

**Anchors (student and printed masks).** Question labels: `6`, `6.`, `Q6`, `6)`, `6(a)`. Text
detection over the mask, recognition on each candidate, then a strict regex parse.

> **Closed-vocabulary filter.** A candidate is accepted as an anchor only if the parsed label exists
> in the frozen Q-matrix for this paper. A hallucinated "Q47" on a thirty-question paper is
> discarded automatically, by construction. This is the anti-hallucination control at the
> localisation layer, and it costs nothing.

Anchors must also be monotonic — non-decreasing question order down the page and across pages.
Violations are flagged, never silently reordered; they usually mean a page is out of sequence, which
is exactly what you want to catch.

**Mark candidates (teacher mask).** Connected components filtered by area, aspect ratio and stroke
width. Additionally:
- **circled numerals** — a component enclosed by a closed contour, detected via contour hierarchy
- **excluded by shape**: ticks, crosses, strikes, underlines, marginal squiggles
- **page and section totals** — usually boxed, underlined, or at the page foot. Detect these
  *separately* and treat them as constraints rather than as question marks. Every total found is an
  extra equation for L6, and extra equations are the cheapest accuracy you will ever buy.

**Answer-block segmentation.** Using the student mask, segment the page into text blocks. The block
that begins at anchor *j* and ends before anchor *j+1* is question *j*'s answer region. This gives
L5 a far better notion of "which question is this mark next to" than raw vertical distance.

### L4 — Recognition (the only model in the system)

One narrow interface, two implementations:

```python
class MarkRecognizer(Protocol):
    def predict(self, crop: Image, legal_values: list[Decimal]) -> dict[Decimal, float]:
        """Probability distribution over the legal values for exactly this question."""
```

The `legal_values` argument is doing enormous work. For a three-mark question the model may only
return a value from `[0, 0.5, 1, 1.5, 2, 2.5, 3, "A"]`. It is structurally incapable of returning 8.
Restricting the output alphabet per cell is the largest accuracy gain available anywhere in this
pipeline, and it is free in both plans.

### L5 — Association

A constrained assignment problem, solved exactly rather than with if-else rules.

Cost of binding mark candidate *i* to anchor *j*:

```
C[i][j] =  w1 · vertical_distance(i, j)
         + w2 · (0 if i falls inside question j's answer block else PENALTY)
         + w3 · side_inconsistency(i, fitted_convention)
         + w4 · page_mismatch(i, j)
         − w5 · log p_legal(value_i | max_marks(q_j))
```

Solved with the Hungarian algorithm (`scipy.optimize.linear_sum_assignment`) under the constraints
that each question takes at most one mark and each mark is used at most once. Exact, optimal, and
about a millisecond for a 30 × 40 matrix.

**Then the second pass.** Take the bindings whose cost margin over the runner-up is large; fit the
teacher's convention from them (modal offset vector, modal side, distance distribution); rebuild the
cost matrix with that convention as a prior; solve again. The ambiguous bindings are now decided by
the teacher's own habit rather than by a tie-break.

### L6 — Reconciliation

Every constraint available, applied at once:

```
maximise    Σ log p_q(m_q)

subject to  Σ_{q ∈ paper}   m_q = grand_total          (if present)
            Σ_{q ∈ section} m_q = section_total        (for each section found)
            Σ_{q ∈ page}    m_q = page_total           (for each page total found)
            0 ≤ m_q ≤ max_marks(q)
            m_q on the legal step lattice
```

Solved as an exact dynamic programme over the mark lattice. If no assignment reaches the likelihood
floor, **the script is flagged, not guessed** — a missing page, an unmarked question or a teacher's
own addition error all surface here rather than silently corrupting a report.

This layer is why the system-level accuracy is far higher than the recogniser's accuracy. A
recogniser that is 92% correct per digit, wrapped in these constraints, produces scripts that are
correct or flagged — almost never silently wrong.

### L7 — Adjudication

Everything L6 could not verify goes to a review queue showing the **crop next to the proposed
value**. One tap to confirm, one to correct. Ordered by expected value of the label, not arrival
time. Every action here writes a training row — see the next section.

---

## 5. The training data store — build this on day one

This is the section that makes "I will train later" actually possible. Most teams intend to collect
training data, store only the final answer, and discover a year later that they have nothing usable.

### 5.1 Separation from the operational database

`ml_corpus` is a **separate schema with separate credentials**, and ideally a separate database
instance. The operational system may read from it; the training pipeline may never write to
operational tables. This separation is what lets you hand a dataset to a contractor, run experiments
freely, and satisfy a school's data questions without touching live marks.

### 5.2 Schema

```sql
-- the raw evidence
create table ml_corpus.capture_asset (
  asset_id      uuid primary key,
  school_id     uuid not null,
  assessment_id uuid,
  student_ref   uuid,              -- pseudonymous; never a name
  page_index    int,
  storage_uri   text not null,     -- encrypted object store
  sha256        text not null,
  captured_at   timestamptz,
  device_hint   text,              -- model of phone, for stratifying the eval set
  quality       jsonb,             -- blur, glare, coverage, skew
  ink_profile   jsonb,             -- the fitted per-school hue centroids
  consent_class text not null,     -- 'operational_only' | 'training_permitted'
  retention_until date
);

-- every region the system looked at
create table ml_corpus.crop (
  crop_id     uuid primary key,
  asset_id    uuid references ml_corpus.capture_asset,
  kind        text not null,       -- 'mark' | 'anchor' | 'cell' | 'total'
  layer       text not null,       -- 'teacher' | 'student' | 'printed'
  bbox        int[] not null,
  preproc_ver text not null,       -- so a crop can be regenerated identically
  storage_uri text                 -- the crop image itself
);

-- every prediction, including the ones that were auto-accepted
create table ml_corpus.prediction (
  prediction_id uuid primary key,
  crop_id       uuid references ml_corpus.crop,
  backend       text not null,     -- 'claude-haiku', 'claude-opus', 'trocr-ft-v3', ...
  model_version text not null,
  distribution  jsonb not null,    -- THE FULL DISTRIBUTION, not just the argmax
  argmax        text,
  confidence    numeric,
  calibrated    numeric,
  latency_ms    int,
  cost_micros   int,
  created_at    timestamptz default now()
);

-- every human judgement
create table ml_corpus.human_label (
  label_id     uuid primary key,
  crop_id      uuid references ml_corpus.crop,
  value        text not null,
  labeler_id   uuid not null,
  mode         text not null,      -- 'review' | 'audit' | 'adjudication'
  time_taken_ms int,               -- slow labels mark genuinely hard crops
  created_at   timestamptz default now()
);

-- disagreements are the highest-value rows in the whole corpus
create table ml_corpus.disagreement (
  crop_id   uuid,
  source_a  text, value_a text,
  source_b  text, value_b text,
  resolved  text,
  resolved_by uuid
);

-- reproducible datasets
create table ml_corpus.dataset_snapshot (
  dataset_id uuid primary key, name text, filter_spec jsonb,
  row_count int, content_hash text, created_at timestamptz
);
create table ml_corpus.dataset_member (dataset_id uuid, crop_id uuid, split text);

create table ml_corpus.eval_run (
  run_id uuid primary key, dataset_id uuid, backend text, model_version text,
  metrics jsonb, created_at timestamptz
);
```

### 5.3 The five rules that make this corpus valuable

1. **Store every prediction, including auto-accepted ones.** This is the rule everybody breaks. If
   you only store the crops a human touched, your training set is composed entirely of hard cases,
   your model learns a skewed distribution, and you can never measure accuracy on easy ones.
2. **Store the full distribution, not the argmax.** Calibration, conformal thresholds and
   distillation to a smaller model all need the distribution. You cannot recover it later.
3. **Append-only. Never delete a label.** Corrections are new rows. A labeller who changes their
   mind is signal.
4. **Record time-taken on every human label.** A crop that took a teacher eight seconds is worth
   more in a training set than one that took one second, and it is a free difficulty annotation.
5. **Separate consent from operation.** A school that has not consented to training use still gets
   full product function; its assets simply carry `consent_class = 'operational_only'` and are
   filtered out of every `dataset_snapshot`. Build this flag now — retrofitting consent is not
   possible.

### 5.4 What you will actually accumulate

| Unit | Mark crops |
|---|---|
| One class, one assessment (40 students × 30 questions) | 1,200 |
| One class, one term (2 assessments) | 2,400 |
| Ten classes, one term | 24,000 |
| One school, one academic year | ~50,000 |

**A fine-tuned handwritten-digit recogniser on a restricted alphabet needs on the order of 2,000 to
5,000 labelled crops to become strong.** You cross that threshold inside the first term of a single
school. That is the concrete basis for the migration plan in Section 8 — it is not aspirational.

### 5.5 Privacy posture

- Mark crops contain a digit and nothing else — no name, no handwriting of substance, no PII. These
  are what leave for training.
- Full page images contain the student's work and stay under restricted access with a retention
  clock. They are never part of an exported training set.
- Student identity in `ml_corpus` is a pseudonymous UUID; the mapping lives in the operational
  database under separate credentials.
- Everything is stored in `ap-south-1`.

---

## 6. Plan A — Open source, and where its accuracy honestly sits

### 6.1 Components

| Job | Component | Licence (verify at adoption) |
|---|---|---|
| L0–L3, L5, L6 (six of seven layers) | **OpenCV + SciPy + NumPy** | Apache-2.0 / BSD |
| Text detection | **PaddleOCR** (PP-OCR detection) or CRAFT | Apache-2.0 |
| Printed recognition | **PaddleOCR** recognition | Apache-2.0 |
| Handwritten digits | **TrOCR-small handwritten**, fine-tuned, or a small CRNN you train | MIT |
| Table structure (unruled fallback) | **Table Transformer** | MIT |
| Whole-page fallback | **Qwen2.5-VL 7B** or **GOT-OCR 2.0** | Apache-2.0 |
| QR decode | **pyzbar** | LGPL |
| Serving | **ONNX Runtime** (CPU), vLLM if a VLM is used | MIT / Apache-2.0 |

### 6.2 Honest accuracy expectation

These are expectations to validate against your own gold set, not measured benchmarks:

| Configuration | Per-digit accuracy | System outcome |
|---|---|---|
| Off-the-shelf handwriting model, no fine-tuning, no constraints | Modest — this is the configuration that disappoints people | Unusable alone |
| Off-the-shelf **+ restricted alphabet + colour separation** | Substantially better | Usable with heavy review |
| **+ constraint solver with totals** | Per-digit accuracy stops being the binding constraint | Correct or flagged |
| **Fine-tuned on 2–5k of your own crops + all of the above** | Strong | Low review rate, zero marginal cost |

**The key intellectual point, and it is true of both plans:** system accuracy is much higher than
component accuracy, because the constraints are doing most of the work. A recogniser that is wrong
one time in twelve, wrapped in a colour-separated, alphabet-restricted, arithmetically-reconciled
pipeline, produces scripts that are either right or flagged. This is why the open-source plan is
genuinely viable for *marks* — a tiny restricted alphabet with hard arithmetic checks around it.

### 6.3 Where open source is not yet good enough

**Reading the question paper.** Extracting question text, marks, section structure, internal choice
and diagram references from a printed paper is a document-understanding task with no arithmetic
oracle and no restricted alphabet. Open models are furthest behind here, and getting it wrong
poisons every downstream report. Do not build this on open models to save ₹50 per paper.

### 6.4 Cost

- Marginal cost per script: **zero**.
- Infrastructure: CPU-only for the classical stack — a four-core VM handles a class of forty in a
  few minutes. Add a GPU (~16–24 GB) only if you adopt a VLM fallback.
- Engineering: **2–3 weeks** of additional work for labelling, fine-tuning and calibration, which is
  precisely the time you do not have right now.

---

## 7. Plan B — Paid multimodal, and where its accuracy sits

### 7.1 Model assignment by stakes

| Stage | Model | Frequency | Rationale |
|---|---|---|---|
| Question paper extraction + classification | `claude-opus-5` | Once per paper | Highest stakes, no arithmetic oracle, amortised across forty students |
| Cover-page marks table (Feature 1) | `claude-opus-5` | Once per student | One frame, high value, cheap at this volume |
| Per-crop mark digits (Feature 2) | `claude-haiku-4-5` | ~30 per student | High volume, tiny crops, restricted alphabet |
| Adjudication on disagreement | `claude-opus-5` | Rare | Only where the cheap model and the classical engine disagree |
| Overnight processing | Message Batches API | All scripts | Not latency-sensitive — 50% cost reduction |

### 7.2 Controls that make it trustworthy

- **Structured outputs with `strict: true` tools**, and foreign-key validation on every returned ID.
  The model cannot invent a chapter or a sub-topic that does not exist in your database.
- **Enum-restricted values** — the schema for a mark cell lists exactly the legal values for that
  question.
- **The model never computes a sum.** Every total is calculated in Python from extracted parts.
- **Two independent passes** on the question paper with a field-level diff; disagreement routes to
  review.
- **Provenance** — every value carries the crop it came from, so a human check takes one second.

### 7.3 Accuracy expectation

Strong out of the box on this task class, with **zero training and zero labelled data**, which is
exactly the constraint you are under. Wrapped in the same L2/L3/L5/L6 machinery as the open plan, it
should reach a high auto-accept rate from the first real class — and critically, whatever it does
not reach is *flagged*, not silently wrong.

### 7.4 Cost

Order-of-magnitude, from published per-token rates, for a class of forty with a thirty-question
paper:

| Item | Estimate |
|---|---|
| Question paper: two passes + classification | ₹40–50, once per paper |
| Cover pages: forty students | ₹40–80 |
| Mark crops: ~1,200 small images on Haiku | ₹30–60 |
| Batch API discount | −50% on the batched portion |
| **Per class, per assessment** | **≈ ₹150–350** |

Twenty classes, two assessments a term: a few thousand rupees per term. Negligible against a
per-school licence, and far cheaper than three weeks of engineering time you would spend to avoid it.

---

## 8. The migration ladder — how you get from Plan B to Plan A

This is the plan, not a hope:

1. **Weeks 0–2.** Ship with `ClaudeRecognizer`. Every prediction and every human correction is
   written to `ml_corpus`. The pilot runs.
2. **Weeks 2–12 (first term).** Normal operation accumulates 20,000–50,000 crops with labels from
   auto-acceptance, teacher review and the audit sample.
3. **End of term one.** Build a `dataset_snapshot` from consented schools. Fine-tune TrOCR-small or
   a CRNN on it. This is a day of work because the data is already clean, labelled and versioned.
4. **Shadow mode.** Run the open recogniser alongside the paid one on live traffic. Log every
   disagreement. Nothing changes for users.
5. **Promotion by evidence.** When the open backend matches or beats the paid one on the gold set at
   the same auto-accept rate, flip the configuration value. Marginal cost goes to zero.
6. **Keep the paid model as the adjudicator.** Even after migration, route the rare hard
   disagreements to `claude-opus-5`. You get open-source economics with paid-model accuracy on the
   cases that matter — which is the best of both and costs almost nothing, because it is rare.

**Keep the paid model permanently for the question paper.** It runs once per paper, and it is the
one place where open models are not close.

---

## 9. The step-by-step runbook

What actually happens, end to end, on a real assessment day.

**Before the assessment**

1. Admin creates the assessment and uploads or photographs the question paper.
2. The system extracts questions, marks and structure; gates G1 (marks reconcile to the printed
   total, respecting internal choice), G2 (question sequence complete) and G3 (two passes agree) run.
3. The system classifies each question into chapter, sub-topic and R&U / AP / AEC, abstaining where
   uncertain.
4. A teacher confirms on one screen — roughly five minutes, showing each question's crop beside its
   proposed classification. The **Q-matrix is frozen and versioned**.
5. QR stickers for the class are printed — one sheet, thirty seconds.

**After marking**

6. Teacher opens the scanner, scans the QR sticker on a student's cover page. The student is bound
   from the roster; no name is typed.
7. **Feature 1**: capture the cover page carrying question numbers and marks. Quality gate must pass.
8. **Feature 2**: capture every page. Each page is quality-scored on the spot; amber pages can be
   retaken individually without disturbing the sequence. Pages are held in the browser only.
9. Teacher presses **Complete**. Pages upload with per-page retry; the server assembles a lossless
   PDF, stores the originals as well, and the script appears in the dashboard against that student
   immediately.
10. Extraction is queued — overnight in batch, or immediately if the teacher is waiting.
11. L1 restores, L2 separates the red teacher layer from the black/blue student layer, L3 finds
    question anchors in the student layer and mark candidates plus totals in the teacher layer.
12. L4 returns a probability distribution over legal values for each mark crop.
13. L5 binds marks to questions with the Hungarian solver, then re-solves using the fitted convention.
14. L6 reconciles against page, section and grand totals. Consistent scripts pass; inconsistent ones
    are flagged with the specific constraint that failed.
15. Anything below the auto-accept threshold appears in the review queue, ordered by importance, with
    the crop shown. One tap to confirm, one to correct.
16. Every prediction, correction and disagreement is written to `ml_corpus`.

**Reporting**

17. Verified marks map through the frozen Q-matrix to chapter, sub-topic and tier.
18. Loss analysis runs with denominators, the evidence floor and credible intervals.
19. Board-weighted indicators and the paper-quality report are computed.
20. The principal's dashboard shows the student report, the class patterns and — importantly — the
    current measured extraction accuracy from the audit sample.

---

## 10. Sprint plan for an immediate pilot

Because no training is required, the schedule compresses considerably.

| Sprint | Days | Delivers |
|---|---|---|
| **S1** | 5 | L0 capture with quality gate; Features 1 and 2 UX including per-page retake, reorder and Complete; IndexedDB staging; resumable upload; PDF assembly; QR binding; dashboard display. `ml_corpus` schema created and writing from the first captured page. |
| **S2** | 5 | L1 restoration; L2 ink separation with unsupervised per-school calibration and red-margin-line removal; L3 localisation with closed-vocabulary anchors, mark candidates and total detection. |
| **S3** | 5 | L4 with the paid backend behind the `MarkRecognizer` interface; L5 Hungarian association plus convention fitting; L6 constraint solver with all three total types; calibration; review queue with crops; the gold set and benchmark harness. |
| **S4** | 5 | Question paper ingest with gates G1–G3, classification, teacher confirmation, frozen Q-matrix. Mapping to chapter/sub-topic/tier; the principal's report. |
| **S5** | 5 | Audit sample and the accuracy dashboard; threshold auto-tuning; consent and retention; row-level security; load testing; handover. |

**First real class through the system: end of Sprint 3, roughly three weeks.** The question paper
path in S4 can be run manually for the first paper if you want a class scanned even sooner.

---

## 11. What I still need

1. **Five answer scripts photographed page by page on a teacher's own phone**, in the room where
   scanning will happen. Not flatbed scans — they look nothing like production. This is the input
   that calibrates the association cost weights in L5 and the ink profile in L2, and it is the one
   thing I genuinely cannot proceed optimally without.
2. **Is a total written anywhere on the script** — grand total, per-section totals, per-page totals,
   or none? Each one is an independent equation in L6 and materially changes accuracy. If none
   exists, I will send you a one-page marks strip to print that creates one.
3. **Your logo files** — still outstanding from the earlier plan, and they block the first screen.
4. **Confirmation on training consent wording** for the school agreement, so `consent_class` is set
   correctly from the very first page captured rather than retrofitted.
