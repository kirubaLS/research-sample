# Yaadhum

Assessment diagnostics for CBSE schools. Two products in one application:

1. **Interest test** — a 36-item RIASEC inventory a Class X student takes themselves,
   scored into a Holland code and a stream indication that only the principal sees.
2. **Marks engine** — reads a question paper and a student's answer script, binds every
   red mark to the right question, reconciles the result against the totals the teacher
   wrote, and turns it into a chapter / sub-topic / tier diagnosis.

Design documents, diagrams and the analysis of eight real CBSE 2026 papers are in
[`docs/`](docs/).

---

## Quick start

```bash
make install          # backend + frontend dependencies
make test             # 62 tests
docker compose up -d  # postgres, redis, minio (optional — SQLite works out of the box)
make seed             # demo school, taxonomy, roster, assessment — prints an API key
make api              # http://localhost:8000/docs
make web              # http://localhost:3000
```

`make seed` prints the class code and API key. Open `/t/<class-code>` for the student
flow and `/admin` for the dashboard.

---

## What is actually implemented

Everything below is working code with tests, not scaffolding.

### The one architectural rule

**Seven layers, exactly one of which contains a model.** Capture, restoration, ink
separation, localisation, association, reconciliation and reporting are deterministic
OpenCV / SciPy / Python. Only *recognition* calls an LLM. That is what lets the paid
recogniser be swapped for a free one by changing a configuration value, and why a failure
is always localised to a named layer instead of "the AI got it wrong".

### Use case 2 — the algorithms that matter

| Module | What it does |
|---|---|
| `app/mapping/solver.py` | **The arithmetic oracle.** Exact constrained MAP assignment: maximise `Σ log p(m)` subject to grand, section and page totals, on the legal mark lattice. Laminar constraints are solved by max-plus convolution over the constraint tree. Repairs a confidently misread 3 into a 1 because the arithmetic says so; flags rather than guesses when nothing reconciles. |
| `app/mapping/association.py` | Binding a mark to its question as a **constrained assignment problem** (Hungarian), then a second pass that fits *this teacher's* layout convention from the confident bindings and re-solves. |
| `app/vision/ink.py` | Teacher red vs student black/blue, with per-school hue centroids fitted by **unsupervised k-means on ink pixels from three unlabelled pages**. Strips the printed red margin rule first. |
| `app/vision/imposition.py` | N-up detection from the `Page N of M` footer. Measured: 1-up (five papers), 2-up (Tamil), 4-up (both Maths). |
| `app/vision/orientation.py` | Orientation from **content**, not metadata — all eight papers report `rotation = 0` while Tamil prints at 90°. |
| `app/extraction/mark_grammar.py` | Three mark forms (`3`, `6×3=18`, `(Grammar) 12 Marks`), the measured right-aligned band at x ≈ 0.88 W, and the **page-furniture filter** that stops the Tamil paper's Q.P. code `10` being read as a mark on every page. |
| `app/extraction/address.py` | The Q-matrix key is `SECTION / QNO / SUBPART / CHOICE`, not the question number. Closed-vocabulary resolution rejects an invented `16(c)`; Devanagari and Tamil numerals normalise. |
| `app/extraction/choice.py` | Internal choice: alternatives contribute their marks **once**, and the unattempted one is `NOT_OFFERED`. |
| `app/extraction/verification.py` | The four gates the paper prints for us — question count, section marks, section arithmetic, paper total. |
| `app/taxonomy/tier.py` | **R&U / AP / AEC** from four independent signals, fused, with conformal abstention. |
| `app/analysis/` | Loss with denominators and Wilson intervals, the evidence floor, board-weighted indicators with coverage gaps, item analysis, Cronbach's α, typology alignment. |

### How the tier is decided

The verb lexicon never outputs a tier. **Bloom level = action × familiarity**, because
"Applying" means carrying out a known procedure in a *new* situation:

|  | T_VERBATIM | PRACTISED | ADAPTED | NOVEL |
|---|---|---|---|---|
| RECALL · EXPLAIN | R&U | R&U | R&U | R&U |
| **EXECUTE · PROVE** | **R&U** | **AP** | AP | AEC |
| APPLY_IN_CONTEXT | AP | AP | AP | AEC |
| ANALYSE · EVALUATE · CREATE | AP | AEC | AEC | AEC |

`T_VERBATIM` means the chapter *body* showed the answer — a named theorem or worked
example: reproduction. `PRACTISED` means it appeared as an *exercise*: the student carried
the procedure out themselves, which is Applying.

That is why *"Prove that √5 is an irrational number"* is **R&U** (Theorem 1.3, in the
chapter body) while *"Prove that 3 + 2√5 is irrational"* is **AP** (Exercise 1.2). Both
carry the verb "prove". See `tests/test_tier.py`.

The CBSE 54/24/22 blueprint is applied **only as a tie-break on abstained items, and only
when the paper declares a blueprint**. On a school's own unit test it is never applied —
a recall-heavy paper is the most valuable finding in the report, not an error to correct.

### Use case 1 — the interest test

36 items, six per scale, in English, Tamil and Hindi. Two steps cheap career tools skip:

* **ipsative centering** — without subtracting the person's own mean, a student who likes
  everything scores high on all six types and gets a meaningless result;
* **the differentiation gate** — when the profile is genuinely flat there is no preference
  to report, so the system withholds the recommendation and says why.

Validity screening (long-string, response speed, reverse-keyed pairs) marks a session
`valid` / `suspect` / `invalid`; an invalid session is never scored.

**The student journey is a dead end.** `/t/session/{id}/complete` returns a thank-you and
nothing else — no score, no code, no stream. `tests/test_api_end_to_end.py` asserts that
none of those words appear in the response body.

---

## Data model

Three states for a mark, not two: `awarded`, `absent`, and **`not_offered`** — the
unattempted half of a choice pair. Scoring it zero would systematically mark every student
weak in whichever topic they chose to avoid.

`mark_event` is **append-only**. A correction is a new row; a projection resolves the
current value by source precedence (`teacher > csv > cover_ocr > page_ocr`). Audit trail,
OCR-versus-teacher reconciliation and correction history all fall out of that one rule.

`ml_corpus` is a separate schema with separate credentials — every prediction with its
**full distribution** (not the argmax), every human label with `time_taken_ms`, every
disagreement, and `consent_class` set at capture time. This is the bridge from a paid
launch to a free recogniser: roughly 2,400 labelled crops per class per term.

---

## Layout

```
backend/
  app/
    api/            FastAPI routes: interest test, marks engine, reports
    models/         SQLAlchemy 2.0 — 26 tables
    psychometrics/  RIASEC instrument, scoring, validity
    vision/         imposition, orientation, quality gate, ink separation
    extraction/     mark grammar, addresses, choice groups, verification gates
    mapping/        Hungarian association, the constraint solver
    taxonomy/       verb lexicon, familiarity buckets, tier ensemble
    analysis/       diagnostics, board indicators, paper quality
    data/           item bank, verb lexicon, stream matrix
  tests/            62 tests
frontend/
  app/t/            student flow: profile → test → thank you
  app/admin/        dashboard and the scanner
  components/       Scanner: quality gate, per-page retake, offline queue
  lib/              API client, browser quality gate, IndexedDB page store
docs/               design documents, diagrams, paper analysis
```

---

## Deployment

`render.yaml` defines both services and the database; see **[docs/DEPLOY.md](docs/DEPLOY.md)**
for the walkthrough.

One decision to make before you deploy: **Render has no India region.** Student answer
scripts contain children's handwriting, so for anything past the pilot, run the compute on
Render/Singapore but point `YAADHUM_DATABASE_URL` and the object store at `ap-south-1`.

Configured for split hosting: CORS from an explicit origin list (never `*`, because the
student route is unauthenticated), a `/healthz` liveness path separate from the `/health`
readiness probe, `postgres://` URL normalisation, Alembic migrations in the pre-deploy
step, per-IP rate limiting on the public route, and security headers.

---

## Status

Implemented and tested: the schema, both scoring engines, every algorithm in the table
above, the API for both use cases, and the frontend flows.

Deliberately not implemented yet, with the reasoning in `docs/`:

* the LLM recognition backend behind `MarkRecognizer` — the interface is defined and the
  cost cascade decided, but it needs real photographed scripts to calibrate against;
* PDF ingest and page rendering (PyMuPDF is an optional dependency);
* G-DINA / IRT — the deterministic layer must be trusted first;
* the bandit intervention policy — it needs multi-cycle logged outcomes that do not exist.
