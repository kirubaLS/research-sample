# Yaadhum — Technical Team Build Plan

A short briefing: what we are building, in what order, with which tools, and how we beat the five
problems that would otherwise sink it.

---

## 1. The stack — decided, with the reason in one line

| Concern | Choice | Why this one |
|---|---|---|
| **Database** | **PostgreSQL 16** (AWS RDS, `ap-south-1`) | One engine gives us relational integrity, `pgvector` for question embeddings, `ltree` for the syllabus tree, and row-level security for school isolation. No second datastore at pilot scale. |
| **Cache / queue** | **Redis** (ElastiCache) + **arq** | Background extraction jobs. Simpler than Celery, plenty at this volume. |
| **Object storage** | **AWS S3**, SSE-KMS, lifecycle rules (**MinIO** locally) | Page images, mark crops, assembled PDFs. Never in the database. |
| **LLM** | **Claude** — `claude-opus-5` for high stakes, `claude-haiku-4-5` for volume, **Message Batches API** overnight (50% cheaper) | Structured outputs and `strict: true` tools let us force schema-valid, FK-checkable output. Zero training needed to launch. |
| **OCR** | **Not a single product — a layered stack**: OpenCV (geometry, colour, blobs) + PaddleOCR (text detection, printed text) + the LLM for handwritten digits. `pyzbar` for QR. TrOCR fine-tune later. | Generic OCR products fail on "a red number somewhere in the margin". We localise deterministically and only ask a model to read one digit at a time. |
| **Cloud** | **AWS `ap-south-1` (Mumbai)** — ECS Fargate, or one EC2 + Docker Compose for the pilot | Children's data under the DPDP Act must stay in India. One school does not need Kubernetes. |
| **Frontend** | **Next.js 15** + TypeScript + Tailwind + shadcn/ui | Test, scanner and dashboard are one deployable. |
| **Offline / camera** | **Dexie** (IndexedDB) + `getUserMedia` + **OpenCV.js** | School Wi-Fi will fail mid-scan. Capture must work with no network. |
| **Backend** | **FastAPI** (Python 3.12) + SQLAlchemy 2.0 + Alembic + Pydantic v2 | Same language as the CV and analysis layers — no service boundary in the middle of the algorithm. |
| **Analysis** | pandas · NumPy · SciPy · **dbt** → DuckDB (ClickHouse later) | Scoring, Wilson intervals, point-biserial, the solver. |
| **Auth** | Auth.js, roles + Postgres RLS | Students never get an account — a per-class code only. |
| **Observability / CI** | Sentry · OpenTelemetry · GitHub Actions | `run_id` propagated end to end so any number traces back to its source crop. |

**The one architectural rule everybody must know:** *the system has seven layers and exactly one of
them contains a model.* Capture, restoration, colour separation, localisation, association,
reconciliation and reporting are all deterministic OpenCV/SciPy/Python. Only **recognition** calls an
LLM. That is why we can launch on a paid model and later swap in a free one by changing a config
value.

---

## 2. Build order — seven phases

### P0 · Foundation — 2 days
1. Repo, Docker Compose (Postgres + Redis + MinIO), FastAPI + Next.js skeletons, CI.
2. Alembic migration: `school`, `section`, `student_profile`, `taxonomy_node`, `chapter_weight`,
   `assessment`, `question`, `question_skill`, `mark_event`, `data_quality_flag`, `analysis_run`.
3. **`ml_corpus` schema created now, not later** — it must be writing from the first captured page.
4. Auth + `school_id` request context; every query filters on it.

*Done when:* `docker compose up`, `alembic upgrade head`, `GET /health` returns 200 with a live DB ping.

### P1 · Interest test (Use case 1) — 5 days
| Step | Method / algorithm | Library |
|---|---|---|
| Consent + profile form | Schema-shared validation client and server | react-hook-form + Zod / Pydantic |
| 36 bilingual items, 6 screens | Scale-interleaved order, fixed seed per student | next-intl (EN/TA) |
| Autosave + resume | Write on every tap; resume by roll no + class code | Dexie |
| Validity screening | Long-string run, median item time, reverse-keyed pair inconsistency | NumPy |
| Scoring | Raw sums → **ipsative centering** (subtract person mean) → percentile with **empirical-Bayes shrinkage** | NumPy / SciPy |
| Interpretation | Holland top-3 code, **differentiation** D and **consistency** C; flat profile ⇒ *no* stream call | pure Python |
| Stream fit | 6×4 weight matrix as **data, not code** | Postgres table |
| Principal views | Student report, cohort dashboard, PDF | Jinja2 + WeasyPrint |

*Done when:* 40 seeded students score end to end, and a deliberately flat profile correctly withholds
its recommendation.

### P2 · Capture + storage — 5 days
1. Camera component, **quality gate before the shutter unlocks**: blur (variance of Laplacian),
   glare (bright-blob fraction), coverage (quad area), skew (top-edge angle) — all at ~10 fps.
2. Feature 1: single cover-page frame. Feature 2: multi-page scan with **per-page retake that keeps
   the page's position**, reorder, delete, explicit Complete.
3. IndexedDB staging + thumbnails + 24-hour purge.
4. Resumable per-page upload; server assembles a **lossless** PDF (`img2pdf` embeds the original
   JPEG bytes) with metadata (`pikepdf`); **store the page images too**, not only the PDF.
5. QR sticker → student binding, checked against the roster.
6. CSV/Excel import as a secondary path (wide and long shapes, dry-run diff, batch undo).

*Done when:* a teacher scans 15 pages for 5 students on a real phone, offline, without help.

### P3 · Question paper → frozen Q-matrix — 5 days
1. `claude-opus-5` structured extraction: `section, question_no, sub_part, text, max_marks,
   has_diagram, choice_group_id`.
2. **Gate G1** Σ max_marks (respecting *OR* choice groups) == printed total.
   **G2** question sequence complete. **G3** two independent passes agree, field by field.
3. Classification into chapter / sub-topic / R&U-AP-AEC: retrieve nearest validated library
   questions → constrained prompt (only existing taxonomy IDs) → self-consistency k=5 →
   **conformal abstention**.
4. One teacher confirmation screen (~5 min, crop beside each row) → **Q-matrix frozen and versioned**.

*Done when:* a real past paper reconciles to its printed total and is confirmed in under 5 minutes.

### P4 · Mark extraction — 5 days (the core)
| Step | Method / algorithm | Library |
|---|---|---|
| Restore | Corner detect → homography → illumination flattening by division → white balance → deskew | OpenCV |
| **Separate ink** | HSV banding; per-school hue centroids fitted by **k-means (k=3) on ink pixels — unsupervised, 3 pages, no labels** | OpenCV + scikit-learn |
| Anchors | Question labels from the **student** layer; **closed-vocabulary filter** against the frozen Q-matrix | PaddleOCR det + regex |
| Candidates | Isolated/circled numerals from the **teacher** layer; ticks, crosses, strikes excluded by shape; **totals detected separately as extra equations** | OpenCV contours |
| Recognise | `MarkRecognizer.predict(crop, legal_values)` → distribution over the legal values for *that* question | `claude-haiku-4-5` (swap later) |
| Associate | Cost matrix (distance, answer-block containment, side consistency, value plausibility) → **Hungarian algorithm**; then **refit the teacher's own convention and re-solve** | `scipy.optimize.linear_sum_assignment` |
| Reconcile | max Σ log p s.t. grand + section + page totals, 0 ≤ m ≤ max, legal step lattice — **exact DP** | pure Python |
| Route | Calibrated confidence; auto-accept or review queue with the crop; **flag, never guess** | FastAPI + Next.js |

*Done when:* the solver corrects a planted misread, and an unreconcilable script flags instead of
guessing.

### P5 · Analysis + report — 5 days
Marks → chapter / sub-topic / tier through the frozen Q-matrix. Loss with denominators, an
**evidence floor** (under 2 marks ⇒ "insufficient evidence", never a percentage), Wilson intervals,
board-weighted indicator with coverage gaps, paper quality (difficulty, point-biserial, Cronbach's α,
χ² against 54/24/22). Principal report + PDF.

### P6 · Hardening + proof — 5 days
Audit sample and accuracy dashboard, threshold auto-tuning, RLS, consent and retention, load test,
handover.

**First real class through the system: end of P4, about three weeks.**

---

## 3. The challenges, and how we beat each one

| # | Challenge | How we tackle it | Tool |
|---|---|---|---|
| 1 | **Bad photos** ruin everything downstream | Quality gate *before* the shutter unlocks — four metrics at 10 fps. A bad photo costs 5 s here, a wrong report later. | OpenCV.js |
| 2 | **The mark is anywhere** — left, right, above, inside the margin | Never use a fixed region. Anchor-first: find question labels, find mark blobs, then solve the binding as an **assignment problem**. | scipy Hungarian |
| 3 | **Student's own working looks like a mark** | Teacher writes red, student black/blue. Split the page into two masks; the mark detector never sees the student's arithmetic. | OpenCV HSV |
| 4 | **Pen colour varies by school** | Don't hardcode hues. Fit centroids with **k-means on ink pixels from 3 unlabelled pages**; re-fit automatically if confidence drops. | scikit-learn |
| 5 | **Printed red margin rule** lands in the teacher mask | Remove long straight structures first (long thin morphological opening + Hough) before any blob detection. | OpenCV |
| 6 | **Handwritten 1 vs 3** — the most confusable pair | Don't fight it at the recogniser. The **constraint solver** uses the totals the teacher wrote: a wrong digit cannot satisfy the arithmetic. | pure Python DP |
| 7 | **LLM hallucination** | Four independent controls: the model never does arithmetic; output is schema-constrained and FK-validated so it *cannot* invent a chapter; the value enum is the legal marks for that question; two independent passes must agree. | Anthropic SDK structured outputs |
| 8 | **Scripts attributed to the wrong student** | Printed **QR sticker** on the cover, checked against the roster. Never handwritten-name matching. | pyzbar |
| 9 | **School Wi-Fi drops mid-scan** | Whole capture flow is offline-first; pages queue in IndexedDB; resumable per-page upload so a drop at page 14 does not lose 1–13. | Dexie + tus |
| 10 | **We have no training data and no time to train** | Launch on the paid model, log **every** prediction with its full distribution plus every human correction to `ml_corpus`. ~2,400 crops per class per term ⇒ enough to fine-tune the free recogniser within one term. | ml_corpus schema |
| 11 | **CBSE internal choice** ("attempt any one of Q31 or Q32") breaks the marks total | `choice_group_id` in the schema from day one — grouped questions contribute their marks once. Build it now or lose a sprint debugging a gate that was right. | Postgres |
| 12 | **Tier (R&U / AP / AEC) is genuinely ambiguous** | Conformal abstention with a coverage guarantee, then one teacher confirmation. Expect ~3× the abstention rate of chapter — that is correct behaviour, not a defect. | conformal calibration |
| 13 | **Proving accuracy to a principal** | Permanent audit sample: 10% of scripts re-keyed by hand *including confident cells*, error rate published on the dashboard. | dbt + dashboard |
| 14 | **DPDP Act, children's data** | Everything in `ap-south-1`; identity in a restricted schema; only **crops of single digits** cross the training boundary; `consent_class` set at capture time. | AWS + RLS |

---

## 4. Who does what

- **Frontend engineer** — P1 test UI, P2 scanner and quality gate, P4 review queue, P5 dashboards.
- **Backend / CV engineer** — P0 schema, P2 upload and PDF assembly, **P4 layers L1–L6** (the hardest
  and most valuable work in the project).
- **Full-stack / data** — P3 question-paper pipeline and prompts, P5 analysis and reports, P6 audit
  and accuracy dashboard. Owns `ml_corpus` end to end.

Parallelism: P1 and P2 can run side by side after P0. P3 and P4 can run side by side once the
`MarkRecognizer` interface is agreed on day one of P4.

---

## 5. Three rules I want the team to hold

1. **Never pay a model to find a rectangle.** Localisation, geometry, colour and association are
   deterministic code. This is a correctness decision, not a cost one — deterministic code cannot
   hallucinate.
2. **Never overwrite a mark.** `mark_event` is append-only; corrections are new rows. Audit trail,
   OCR-versus-teacher reconciliation and correction history all come free from this one discipline.
3. **Never guess.** If the arithmetic does not reconcile, flag the script. A flagged script costs a
   teacher thirty seconds; a silently wrong one costs the school relationship.

---

## 6. Blocking inputs

1. **Five answer scripts photographed page by page on a teacher's own phone**, in the room where
   scanning will happen. Not flatbed scans. This calibrates the association weights and the ink profile.
2. **Is a total written anywhere on the script** — grand, per-section, per-page, or none? Each one is
   an extra equation in the solver and directly improves accuracy.
3. **Logo files** (SVG + PNG) and brand colours.
4. **Training-consent wording** for the school agreement.
