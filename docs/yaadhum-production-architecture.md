# Project Yaadhum — End-to-End Production Architecture

**Scope of this document.** The pilot scope PDF defines *what* Yaadhum does. This document defines
*how* to build it so that it survives past one school: the method and algorithm chosen for every
layer, the storage engine chosen for every layer, the tech stack, and — critically — the closed
feedback loops that let the system improve from its own data (supervised correction loops,
psychometric re-estimation, and a bandit/RL intervention layer).

**One framing decision that shapes everything below.** Yaadhum is not a "marks report generator".
It is a **cognitive diagnosis system**: the blueprint (question → chapter → sub-topic → typology
tier) is a **Q-matrix**, and student responses over that Q-matrix are exactly the input to
well-established latent-skill models (DINA/G-DINA, IRT, BKT). Adopting that formalism gets three
things for free that a spreadsheet-style analyzer can never give you:

1. **Mastery with uncertainty** instead of "lost 3 marks" (which is noise at n=1 test).
2. **Data-driven validation of your own classification** — Q-matrix refinement tells you which
   question→sub-topic mappings the response data disagrees with. Your reviewer-agreement layer
   gets a second, automatic opinion.
3. **A learnable target for the intervention layer** — Δmastery between assessment cycles is the
   reward signal for the paid product's recommendation policy.

---

## 0. Layer map

| # | Layer | Core method | Store |
|---|-------|-------------|-------|
| L0 | Ingestion (teacher entry / OCR) | Constrained field extraction + validation solver | S3 (images) + Postgres (append-only events) |
| L1 | Blueprint & taxonomy | Controlled vocabulary, versioned as a graph | Postgres + `ltree`/closure table |
| L2 | Question classification | Retrieval (Question Library) → LLM w/ constrained decoding → conformal abstention → human review | Postgres + pgvector |
| L3 | Validation & reconciliation | Hard invariants + Great Expectations contracts | Postgres constraints + quarantine table |
| L4 | Deterministic analyzer | Pure functions over marks × Q-matrix | dbt models → ClickHouse/DuckDB |
| L5 | Psychometric layer | G-DINA / 2PL IRT / hierarchical Bayes shrinkage | NumPyro/Stan → posterior tables in Postgres |
| L6 | Board-weighted indicator | Beta-binomial posterior × board weight, with credible interval | Materialized view |
| L7 | Paper quality | Classical item analysis + distribution divergence vs CBSE target | dbt + ClickHouse |
| L8 | Reporting & narrative | Template-first, LLM only for phrasing, schema-validated | Postgres + object store (rendered PDFs) |
| L9 | Intervention policy (paid) | Contextual bandit → offline RL, with OPE gate | Feature store + logged-bandit table |
| L10 | Feedback & learning | Human corrections → active learning → retrain; teacher actions → reward | MLflow + versioned datasets (LakeFS/DVC) |

---

## L0 — Input collection

### Option A: teacher entry (make this the default path)

The pilot's biggest risk is not modelling — it is **getting clean question-wise marks at all**.
Design for the failure mode where a teacher has 40 scripts and 30 questions.

- **UI**: a grid keyed by *question* (column) × *student* (row), not a form per student. Keyboard-first:
  digits advance the cursor, `/` is never typed (max marks are known from the blueprint, so entry
  is "3" not "3/3").
- **Per-cell validation at keystroke**: `0 ≤ mark ≤ max_marks(q)`, and step size from the marking
  scheme (allow 0.5 only where the scheme allows it).
- **Offline-first**: the school's connectivity will fail. Use IndexedDB + a sync queue with
  **CRDT-free last-write-wins per cell plus an append-only event log** (each cell edit is an event,
  not a mutation). Conflicts become an audit trail, not data loss.
- **Storage**: never store the grid as the source of truth. Store
  `mark_events(student_id, question_id, marks, source, actor_id, ts, device_id)` append-only; the
  grid is a materialized projection. This is what makes OCR-vs-teacher disagreement, later
  corrections, and audit all fall out of the same mechanism.

### Option B: assisted extraction (OCR)

Treat this as **structured field extraction with a hard arithmetic constraint**, not generic OCR.

Pipeline:

1. **Capture normalisation** — dewarp + deskew (OpenCV, or DocAligner), illumination correction,
   300 DPI target. Reject-and-recapture loop on a blur/contrast score before anything else runs.
2. **Page identity** — a printed QR/DataMatrix sticker on the script cover carrying
   `(assessment_id, student_id)`. This removes the single largest OCR error class: attributing
   marks to the wrong student. Do not attempt name-matching handwriting.
3. **Region proposal** — the per-question marks in the margin and the total on the cover.
   Fine-tune a light layout detector (`YOLOv8n` / `DocLayout-YOLO`) on ~300 annotated scripts, or
   skip ML entirely for the pilot by mandating a **pre-printed marks strip** on the cover page with
   fixed boxes (this is the highest-ROI intervention available and costs one A4 template).
4. **Recognition** — handwritten numerals in boxes: a small CNN/CRNN on MNIST-style data
   fine-tuned on teacher handwriting, or `TrOCR-small-handwritten` fine-tuned. Emit a
   **per-field probability distribution over the legal values** (0..max_marks in legal steps),
   not a string. Restricting the output alphabet per field is the single biggest accuracy win.
5. **Constraint solving (the key step)** — you have per-question posteriors `p_q(m)` and a read
   total `T`. Choose the assignment maximising `Σ log p_q(m_q)` subject to `Σ m_q = T`. This is a
   small knapsack/DP over integer (or half-integer) marks — exact, milliseconds, and it repairs a
   large fraction of single-digit misreads. If no assignment reaches a likelihood floor, the script
   is flagged rather than guessed.
6. **Calibration & routing** — calibrate confidences (temperature scaling / isotonic on a held-out
   set) so that "0.95" means 95%. Then route by **expected cost**: auto-accept above a threshold
   chosen to hit a target error rate, otherwise send to a review queue that shows the cropped cell
   image next to the proposed value. Target: human touches <15% of cells but catches >90% of errors.
7. **Learning loop** — every human correction is a labelled example. Retrain on a cadence with
   **uncertainty + disagreement sampling** (label the cells the model is least sure about, and the
   ones where OCR and teacher entry disagreed). Track CER and per-field accuracy per school, since
   handwriting distribution is school-specific.

**Storage**: originals in S3-compatible object storage (`s3://yaadhum/scripts/{school}/{assessment}/{page}.jpg`),
server-side encrypted, lifecycle-expired after the retention window; crops for the review queue in a
short-TTL bucket; extraction results as `mark_events` with `source='ocr'` and a `confidence` +
`model_version` column. **Never overwrite a teacher-entered event with an OCR event** — write both,
resolve by precedence rule at projection time.

**Tech**: Python + FastAPI worker, OpenCV, PyTorch, ONNX Runtime for inference (CPU is fine at this
scale), Temporal or Prefect for the per-script workflow (retries, human-in-the-loop wait states —
Temporal's durable `await signal` models "waiting for a reviewer" natively).

---

## L1 — Taxonomy and blueprint (the asset that compounds)

This is the layer with the longest half-life. Everything else can be rewritten; the validated
taxonomy and Question Library are the moat.

**Model it as a versioned DAG, not enum columns.**

```sql
-- controlled vocabulary, versioned, never hard-deleted
create table taxonomy_node (
  node_id      uuid primary key,
  kind         text not null check (kind in ('board','subject','grade','chapter','subtopic','qtype','tier')),
  code         text not null,             -- stable, human-readable: 'X.MATH.SAV.COMPOSITE'
  label        text not null,
  parent_id    uuid references taxonomy_node(node_id),
  path         ltree not null,            -- fast subtree queries
  valid_from   date not null,
  valid_to     date,                      -- SCD-2: syllabus changes are versioned, not destructive
  curriculum_version text not null        -- 'CBSE-2026-27'
);
create index on taxonomy_node using gist (path);
```

Rules that keep it clean:

- **No free-text tagging, ever** (already in scope — enforce it at the DB level with FK constraints,
  not in the UI).
- **Slowly-changing dimension type 2**: when CBSE revises a chapter, you add a node version and
  keep the old one. Historical reports must remain reproducible.
- **Board weights are data, not code**: `chapter_weight(curriculum_version, chapter_node_id, weight_pct, source_doc_url)`.
- **Aliases table** so "Surface Areas & Volumes", "SA&V", "Ch 13" all resolve to one node.

**Blueprint = Q-matrix.** Each question maps to one or more sub-topics:

```sql
create table question (
  question_id uuid primary key,
  assessment_id uuid not null,
  number text not null,          -- '4', '26(a)'
  max_marks numeric(4,2) not null,
  stem_text text,                -- for retrieval/dedup
  stem_hash text,                -- normalised hash for exact reuse
  embedding vector(1024)         -- pgvector, for near-duplicate reuse
);
create table question_skill (   -- the Q-matrix
  question_id uuid references question,
  subtopic_id uuid references taxonomy_node,
  weight numeric default 1.0,    -- for multi-skill questions
  tier_id uuid references taxonomy_node,
  qtype_id uuid references taxonomy_node,
  primary key (question_id, subtopic_id)
);
```

Multi-skill questions matter: a composite-solid word problem loads on *both* "composite solids"
and "word problem interpretation". Allowing >1 skill per question is what makes G-DINA (below)
able to separate "can't do the geometry" from "can't parse the problem".

**Storage**: Postgres. Taxonomy is small, relational, heavily joined, and needs constraints and
transactions — no other engine is appropriate. `pgvector` alongside it avoids a separate vector DB
at pilot scale (and at 10⁵ questions, still avoids it).

---

## L2 — Question classification (the accuracy-critical layer)

The scope doc is right that a wrong classification poisons everything downstream. Build it as a
**cascade with an explicit abstain option**, never as a single model call.

### Stage 2.1 — Exact/near-duplicate reuse (Question Library)

Most questions in Indian school assessments are recycled from NCERT, sample papers, and previous
years. Exploit this hard.

- Normalise the stem (lowercase, collapse whitespace, canonicalise numbers to `<NUM>`, strip
  figure references) → `stem_hash`. Exact hit = reuse the validated mapping, confidence 1.0.
- Near-duplicate: **MinHash/LSH on character 5-grams** for cheap recall, plus **cosine similarity
  over multilingual embeddings** (`BGE-M3` or `multilingual-e5-large` — both handle Tamil/English
  code-mixing, which matters in Krishnagiri) for semantic recall. Above a tuned similarity
  threshold with unanimous k-NN labels → reuse.
- This is the layer that makes cycle 2 of the pilot dramatically cheaper than cycle 1. Track
  **reuse rate** as a first-class product metric.

### Stage 2.2 — Model classification

For genuinely new questions, an ensemble:

- **Retrieval-augmented LLM** (Claude/GPT class, or a hosted open model) with:
  - the k nearest validated library questions as few-shot exemplars,
  - the *legal* sub-topic list for the detected chapter injected into the prompt,
  - **structured output / constrained decoding** so the model can only emit taxonomy IDs that
    exist — never free text (JSON schema + tool-use enforcement, then FK-validate anyway),
  - a required **rationale** field (improves accuracy and gives reviewers something to check),
  - self-consistency: sample k=5 at temperature ~0.7, take the majority; the vote spread is a
    usable uncertainty signal.
- **A cheap supervised head** trained on the growing library: embeddings → linear/`SetFit`
  classifier per chapter. Once you have ~2–3k validated questions this typically *beats* the LLM
  on your own distribution and costs ~nothing. Keep both; disagreement routes to review.

### Stage 2.3 — Abstention with a guarantee (conformal prediction)

Don't hand-tune a confidence threshold. Use **split conformal prediction**: on a held-out validated
set, calibrate a threshold such that the returned label *set* contains the truth with probability
≥ 1−α (e.g. 95%). Then:

- singleton set → auto-accept,
- set size >1 or empty → human review, with the candidate set pre-selected in the UI.

This gives you a defensible statement — "classification is ≥95% reliable, and everything below that
bar was human-reviewed" — which is exactly what a principal will ask for.

### Stage 2.4 — Human adjudication

- **Two independent reviewers** at pilot setup (already in scope). Measure **Cohen's κ** per
  taxonomy level; report it in the pilot success metrics (target κ ≥ 0.75 for sub-topic, ≥ 0.85 for
  chapter, ≥ 0.70 for tier — tier is genuinely the hardest).
- Aggregate labels with **Dawid–Skene / MACE** rather than simple majority once you have ≥3
  annotators: it estimates each reviewer's reliability and weights them, and flags a systematically
  drifting reviewer.
- Disagreements go to a third adjudicator; the adjudicated item is added to the library **and** to
  the conformal calibration set.
- **Tooling**: Label Studio (self-hosted) for the review UI, or a thin custom Next.js queue — the
  custom one is usually worth it because the review needs to show the question, the candidate
  set, the nearest library matches, and the rationale side by side.

### Stage 2.5 — Active learning

Choose what humans label next by expected value, not arbitrarily:
- highest predictive entropy / smallest margin,
- ensemble disagreement (LLM vs supervised head),
- questions with the **highest downstream leverage**: high `max_marks`, appearing in a
  high-board-weight chapter, or answered by many students. A 6-mark question in a 15%-weight
  chapter is worth 10× the review time of a 1-mark question.

**Storage**: `question_classification(question_id, subtopic_id, tier_id, source, model_version,
confidence, conformal_set, created_at)` — append-only, plus a `question_classification_current`
view resolving by precedence `human_adjudicated > human > library_reuse > model`. Never mutate.
`pgvector` HNSW index for retrieval. Keep the labelled dataset snapshotted per training run
(DVC or LakeFS) so every model version is reproducible.

---

## L3 — Validation and reconciliation

Hard invariants, enforced as close to the data as possible:

- `Σ marks over questions == recorded_total` (the scope's mandatory check). Implement as a
  **deferred DB constraint or a validation job that quarantines**, not as UI-only logic.
- `0 ≤ marks_q ≤ max_marks_q`, legal step sizes.
- Every question in an assessment has a classification with status ≥ threshold before report
  generation.
- Every enrolled student has either a complete script or an explicit `absent` marker (missing ≠ zero
  — conflating them destroys the analysis).
- `Σ max_marks == paper total`.

Failures write to `data_quality_flag(entity, rule, severity, detail, status)` and **block report
generation** for the affected student only, not the whole batch.

Beyond invariants, run **statistical anomaly checks**: a question everyone gets right or everyone
gets wrong (possible mis-key or mis-entry), a student whose profile flips sharply from prior
cycles, a question whose point-biserial correlation is negative (strong signal of a marking or
entry error, or a genuinely bad question — either way, a human should look).

**Tooling**: Pandera or Great Expectations for data contracts in the pipeline; dbt tests
(`not_null`, `accepted_values`, `relationships`, plus custom singular tests for the sum rule) at the
warehouse layer. Fail the DAG loudly; never silently drop rows.

**Data-quality lineage** is already in scope (`teacher_entered / ocr_extracted / manually_verified`).
Model it as a per-cell provenance enum on `mark_events` and surface it in the report footer — it is
a trust feature.

---

## L4 — Deterministic analyzer

Keep this layer **pure, deterministic, and versioned**. No ML. It is what teachers will check by
hand, and it must reconcile to the mark sheet exactly.

Computations (all straightforward, all as dbt models):

- `loss(student, chapter) = Σ_q∈chapter (max_marks_q − marks_q)`
- `loss_rate(student, sub-topic) = Σ lost / Σ available` — always report the **rate with the
  denominator visible** ("3 of 4 marks available"), because "lost 3 marks" is meaningless without it.
- `loss(student, tier)` and the **sub-topic × tier cross-tab** — this is the diagnostic core:
  high R&U mastery + low AP mastery on the *same* sub-topic is the "knows the formula, can't apply
  it" signature the scope doc describes, and it is only detectable if the paper actually contains
  both tiers for that sub-topic. **Check that coverage and say so when it's absent** rather than
  asserting a diagnosis the paper cannot support.
- Class aggregates: per-question mean score rate, per-sub-topic class loss rate, and the ranked
  "commonly missed" list.

**Small-sample honesty (do not skip this).** With 1–4 marks available per sub-topic, a raw
percentage is nearly pure noise. Two mitigations, both cheap:

1. **Empirical-Bayes shrinkage**: model sub-topic score as Beta-Binomial with a prior fitted from
   the class (or across schools once you have them). Report the posterior mean and a credible
   interval. A student who lost 1 of 1 mark should read as "weak evidence of a gap", not "0% mastery".
2. **Suppress claims below an evidence floor**: if a sub-topic has <2 marks or <2 questions, mark
   the finding "insufficient evidence in this paper" instead of reporting a number. This single rule
   will do more for teacher trust than any model.

**Storage**: source marks stay in Postgres; analytics run in **dbt** materialising into
**ClickHouse** (or DuckDB while you're at pilot scale — a single-file DuckDB warehouse is entirely
adequate for one school and removes an ops burden; the dbt models port to ClickHouse unchanged when
you scale to districts). Snapshot each report's inputs so a regenerated report is bit-identical:
store `analysis_run(run_id, assessment_id, code_version, taxonomy_version, model_versions, ts)` and
tag every derived row with `run_id`.

---

## L5 — Psychometric layer (where Yaadhum stops being a spreadsheet)

Run **after** L4 and present it *alongside* the deterministic numbers, never instead of them.

### 5.1 Cognitive diagnosis: G-DINA over your Q-matrix

Your blueprint is a Q-matrix `Q[question, sub-topic]`. Fit a **G-DINA** model (generalises DINA/DINO/
A-CDM) to get, per student, a **posterior probability of mastery for each sub-topic**, rather than
a mark count. Benefits:

- Pools evidence across every question touching a sub-topic, weighted by how diagnostic each
  question actually is (estimated slip and guess parameters).
- Handles multi-skill questions properly.
- Produces `P(mastered)` — directly usable for grouping, thresholding, and as the RL state.

At n≈40 students, a fully free G-DINA is under-identified. Handle it by:
- restricting to DINA (2 params/item: slip, guess) with **informative priors** (e.g. Beta(2,10) on
  both), fitted in **NumPyro/Stan** with MCMC (fast at this size), and
- **hierarchical partial pooling** across classes/schools/cycles as data accumulates — item
  parameters for reused library questions pool across every school that used them. This is the
  compounding asset again: a question used 20 times has well-estimated parameters, so a school
  using it the 21st time gets a better diagnosis on day one.

### 5.2 Item response theory for item quality

Fit a **2PL IRT** model per assessment (or Rasch at small n) to get item difficulty and
discrimination. Uses:
- feeds the paper-quality report (L7),
- flags items with near-zero or negative discrimination as broken,
- gives a **latent ability estimate θ** that is comparable across the two pilot cycles even though
  the papers differ — which is exactly what you need to claim "improvement", since raw percentages
  across two different papers are not comparable.

Equating across cycles requires **anchor items**: deliberately reuse 4–6 validated questions
across cycle 1 and cycle 2. This is a *pilot design decision you must make now*, not a modelling
choice you can make later. Without anchors, cross-cycle improvement claims are unfalsifiable.

### 5.3 Q-matrix validation (free QC on your own taxonomy)

Run the **de la Torre & Chiu δ-method / stepwise Q-matrix refinement**: it identifies questions
whose response patterns are inconsistent with their assigned skills. Feed those back into the L2
review queue as a *third reviewer that never gets tired*. Over the pilot this is a strong,
data-grounded answer to "how do you know your classification is right?"

### 5.4 Longitudinal tracking

Across the two cycles (and beyond, in the paid product), track mastery with **Bayesian Knowledge
Tracing** or a state-space model per (student, sub-topic): prior mastery → intervention → posterior
mastery. This is the substrate for both progress tracking and the RL reward.

**Storage**: posteriors are the model output, not the truth — store them versioned and separate:
`skill_mastery_posterior(run_id, student_id, subtopic_id, p_mastery, ci_low, ci_high, model_version)`.
Never overwrite; the whole point is being able to compare cycle 1 and cycle 2 estimates produced by
different model versions and know which is which.

**Tech**: Python, NumPyro (JAX) or Stan via CmdStanPy; batch job orchestrated by Prefect/Dagster;
outputs written back to Postgres and to the warehouse. No GPU needed at this scale.

---

## L6 — Board-weighted diagnostic indicator

The scope formula:

```
indicator(student, chapter) = (marks_lost_in_chapter / marks_available_in_chapter_in_this_test)
                              × board_weight(chapter)
```

Production hardening:

- **Propagate uncertainty.** `marks_lost / marks_available` is a proportion from a tiny denominator.
  Use the Beta-Binomial posterior from L4 and report the indicator as an interval. Rank chapters by
  the *lower* bound when you want a conservative "definitely a problem" list, and by the mean when
  you want a watchlist.
- **Handle zero-coverage chapters explicitly.** If a chapter has 0 marks in this test but 12% board
  weight, the indicator is undefined — and that is itself the most important finding on the page
  ("this test gives you no information about a 12%-weight chapter"). Emit it as a distinct
  *coverage gap* item, not as a 0.
- **Normalise for comparability**: report both the raw indicator and its share of total indicator
  mass, so "where do I spend the next two weeks" has a defensible answer.
- Keep `board_weight` versioned by `curriculum_version` with a citation URL — a principal will
  challenge these numbers.
- **Naming discipline**: the scope is right to call this an indicator, not a prediction. Enforce it
  in the report templates with a lint rule in CI that rejects predictive phrasing ("will score",
  "expected board marks") in template strings. Sounds petty; prevents the one claim that can end a
  school relationship.

**Storage**: a materialized view keyed by `run_id`, refreshed per analysis run.

---

## L7 — Paper quality analysis

Two independent questions: *is the paper well-built?* and *does it match the board?*

**Build quality (classical item analysis + IRT from L5):**
- difficulty `p` per item, target spread roughly 0.3–0.8 with a few anchors outside,
- discrimination: point-biserial `r_pb` (flag `< 0.2`; investigate `< 0`),
- reliability: **Cronbach's α** and, better for non-parallel items, **McDonald's ω**,
- an item table sorted by "most likely to be a bad question".

**Board alignment:**
- Observed vs target typology distribution (R&U 54 / AP 24 / AEC 22) — compare with a
  **chi-square goodness-of-fit** and report the **KL divergence** or **total variation distance**
  as a single 0–1 "alignment score" that is stable enough to trend over time.
- Chapter coverage vs board weights: same treatment, plus explicit coverage-gap list from L6.
- Mark-type mix (MCQ / short / long) vs board pattern.
- Output a one-line verdict of the form the scope shows: *"Paper is recall-heavy relative to the
  expected board distribution: 71% R&U vs 54% target; AEC under-represented at 8% vs 22%."*

Note the **confound worth stating in the report**: typology tier is a property of the *question as
classified*, so alignment quality inherits classification quality. Show the classification
confidence summary on the same page.

---

## L8 — Reporting and narrative generation

**Template-first, LLM-second.** Every number in a report comes from L4–L7. The LLM's only job is
fluency and ordering, and it must never see raw arithmetic to perform.

Architecture:
1. **Insight selection** (deterministic): rank candidate findings by
   `board_weight × evidence_strength × actionability`, apply the evidence floor from L4, cap at
   3–5 findings. A report with 14 findings changes no behaviour.
2. **Narrative assembly**: Jinja templates per finding type, with slots. This covers ~90% of
   reports and is fully auditable.
3. **Optional LLM polish**: pass the *structured finding objects* and ask for phrasing only, with
   output constrained to a schema, then run a **numeric fidelity check** — extract every number
   from the generated text and assert it appears in the source findings. Reject and fall back to
   the template on mismatch. This is a cheap, complete defence against fabricated numbers.
4. **Multilingual**: generate English + Tamil for parent/student-facing text later; keep the
   finding objects language-neutral so translation is a rendering concern.
5. **Practice recommendations**: retrieve from a tagged resource bank (NCERT exercises, CBSE sample
   paper items) keyed by `subtopic_id × tier_id`. Content-based retrieval at first; the bandit in L9
   takes over ranking once you have outcome data. Never let an LLM invent an exercise number —
   retrieve, don't generate.

**Storage**: findings as structured rows (`report_finding(run_id, student_id, type, payload jsonb,
rank)`) so reports are queryable and re-renderable; rendered PDF/HTML in object storage with a
content hash. Rendering via WeasyPrint or a headless-Chromium service.

---

## L9 — Intervention policy: the learning layer (paid product)

This is where "learns from data, like reinforcement" becomes concrete. Be deliberate about
sequencing — reaching for deep RL on 40 students would be malpractice.

### The decision problem

**State** `s`: student's mastery posterior vector (L5), recent trajectory, chapter board weights,
time remaining in term, class context.
**Action** `a`: which sub-topic to target next, which remediation group to place the student in,
which worksheet/practice set to assign, at what difficulty.
**Reward** `r`: primarily **Δ mastery on the targeted sub-topic at the next assessment** (from L5,
which is why the anchor-item design matters), plus shaping terms:
- teacher acceptance of the suggestion (immediate, cheap, dense),
- completion rate of the assigned work,
- a penalty on teacher workload and on churning students between groups,
- a fairness term so the policy doesn't concentrate attention on students near a grade boundary.

### Staged rollout — this is the important part

**Stage 0 (pilot): rules + psychometrics, zero learning.** Rank by board-weighted mastery deficit,
group by mastery pattern (k-means or simple thresholding on the posterior vector — the scope's
"Group A conceptual / Group B application" is exactly a 2-cluster split on the R&U vs AP mastery
plane). **Log everything** in bandit format from day one, even though nothing is learning yet:
`(state_features, action, propensity, reward, timestamp, policy_version)`. Without logged
propensities you cannot do off-policy evaluation later, and retrofitting them is impossible.

**Stage 1: contextual bandit.** Once you have a few thousand (student × recommendation × outcome)
tuples: LinUCB or **Thompson sampling with a hierarchical Bayesian prior** (pool across students
within class, classes within school). Handles cold start gracefully, which matters because every
new school starts cold. Keep exploration **small and bounded** (ε ≈ 0.05–0.1) and never explore
into pedagogically bad actions — constrain the action space to teacher-approved options first.

**Stage 2: offline RL.** With multi-step trajectories across several cycles, the problem is genuinely
sequential (today's remediation changes what's optimal next month). Use **conservative offline
methods** — CQL or IQL — trained purely on logged data. Do not run online policy-gradient RL against
children's learning.

**Stage 3 gate: off-policy evaluation before any deployment.** Estimate the new policy's value
with **IPS, self-normalised IPS, and doubly-robust** estimators on logged data, with confidence
intervals. Ship only if the DR lower bound beats the incumbent. Then A/B (or better,
**switchback by class**) with a pre-registered primary metric.

### Safety constraints that are non-negotiable

- **Teacher-in-the-loop always**: the policy proposes, the teacher disposes. Every suggestion is
  accept/edit/reject, and the rejection is itself training signal.
- **No autonomous student-facing action** in any stage.
- **Guardrails**: never recommend >N minutes of work, never leave a student without any
  recommendation, never let a student's targeted sub-topic go untouched for >2 cycles.
- **Reward-hacking watch**: the obvious failure is a policy that targets easy sub-topics to maximise
  Δmastery. Counter by weighting reward with board weight and by monitoring the *distribution* of
  targeted sub-topics against the deficit distribution.
- **Fairness monitoring**: track outcome parity across gender and prior-attainment bands; a policy
  that improves the class mean while abandoning the bottom decile is a failure, not a success.

**Storage**: a dedicated append-only `policy_decision` table (immutable, includes propensity and the
full feature vector as it was at decision time — not a re-derivation), and a **feature store** to
guarantee train/serve consistency. At this scale, "feature store" = a set of dbt-built,
point-in-time-correct feature tables in Postgres with an `as_of` timestamp; adopt Feast only when
online low-latency serving actually appears.

---

## L10 — The learning loops, consolidated

Four distinct loops, different cadences, different owners:

| Loop | Signal | Method | Cadence |
|------|--------|--------|---------|
| **OCR** | Reviewer corrections on low-confidence cells | Supervised fine-tune + uncertainty sampling | Per school onboarding, then monthly |
| **Classification** | Adjudicated labels, Q-matrix refinement flags | Library growth + retrain supervised head + re-calibrate conformal threshold | Per assessment batch |
| **Psychometrics** | Every new response | Hierarchical re-estimation, item params pooled across schools | Per assessment |
| **Intervention** | Δmastery, teacher accept/reject, completion | Bandit → offline RL, gated by OPE | Per cycle (quarterly) |

Cross-cutting requirements for all four:
- **Every model version is reproducible**: dataset snapshot (LakeFS/DVC) + code SHA + params, tracked
  in **MLflow**. A report generated in March must be regenerable in December.
- **Shadow mode before promotion**: new model runs alongside the incumbent, disagreements are logged
  and reviewed, promotion is a human decision on evidence.
- **Drift monitoring** (Evidently or hand-rolled): input drift (new question styles, new handwriting),
  prediction drift (tier distribution shifting), and performance drift on the rolling human-reviewed
  sample. **Always keep a small random sample of high-confidence items in the human review queue** —
  otherwise you only ever measure accuracy on the hard cases and go blind to silent degradation.

---

## Storage decisions, summarised

| Data | Engine | Why |
|------|--------|-----|
| Marks events, students, taxonomy, classifications, flags | **PostgreSQL** (RDS/Supabase, `ap-south-1`) | Transactional, relational, constraint-enforced, small. Append-only event tables + projections. |
| Question embeddings | **pgvector** in the same Postgres | Avoids a second datastore; HNSW is ample to ~10⁶ vectors. |
| Answer script images, rendered reports | **S3-compatible object store** (S3 / MinIO), SSE-KMS, lifecycle rules | Blobs never belong in a DB. |
| Analytical models, aggregates, dashboards | **DuckDB (pilot) → ClickHouse (scale)**, built by **dbt** | Columnar, cheap, and dbt gives you tests + lineage + docs for free. |
| Feature tables for the policy layer | dbt-built point-in-time tables in Postgres → Feast later | Train/serve consistency is the requirement, not latency. |
| Model artifacts, metrics, lineage | **MLflow** + object store | Reproducibility. |
| Labelled datasets | **LakeFS or DVC** on the object store | Data versioning; retraining must be replayable. |
| Cache, queues, rate limits | **Redis** | — |
| Workflow state, human-in-the-loop waits | **Temporal** (or Prefect for simpler needs) | Durable execution across day-long human review waits. |
| Audit log | Append-only Postgres table + periodic object-store export | Compliance and trust. |

---

## Application stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy + Alembic, Pydantic v2 as the contract layer between
  every stage (types are your best defence in a pipeline this branchy).
- **Analytics/ML**: pandas/Polars, scikit-learn, PyTorch, NumPyro (JAX) or CmdStanPy, `py-irt`/
  custom G-DINA, ONNX Runtime for OCR inference.
- **Orchestration**: Temporal for per-script/per-assessment workflows with human waits; Dagster or
  Prefect for the batch analytics DAG (Dagster if you want asset lineage to line up with dbt).
- **Transform**: dbt-core (dbt tests double as the data-quality layer).
- **Frontend**: Next.js + TypeScript, TanStack Table for the marks grid, offline via IndexedDB +
  a sync queue, Tailwind + shadcn/ui. Recharts/Visx for charts.
- **Reports**: Jinja → HTML → WeasyPrint PDF; reports are also viewable in-app.
- **Auth**: OIDC (Clerk/Auth0/Keycloak), RBAC with roles `teacher / hod / principal / admin /
  reviewer`, and **row-level security in Postgres** scoped by `school_id` — enforce tenancy in the
  database, not only in application code.
- **Infra**: containers on ECS Fargate / GKE Autoscale, or a single well-provisioned VM with Docker
  Compose for the pilot (be honest: one school does not need Kubernetes). Terraform for whatever
  you do provision.
- **Observability**: OpenTelemetry traces, Prometheus + Grafana, Sentry, structured JSON logs with
  `run_id` propagated end-to-end so any number in any report traces back to the events that produced it.
- **CI/CD**: GitHub Actions — unit tests, dbt build against a seeded warehouse, golden-file tests on
  report generation, the report-phrasing lint rule, and a model-eval gate that blocks promotion on
  metric regression.

---

## Privacy, compliance, and ethics

Non-optional, because this is children's data in India.

- **DPDP Act 2023**: children's personal data requires **verifiable parental consent** and prohibits
  tracking/behavioural monitoring and targeted advertising directed at children. Design consent
  capture into school onboarding, with the school as the collecting party and a documented DPA.
- **Data minimisation**: the analytics layers need `student_id`, not names. Keep identity in a
  separate schema with restricted access; the warehouse gets pseudonymous IDs only.
- **Encryption** at rest (KMS) and in transit; **residency in `ap-south-1`**.
- **Retention**: answer script images expire on a defined schedule (e.g. 180 days) once extraction is
  verified; marks and derived analytics persist longer under an explicit policy.
- **No training third-party LLMs on student data**: use zero-retention API terms, and prefer sending
  *question text* (not student data) to any external model. Question classification needs the question,
  never the student. Enforce this at the API-client boundary.
- **Right to explanation**: every report claim links to the questions and marks that produced it.
  This is achievable precisely because L4 is deterministic — keep it that way.
- **Anti-labelling**: never render a student-level label like "weak student"; findings are
  sub-topic-scoped and time-scoped. Ban ranking students publicly in any teacher-facing view.

---

## Pilot vs. production: what to actually build first

The architecture above is the destination. Building all of it for one school and one unit test
would guarantee the pilot fails on timeline. Sequence:

**Pilot (weeks 0–8) — build only this:**
Postgres + FastAPI + Next.js marks grid (teacher entry only; OCR via pre-printed marks strip *or*
skipped entirely). Taxonomy tables + a manually curated Q-matrix, dual-reviewer classification in a
simple queue. dbt + DuckDB for L4. Deterministic reports with Jinja templates and the evidence
floor. Board-weighted indicator with credible intervals. Classical item analysis for the paper
report. Log everything append-only, including propensity-shaped fields you don't yet use.
*Explicitly include anchor items across the two cycles.* Skip: G-DINA, bandits, Temporal, ClickHouse,
Feast, Kubernetes.

**v1 (post-pilot, 2–3 schools):** OCR cascade with the constraint solver; classification cascade with
retrieval + conformal abstention; G-DINA/IRT layer with hierarchical pooling; MLflow + shadow mode;
Temporal for human-in-the-loop workflows.

**v2 (paid product, 10+ schools):** intervention policy Stage 1 bandit behind OPE gates; progress
tracking with BKT; principal dashboards on ClickHouse; multi-tenant hardening, RLS, SSO.

---

## Success metrics, made measurable

Extending the scope doc's list with the specific statistic for each:

**Accuracy** — classification: Cohen's κ (inter-reviewer) and macro-F1 vs adjudicated gold, per
taxonomy level; conformal coverage (target ≥95%) and abstention rate. Marks capture: cell-level
error rate against a re-keyed audit sample of ≥10% of scripts. OCR: character error rate and
field-level accuracy, plus % auto-accepted.

**Reliability of the diagnosis** — the honest test: does cycle-1 sub-topic mastery predict cycle-2
performance on that sub-topic better than overall marks alone? Report AUC / incremental R² over a
marks-only baseline. If it doesn't, the diagnostic claim is not yet earned.

**Adoption** — report open rate, time-in-report, % of teachers who used the intervention view,
question-library reuse rate in cycle 2 (a direct proxy for whether the system is compounding).

**Impact** — pre-registered: change in class mastery on the sub-topics a teacher targeted, versus
sub-topics they didn't (a within-class difference-in-differences, which is feasible at n=40 and
avoids needing a control school). Plus qualitative: did reteaching plans actually change?

---

## The three risks worth naming up front

1. **Sample size.** One class, one test, 1–4 marks per sub-topic. Every methodological choice above
   (shrinkage, credible intervals, evidence floors, hierarchical pooling, anchor items) exists to
   stop the system from confidently reporting noise. Skipping them doesn't just risk being wrong —
   it risks a teacher reteaching the wrong chapter, which is worse than doing nothing.
2. **Classification is load-bearing.** It's the cascade's first link and everything downstream
   inherits its error. The conformal abstention + dual review + Q-matrix refinement stack is the
   answer; budget real reviewer hours for cycle 1.
3. **The paper limits the diagnosis.** You cannot diagnose application weakness in a chapter whose
   questions are all recall. The paper-quality report and the coverage-gap output should be framed
   as the *first* deliverable to the principal, not the last — it's the finding that makes the next
   cycle's data better.
