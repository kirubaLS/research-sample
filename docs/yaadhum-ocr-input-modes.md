# Use Case 2 — Expanded Input Modes and Two Implementation Plans

**Scope.** This document extends the marks engine with the three input modes you described,
specifies the algorithm for locating a mark anywhere on a page and binding it to the right
question, and then gives two complete implementation plans — one entirely open-source and free to
run, one using commercial multimodal models — with a recommendation on how to choose between them
using your own data rather than anyone's claims.

**On "100% accuracy", once and then I'll stop repeating it.** No pipeline containing a recogniser
is literally 100%. What this design delivers instead is stronger than a claim: *every mark that
reaches a report is either arithmetically verified against a number the teacher wrote, or was
confirmed by a human*. Errors are structurally prevented from reaching a report, and the residual
rate is measured and published rather than asserted.

---

## Part 0 — The architectural spine: three modes, one contract

The most important decision in this whole extension is to stop thinking of the three modes as three
features. They are three **adapters** onto one canonical fact:

```python
MarkFact = {
  "student_id":   UUID,
  "question_id":  UUID,          # resolved against the frozen Q-matrix, never free text
  "marks":        Decimal,       # 0 <= marks <= max_marks(question)
  "source":       Literal["csv", "cover_ocr", "page_ocr", "teacher"],
  "confidence":   float,         # 1.0 for csv and teacher
  "provenance":   {              # what a human would need to check this in one second
     "page_id":   UUID | None,
     "bbox":      [x1, y1, x2, y2] | None,
     "crop_uri":  str | None,
     "row_ref":   str | None     # e.g. "sheet1!C14" for CSV
  }
}
```

Everything downstream — validation, the constraint solver, chapter/sub-topic/tier mapping, the
report — consumes `MarkFact` and nothing else. The three modes never touch analysis code.

**Precedence when modes disagree**, resolved at projection time, never by overwriting:

```
teacher (manual correction)  >  csv  >  cover_ocr  >  page_ocr
```

Disagreement between two sources is not an error to suppress — it is a **free accuracy signal**.
If a CSV says 3 and the page OCR says 1, that pair goes to review, and it is also a labelled
training example. Log every disagreement.

**Practical consequence worth stating plainly:** Mode C (CSV) is the most accurate mode you will
ever have. Design the product so OCR *accelerates* mark entry rather than replacing it, and so a
school that already keeps marks in Excel gets full value on day one with zero OCR risk.

---

## Part 1 — Mode A: cover-page capture (question numbers + marks table)

A single frame containing a tabulated list of question numbers and marks. This is a **table
structure recognition** problem, not an OCR problem, and treating it as the latter is the usual
mistake.

### A.1 Capture

1. Live camera view with a rectangle guide overlay and real-time corner detection.
2. **Quality gate before the shutter is even usable** — computed at ~10 fps in the browser:
   - blur: variance of the Laplacian, normalised by image size
   - glare: fraction of pixels above a luminance threshold in a connected blob
   - coverage: the detected quad must occupy ≥ 60% of the frame
   - skew: angle of the detected quad's top edge
   The shutter button turns green only when all four pass. This one control removes the majority of
   downstream failures at zero model cost.
3. Capture at the highest available resolution, not the preview resolution.

### A.2 Geometric normalisation

1. Corner detection: adaptive threshold → morphological close → largest 4-point contour
   (`cv2.findContours` + `cv2.approxPolyDP`). Fall back to a line-based Hough estimate.
2. Perspective correction via homography (`cv2.getPerspectiveTransform` + `warpPerspective`) to a
   fixed A4 aspect at ~300 DPI equivalent.
3. Illumination correction: divide by a heavily blurred copy of the image (a cheap, very effective
   flat-field correction for phone photos under tube lights).
4. Deskew residual rotation by minimising horizontal projection-profile entropy.

### A.3 Table structure — use morphology, not a model

For a **ruled** grid this is the highest-accuracy, zero-hallucination approach and it is fully
deterministic:

```
binary  = adaptiveThreshold(gray)
h_lines = morphologyEx(binary, MORPH_OPEN, kernel=(width//30, 1))
v_lines = morphologyEx(binary, MORPH_OPEN, kernel=(1, height//30))
grid    = h_lines & v_lines          # intersections = cell corners
cells   = connected_components(h_lines | v_lines)
```

You get an exact cell lattice with no neural network involved. Only when line detection fails
(unruled or hand-drawn tables) do you escalate to a learned table-structure model — Table
Transformer (`microsoft/table-transformer-structure-recognition`) or PaddleOCR's PP-Structure table
module. Escalation, not default.

### A.4 Column semantics

Which column is "Q.No" and which is "Marks"?

1. Header text recognition on the top row; fuzzy-match against a synonym list
   (`Q.No | Question | Qn | வினா எண்`, `Marks | Mark | Score | மதிப்பெண்`).
2. If headers are absent or unreadable, fall back to content typing: a column whose values form a
   near-complete run 1..N is the question column; a column whose values are all ≤ the corresponding
   `max_marks` is the marks column.
3. **Confirm once per template, not per script.** The first script of a batch shows a one-screen
   confirmation; the mapping is stored as a `sheet_template` and reused for every subsequent script
   in that batch. This is the difference between 5 seconds and 5 minutes of teacher time per class.

### A.5 Cell recognition with a restricted alphabet

For each marks cell, the recogniser must return **a probability distribution over the legal values
for that question**, not a string:

```python
legal_values(q) = [0, 0.5, 1, 1.5, ..., max_marks(q)]   # step from the marking scheme
                + ["A"]                                  # absent
```

Restricting the output alphabet per cell is the single largest accuracy gain available in the whole
pipeline, and it costs nothing. A model that cannot output "8" for a 3-mark question cannot make
that error.

### A.6 Validation

- `Σ marks == printed total` (the constraint solver from the main design runs here too)
- every question number in the table exists in the frozen Q-matrix
- no duplicate question numbers
- the run of question numbers is complete

---

## Part 2 — Mode B: full-script scan

Everything in Mode A, plus page management, plus the hard part: **finding a mark that could be
anywhere and knowing which question it belongs to.**

### B.1 Page capture, temporary storage and PDF assembly

**Client-side (nothing hits the server until "Complete"):**

| Step | Mechanism |
|---|---|
| Capture page *n* | Same quality gate as A.1; store the full-resolution JPEG blob |
| Temporary store | IndexedDB via Dexie, keyed `(scan_session_id, page_index)`, with a separate thumbnail store so the strip renders instantly |
| Preview strip | Horizontal thumbnail rail; amber badge on any page below the quality threshold |
| **Retake page *n*** | Re-shoots that page only and **keeps its index** — the sequence is never disturbed |
| Reorder / delete | Drag to reorder, swipe to delete, with an undo toast |
| Page counter | "12 of ~15" with the expected count taken from the assessment config, as a soft check |
| **Complete** | Explicit button; blocks if any page is below a hard quality floor, warns if merely amber |

Storage discipline: blobs live in IndexedDB only until upload succeeds, then are evicted. A scan
session older than 24 hours is purged automatically — you do not want a term's worth of children's
answer scripts sitting in a browser database on a shared staffroom laptop.

**Server-side, after "Complete":**

1. Resumable chunked upload per page (tus protocol or plain multipart with a per-page idempotency
   key). Retries are per page, so a dropped connection at page 14 does not lose pages 1–13.
2. Store **both**: the original page images *and* an assembled PDF. The PDF is for humans; the
   images are what the crops, provenance links and any re-processing need. Do not store only the PDF.
   - Assembly: `img2pdf` (lossless — it embeds the original JPEG bytes rather than re-encoding),
     then `pikepdf` to attach metadata (student, assessment, scan session, page hashes).
3. Bind to the student — QR sticker decode (`pyzbar`) if present, otherwise the roll number entered
   at the start of the session, checked against the roster.
4. Return a viewer URL; the dashboard shows the PDF alongside that student's record immediately,
   before any extraction has run.

### B.2 The mark-localisation problem, stated properly

You are right that the mark's position is not fixed: left margin, right margin, above the answer,
inside the margin, next to the question number, or circled in the body. **Do not try to solve this
with a fixed region-of-interest.** The reliable approach is anchor-first association.

#### Step 1 — Separate the teacher's ink from the student's

Teachers mark in red or another contrasting pen. This is an enormous, nearly free signal:

```python
hsv  = cv2.cvtColor(page, cv2.COLOR_BGR2HSV)
red  = cv2.inRange(hsv, (0,70,50), (10,255,255)) | cv2.inRange(hsv, (170,70,50), (180,255,255))
```

Everything that follows runs on the red channel mask. This removes almost all false positives from
the student's own arithmetic working, which is otherwise the dominant error source. Calibrate the
hue range per school once (green and blue pens exist); if the marking pen is the same colour as the
student's, fall back to stroke-width and glyph-size heuristics and expect a lower auto-accept rate —
and tell the school that a red pen materially improves their results.

#### Step 2 — Find question-number anchors

Anchors are the printed or handwritten question labels: `6`, `6.`, `Q6`, `6)`, `6(a)`.

1. Text detection over the full page — DBNet or CRAFT (open plan) / the VLM's own layout output
   (commercial plan) — producing candidate boxes.
2. Recognition on each candidate, then parse with a strict regex.
3. **Closed-vocabulary filter:** a candidate is accepted as an anchor only if the parsed label
   exists in the frozen Q-matrix for this paper. A hallucinated "Q47" on a 30-question paper is
   discarded automatically. This is the anti-hallucination mechanism at the localisation layer.
4. Enforce monotonicity: anchors should appear in non-decreasing question order down the page and
   across pages. Violations are flagged, not silently reordered — they usually mean a page is out of
   sequence, which is exactly what you want to catch.

#### Step 3 — Find mark candidates

On the red mask, detect small isolated numeral-like components:
- connected components filtered by area, aspect ratio and stroke width
- circled numerals (Hough circle or contour-hierarchy detection — a numeral inside a closed contour)
- exclude tick and cross glyphs by shape (they are marking artefacts, not values)
- exclude long horizontal strikes and underlines

#### Step 4 — Associate marks to questions (the core algorithm)

This is a **constrained assignment problem**, and it should be solved as one rather than with
if-else rules.

Build a cost matrix `C[i][j]` = cost of assigning mark candidate *i* to anchor *j*:

```
C[i][j] =  w1 · vertical_distance(i, j)
         + w2 · (0 if mark i lies in the vertical band [anchor j, anchor j+1] else PENALTY)
         + w3 · horizontal_side_mismatch(i, j)      # left vs right margin consistency
         + w4 · page_mismatch(i, j)                 # same page strongly preferred
         − w5 · log p_legal(value_i | max_marks(q_j))   # a 7 next to a 3-mark question is unlikely
```

Solve with the Hungarian algorithm (`scipy.optimize.linear_sum_assignment`) under the constraints
that each question receives at most one mark and each mark is used at most once. This is optimal,
exact, and runs in milliseconds for a 30×40 matrix.

#### Step 5 — Learn this teacher's convention, then re-solve

The step that lifts accuracy from "good" to "reliable":

1. Take the high-confidence assignments from step 4 (large cost margin over the runner-up).
2. Fit the layout convention they imply — the modal offset vector from anchor to mark, the modal
   side (left/right), the modal distance distribution. A teacher is highly consistent *within* a
   script and usually within a batch.
3. Re-weight the cost matrix with the fitted convention as a prior and solve again.
4. Ambiguous assignments that were coin-flips in pass 1 are now resolved by the teacher's own habit.

This is a two-pass robust fit — cheap, deterministic, and it exploits the strongest regularity in
the data. It is the piece a competitor building on a generic OCR API will not have.

#### Step 6 — Constraint solving and routing

Feed the per-question distributions into the arithmetic solver from the main design:

```
maximise  Σ log p_q(m_q)
subject to  Σ m_q = T (the cover or section total)
            0 ≤ m_q ≤ max_marks(q)
```

Then route by calibrated confidence: auto-accept above threshold, everything else into the review
queue with the crop displayed. If no assignment reaches the likelihood floor, the script is flagged
rather than guessed — a missing page, an unmarked question or a mis-added total all surface here.

### B.3 Section totals as extra constraints

Most CBSE-format papers are divided into sections with their own totals. Every section total is an
**additional independent equation**. Extract them and add them as constraints — the solver becomes
dramatically better conditioned, because a wrong digit now has to be consistent with both its
section total and the grand total. Extracting section totals is a small amount of work for a large
accuracy return.

---

## Part 3 — Mode C: CSV / Excel upload

The mode most likely to be used daily, and the one that should be flawless.

### C.1 Accepted shapes

Auto-detect between the two layouts teachers actually produce:

- **Wide**: one row per student, one column per question (`RollNo, Q1, Q2, ... Q30, Total`)
- **Long**: one row per mark (`RollNo, QuestionNo, Marks`)

Detection heuristic: if ≥ 60% of column headers parse as question labels present in the Q-matrix,
it is wide; otherwise look for a header triple matching the long shape.

### C.2 Import pipeline

1. **Parse** — `pandas.read_csv` / `openpyxl` for `.xlsx`. Handle the realities: BOM, `;` and `\t`
   delimiters, merged header cells, a title row above the real header, trailing blank rows, Tamil
   column names.
2. **Column mapping screen** — fuzzy-matched proposals the user can override, remembered as a
   `sheet_template` for the next upload.
3. **Normalise cells** — strip whitespace, convert `3/5` to `3`, treat `AB`/`A`/`-` as absent,
   `0` as a genuine zero. **Blank is not zero** and must be resolved explicitly.
4. **Dry run** — a diff preview: *N rows will be created, M will change an existing mark, K rows
   have errors.* Nothing is written yet.
5. **Validate** — every roll number matches the roster; every question exists in the Q-matrix; every
   value is within range and on a legal step; per-student sum equals the stated total if a total
   column is present.
6. **Commit** — one transaction, tagged with an `import_batch_id`, written as append-only
   `mark_event` rows with `source="csv"` and `confidence=1.0`. Re-uploading the same file is a
   no-op; re-uploading a corrected file creates new events and the projection picks them up.
7. **Undo** — one button that reverses an entire `import_batch_id`. Teachers will upload the wrong
   file at least once.

### C.3 Give them the template

Ship a downloadable `.xlsx` pre-filled with the roster and the question columns for this
assessment, with data validation on each cell (range, step, dropdown for absent). Most import errors
disappear when the file originates from your template.

---

## Part 4 — Plan 1: fully open-source, zero marginal cost

Everything self-hosted. No per-page fee, no student data leaving your infrastructure.

### 4.1 Component choices

| Job | Component | Notes |
|---|---|---|
| Geometry, dewarp, illumination | **OpenCV** | Classical, deterministic. Used identically in both plans. |
| Ruled table structure | **OpenCV morphology** | Exact cell lattice, no model. Used identically in both plans. |
| Unruled table structure | **Table Transformer** (`microsoft/table-transformer-structure-recognition`) | Escalation path only |
| Text detection | **PaddleOCR** (PP-OCR detection) or **CRAFT** | Mature, CPU-capable, strong on mixed scripts |
| Printed text recognition | **PaddleOCR** recognition | Question numbers, headers, printed papers |
| Handwritten digit / short-string recognition | **TrOCR handwritten** (`microsoft/trocr-base-handwritten`), or a small CRNN you train | The component that needs your data |
| Page layout | **DocLayout-YOLO** or **PP-Structure** | Optional; the anchor-first method reduces the need |
| Open multimodal fallback | **Qwen2.5-VL 7B** or **GOT-OCR 2.0** | For whole-page reads when the classical path abstains |
| Barcode / QR | **pyzbar** (ZBar) | Student binding |
| Serving | **ONNX Runtime** (CPU) and **vLLM** (if running a VLM) | ONNX for the small models is fast enough on CPU |

> **Verify licences at adoption time.** These are permissively licensed as of writing (Apache-2.0
> for PaddleOCR and Qwen2.5-VL, MIT for the Microsoft models), but licence terms change and you are
> commercialising — have this checked before the code depends on it.

### 4.2 Hardware

- The classical path (OpenCV + PaddleOCR + TrOCR-small under ONNX) runs acceptably on **CPU only**.
  A 4-core cloud VM handles a class of 40 scripts in a few minutes.
- Adding Qwen2.5-VL 7B needs one GPU with ~16–24 GB. Either a bought box (roughly ₹1.5–2.5 lakh for
  a workstation with a 24 GB card) or a rented instance at roughly ₹15,000–30,000 per month.
- Start CPU-only. Add the GPU only if the benchmark in Part 6 says the classical path is not enough.

### 4.3 The work this plan actually requires

This is the honest cost of "free":

1. **Collect and label ~500 mark crops** from real scripts at this school. Two days of work,
   and it is unavoidable — Indian handwritten digits under phone-camera conditions are not what any
   public checkpoint was trained on.
2. **Fine-tune the recogniser** on those crops (TrOCR-small or a CRNN). One day, CPU-feasible for a
   small model, a few hours on a rented GPU.
3. **Calibrate** — temperature scaling on a held-out split so the confidences mean something.
4. **Ensemble for redundancy.** In the commercial plan, redundancy comes from two LLM passes. Here
   it comes from running **two structurally different engines** (PaddleOCR recognition and the
   fine-tuned TrOCR) and routing disagreement to review. Two different architectures making the same
   mistake is much rarer than one model being confidently wrong twice.
5. **Retrain quarterly** as corrections accumulate.

**Add roughly 2–3 weeks to the schedule** for items 1–4, and expect to re-do item 1 when you onboard
a school with different handwriting.

### 4.4 Where this plan is genuinely better

- Zero marginal cost per script — decisive at 100 schools.
- No student handwriting ever leaves your infrastructure. This is the strongest possible answer to a
  DPDP Act question, and some schools will choose you for it alone.
- No vendor dependency, no rate limits, no pricing changes.
- Latency is predictable and offline operation is possible.

### 4.5 Where it is weaker

- Lower accuracy on messy handwriting until you have collected enough school-specific data.
- It cannot read the *question paper* well. Extracting question text, marks and structure from a
  printed paper with diagrams and internal choice is genuinely hard for classical OCR, and this is
  where open models are furthest behind. See the recommendation in Part 6.

---

## Part 5 — Plan 2: commercial multimodal

### 5.1 Model assignment by stakes

| Stage | Model | Frequency | Why |
|---|---|---|---|
| Question paper extraction + classification | `claude-opus-5` | Once per paper | Highest stakes, amortised over 40 students. Structured outputs (`output_config`), tools with `strict: true`, two independent passes with a field-level diff. |
| Cover-page marks table | `claude-opus-5` | Once per student | One frame, high value, cheap at this volume |
| Per-crop mark digits | `claude-haiku-4-5` | ~30 per student | High volume, tiny images, restricted output alphabet |
| Adjudication on disagreement | `claude-opus-5` | Rare | Only where the cheap model and the classical engine disagree |
| Overnight processing | Message Batches API | All scripts | Answer scripts are not latency-sensitive — 50% cost reduction |

The cascade is the point: pay the expensive model only where a mistake is expensive and the volume
is low.

### 5.2 Anti-hallucination controls specific to this plan

- **Structured outputs plus foreign-key validation** — the model returns taxonomy IDs, and any ID
  that does not exist in the database is rejected before it is stored. It cannot invent a chapter.
- **Restricted value sets** — for a mark cell, the schema's enum is the legal values for that
  question. The model cannot return 8 for a 3-mark question.
- **Never ask for a sum.** Every total is computed in Python from the extracted parts.
- **Two-pass consensus** with a field-level diff; disagreement routes to review.
- **Provenance** — every value carries the crop it came from, so a human check costs one second.

### 5.3 Cost

Order-of-magnitude, from published per-token rates, for a class of 40 with a 30-question paper:

| Item | Estimate |
|---|---|
| Question paper: 2 passes + classification | ₹40–50, once per paper |
| Cover pages: 40 students | ₹40–80 |
| Mark crops: ~1,200 small images on Haiku | ₹30–60 |
| Batch API discount | −50% on the batched portion |
| **Total per class per assessment** | **≈ ₹150–350** |

At two assessments per term across 20 classes that is a few thousand rupees a term — negligible
against a per-school licence, and decisively cheaper than the engineering time Plan 1 requires
until you are at real scale.

### 5.4 Where it is weaker

- Per-script marginal cost that scales with your success.
- Student handwriting goes to a third party. Mitigate with zero-retention terms and by stripping
  identity before every call — the model sees a crop of a number, never a name — but it remains a
  conversation you must have with each school.
- Vendor dependency: pricing, availability and model behaviour are outside your control.

---

## Part 6 — The recommendation: build one spine, make the recogniser pluggable

The two plans share far more than they differ. **Roughly 70% of the code is identical** — capture,
quality gating, dewarping, red-ink separation, table morphology, anchor detection, Hungarian
association, the constraint solver, calibration, routing, review UI, CSV import. All of that is
classical, free, deterministic and hallucination-proof in both plans.

The plans differ at exactly one interface:

```python
class MarkRecognizer(Protocol):
    def predict(self, crop: Image, legal_values: list[Decimal]) -> dict[Decimal, float]:
        """Return a probability distribution over legal values for one mark cell."""

class QuestionPaperExtractor(Protocol):
    def extract(self, pages: list[Image]) -> list[QuestionRecord]:
        """Return structured question records for one paper."""
```

Implement both backends behind those two interfaces:

- `PaddleTrOCRRecognizer` / `QwenPaperExtractor` — Plan 1
- `ClaudeRecognizer` / `ClaudePaperExtractor` — Plan 2

Then decide with evidence rather than argument. Concretely, my recommendation:

1. **Never pay a language model to find a rectangle.** Localisation, geometry, table lattices and
   association are classical CV in both plans. This is not a cost decision, it is a correctness
   decision — deterministic code cannot hallucinate.
2. **Question paper: use the commercial model.** It runs once per paper, costs about ₹50, and is
   the task where open models are furthest behind. Building this on open models would cost weeks
   to reach worse accuracy on the highest-stakes artefact in the system.
3. **Mark crops: start commercial, migrate to open.** Ship with `ClaudeRecognizer` so you are live
   in Sprint 4. Every crop it processes, plus every teacher correction, becomes a labelled example.
   By the time you have 2,000 labelled crops — around school three — train the open recogniser and
   run it in shadow mode. Promote it when the benchmark says it wins.
4. **This ordering is not a compromise, it is the fast path to Plan 1.** The commercial model is how
   you generate the training data that makes the free model good. Starting with open models means
   labelling 500 crops by hand before you can ship anything.

---

## Part 7 — The benchmark harness (build this in Sprint 4, not later)

You cannot choose between the plans, or claim any accuracy figure, without this.

1. **Gold set**: 500 mark crops and 20 full scripts from this school, labelled by hand, held out
   permanently. Include the hard cases — smudges, overwrites, marks in unusual positions.
2. **Metrics**, computed identically for every backend:
   - field-level accuracy (exact match on the mark value)
   - script-level accuracy (all marks on a script correct)
   - auto-accept rate at a fixed target error, e.g. "what fraction can we accept while keeping
     the error rate below 0.5%?" — this is the number that matters commercially
   - calibration: expected calibration error, so a stated 95% means 95%
   - association accuracy (was the mark bound to the right question) reported separately from
     recognition accuracy — they fail for different reasons and need different fixes
3. **Run every backend on the same gold set** and publish a comparison table internally.
4. **Permanent audit sample** in production: 10% of scripts re-keyed by hand, including cells the
   system was confident about, so you detect silent drift rather than discovering it from a parent.

---

## Part 8 — Step-by-step implementation order

Revised sprint plan incorporating the three modes.

**Sprint 3 — Capture and storage (5 days)**
1. Camera component with live quality gate (blur, glare, coverage, skew) at ~10 fps
2. Mode A single-frame capture; Mode B multi-page capture with per-page retake, reorder, delete
3. IndexedDB temporary store with thumbnails and a 24-hour purge
4. Resumable per-page upload; server-side PDF assembly with `img2pdf` + `pikepdf`
5. Store originals *and* PDF; bind to student by QR or roll number; display in the dashboard
6. **Mode C in full** — this is small, high-value and completely independent of the OCR risk:
   parse, shape-detect, column mapping, dry-run diff, transactional commit, batch undo, template
   download

**Sprint 4 — Localisation and recognition (5 days)**
7. Geometric normalisation: corner detection, homography, illumination flattening, deskew
8. Red-ink separation with per-school hue calibration
9. Table morphology for Mode A; column semantics with a stored `sheet_template`
10. Anchor detection with closed-vocabulary filtering against the frozen Q-matrix
11. Mark-candidate detection on the red mask
12. Hungarian association, then the convention-fitting second pass
13. `MarkRecognizer` interface with the commercial backend implemented first
14. Constraint solver with grand total *and* section totals
15. Calibration and confidence routing; review queue showing crops
16. **The benchmark harness and the gold set**

**Sprint 5 — Mapping, analysis, report (5 days)**
17. `MarkFact` → chapter / sub-topic / tier aggregation via the frozen Q-matrix
18. Loss analysis with denominators, evidence floor, Wilson intervals
19. Board-weighted indicator; paper quality report
20. Principal's report, PDF export, dashboard integration

**Sprint 6 — Hardening and the open-source path (5 days)**
21. Production audit sample and the published accuracy dashboard
22. `PaddleTrOCRRecognizer` implemented behind the same interface
23. Shadow-mode comparison against the commercial backend on live traffic
24. Retention, consent, row-level security, load testing, handover documentation

---

## Part 9 — Decisions I need from you

1. **Marking pen colour.** If teachers mark in red, say so and I will build the red-channel
   separation as the primary path. If it varies, I need three sample scripts to calibrate against.
2. **Is there a total anywhere on the script?** Grand total, section totals, or neither. This
   determines how well-conditioned the constraint solver is, and it is the difference between good
   and excellent accuracy.
3. **The five photographed sample scripts** I asked for previously. Everything in Part 2 —
   especially the association cost weights — is designed against assumptions I cannot validate
   without them.
4. **Do any schools already keep marks in Excel?** If yes, Mode C alone delivers most of the product
   value with none of the OCR risk, and it should ship in Sprint 3 as planned rather than being
   treated as a fallback.
