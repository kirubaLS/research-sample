# Yaadhum — Full Product & Codebase Context

> **Naming note (read this first):** the codebase, its FastAPI `title="Yaadhum"` (see
> `backend/app/main.py:49`), its database, module docstrings, and every identifier
> throughout are named **Yaadhum**. The string "Avai" does not appear anywhere in this
> repository (verified by full-text search across `backend/` and `frontend/`). If the
> business is marketing this product externally as "Avai," that is a rebrand that has not
> reached the code, configuration, `package.json`, `pyproject.toml`, or any user-facing
> string. See §12 for the full flag.

This document is grounded entirely in the repository at `/home/user/research-sample` as it
exists today. Every model, endpoint, and page cited below was read directly from source;
nothing is inferred from naming conventions alone.

---

## 1. Tech Stack

**Backend** (`backend/`)
- **Framework:** FastAPI (`backend/app/main.py`), Python, `from __future__ import annotations` style throughout.
- **ORM:** SQLAlchemy 2.x declarative models (`Mapped[...]`/`mapped_column`) under `backend/app/models/`.
- **Migrations:** Alembic, `backend/migrations/versions/`.
- **DB:** Postgres in production (SQLite for tests/dev — `sqlite+pysqlite` default in `config.py`). A separate `ml_corpus` schema/credential set exists for the ML training-data bridge (`corpus.py`, `corpus_database_url` setting).
- **Object storage:** `backend/app/storage.py` — a `LocalObjectStore` (filesystem, dev-only) behind an `ObjectStore` protocol; an S3-compatible backend is configured via `storage_backend`, `s3_bucket`, `s3_endpoint_url`, `s3_region` (default `ap-south-1`, chosen for India data residency), `s3_access_key_id/secret`. **No S3 lifecycle-rule code exists** — see §12.
- **Background jobs:** No task queue (no Celery/RQ). Long-running work (vision OCR, book ingest, placement classification) is dispatched via FastAPI's `BackgroundTasks`, writing to job tables (`GridSheetJob`, `PaperScanJob`, `PlacementJob`, `IngestJob`) that the frontend polls. This exists specifically to survive Render's reverse-proxy request timeout.
- **LLM/vision providers:** Anthropic (Claude) is the primary classifier/vision provider (`model_high_stakes = "claude-opus-5"`, `model_classifier = "claude-sonnet-5"`, `model_high_volume = "claude-haiku-4-5"`). Gemini (`gemini-3.6-flash`) and Sarvam (Indic OCR) are used for Hindi book OCR since NCERT's Hindi PDFs have a broken/pre-Unicode text layer. Jina (`jina-embeddings-v4`) provides multilingual embeddings for semantic retrieval.
- **PDF rendering:** `fpdf2` (optional — `app/analysis/report_pdf.py`, degrades to 501 if not installed).
- **Rate limiting:** `app/ratelimit.py` (`FixedWindowLimiter`), applied to the public student route and the platform sign-in.
- **Config:** `backend/app/config.py`, pydantic-settings, all env vars prefixed `YAADHUM_` (e.g. `YAADHUM_ANTHROPIC_API_KEY`, `YAADHUM_PLATFORM_ADMIN_KEY`, `YAADHUM_DATABASE_URL`).
- **Testing:** pytest, `backend/tests/` — over 50 test files, heavy on extraction/OCR/ingest correctness, plus API-level tests (`test_api_end_to_end.py`, `test_roles.py`, `test_staff_visibility.py`, `test_platform_api.py`, etc.).

**Frontend** (`frontend/`)
- **Framework:** Next.js App Router (`frontend/app/`), TypeScript.
- **API client:** `frontend/lib/api.ts` — a single hand-written, fully typed client (~1400 lines) wrapping every backend route. No codegen/OpenAPI client; this file is maintained by hand alongside the backend, and is the single most useful place to read the true response shapes.
- **Session/auth storage:** `frontend/lib/session.ts` — plain `localStorage`, separate keys for school-staff credentials (`yaadhum:apiKey`, `yaadhum:role`, `yaadhum:activeSchool`) and the platform operator credential (`yaadhum:platformKey`). No cookies, no server sessions — every authenticated request sends `X-API-Key` (and `X-School-Id` when an admin key needs to say which school) or `X-Platform-Key` read straight from `localStorage`.
- **Styling:** No component library. Hand-built CSS using a custom-property design system in `frontend/app/globals.css` (~830 lines), plus per-page `styled-jsx` blocks. `lucide-react` (icons), `framer-motion` (animation), and `blobs` (decorative vector backgrounds) are recently added, narrowly-scoped dependencies — not a UI kit.
- **Fonts:** Manrope (display), Source Sans 3 (body), JetBrains Mono (mono/code), loaded as CSS custom properties `--font-display` / `--font-body` / `--font-mono`.

---

## 2. Roles & Auth Model

Source of truth: `backend/app/api/deps.py`, confirmed against `backend/app/models/core.py`.

Three credential types, one header scheme:

| Credential | Header(s) | Resolves to | Scope |
|---|---|---|---|
| **School's own legacy API key** (`School.api_key`) | `X-API-Key` | `Staff(role="admin", home=<that School>)` | that one school, admin-equivalent |
| **StaffKey** (`StaffKey.api_key`, `role` ∈ `("principal", "admin")` — `STAFF_ROLES` in `core.py`) | `X-API-Key` (+`X-School-Id` if admin acting cross-school) | `Staff(role=k.role, home=k.school)` | principal: exactly one school (fixed by the key, never overridable by request); admin: any school, named per request |
| **Platform operator key** (`YAADHUM_PLATFORM_ADMIN_KEY`) | `X-Platform-Key`, or `X-API-Key` when equal to it | opens `/platform/*` (school creation, key issuance) | every school; also usable as `Staff(role="admin", home=None)` on the school-facing API |

Dependency functions and what they gate:
- `current_staff` — resolves any of the above to a `Staff` dataclass. Revoked keys 404 identically to nonexistent ones (no oracle).
- `require_staff` — any signed-in staff member; read-only surfaces.
- `require_scanner` — scanning papers, storing scripts, entering marks: **open to both principal and admin** (a deliberate widening — see docstring in `deps.py`). What stays admin-only: the roster and the school itself (superseded later — see below, roster is now `require_scanner` too).
- `require_admin_staff` / `require_admin` — school-mutating actions and "the whole marks engine" (Q-matrix freeze, delete assessment, confirm placement review, revoke keys). A principal gets 403 (not 404 — they are legitimately signed in).
- `require_reader` — any read, scoped to the resolved school.
- `require_platform_admin` — `/platform/*`; only the operator key or an admin `StaffKey` with `school_id IS NULL`.

`GET /admin/me` (`backend/app/api/admin.py`) is the canonical server-computed permission object the frontend trusts — never a role inferred client-side:
```json
{
  "school_id": "...", "name": "...", "board": "CBSE", "state": "Tamil Nadu",
  "training_consent": "operational_only", "role": "principal",
  "scope": "one_school",
  "can": {
    "read_results": true, "scan_papers": true, "enter_marks": true,
    "manage_roster": true, "manage_schools": false
  }
}
```
Note `manage_roster: true` for a principal too — a comment in `admin.py` confirms this was a deliberate widening (`create_student`/`edit_student`/`delete_student` all sit behind `require_scanner`, not `require_admin`). What a principal genuinely cannot do: issue/revoke staff keys, delete an assessment, freeze the Q-matrix's chapter-confirm step (`review/{question_id}` confirm is `require_admin`), post raw marks batches directly (`POST /assessments/{id}/marks` is `require_admin`), or anything under `/platform/*`.

**Students never authenticate.** `POST /t/{class_code}/start` takes only `roll_no`/`name`/etc — the "class code" is literally the `Section.id`, handed out as a link (`/t/{section.id}`) written on a whiteboard, not a secret. No route under `/t/*` (`backend/app/api/interest.py`) ever returns a score, a Holland code or a stream — a docstring states this is deliberate ("The student surface is unauthenticated by design ... and it is a dead end: no route here returns a score").

**Frontend mismatch to flag:** `frontend/lib/session.ts`'s `StaffRole` interface omits `manage_roster` in its TS comment example but the actual type includes it correctly — verified consistent with `api.ts`'s `whoami` return type (`can: {read_results, scan_papers, enter_marks, manage_roster, manage_schools}`).

---

## 3. Database Schema (exhaustive)

All tables below use `PkMixin` (a string `id` primary key — likely UUID/ULID, see `backend/app/models/base.py`) and, unless noted, `TimestampMixin` (`created_at`, presumably `updated_at`). File paths given per table.

### 3.1 Tenancy & roster — `backend/app/models/core.py`

**`school`**
- `name: String(200)`
- `board: String(32)` default `"CBSE"`
- `state: String(64) | None` default `"Tamil Nadu"`
- `api_key: String(64)` unique, indexed — the legacy per-school admin key
- `ink_profile: String(2000) | None` — per-school fitted HSV centroids for teacher/student ink (referenced but not deeply used in the routers read)
- `training_consent: String(32)` default `"operational_only"` — validated values (only enforced in `platform.py`'s Pydantic model, not a DB constraint): `"operational_only" | "improve_models" | "research"`

**`staff_key`**
- `school_id: FK(school.id) | None` — null only for admin keys ("belongs to no school")
- `api_key: String(64)` unique, indexed
- `role: String(16)` default `"principal"` — `STAFF_ROLES = ("principal", "admin")`
- `label: String(120)` default `""`
- `revoked_at: DateTime | None`

**`section`**
- `school_id: FK(school.id)`, `grade: Integer` default `10`, `name: String(8)` default `"A"`
- unique `(school_id, grade, name)`

**`student_profile`**
- `school_id: FK`, `section_id: FK`
- `name: String(200)`, `roll_no: String(16)`
- `age: Integer | None`, `gender: String(16) | None`, `dob: Date | None`
- `consent_ref: String(120) | None`
- unique `(section_id, roll_no)`
- docstring: "Restricted schema. Analytics joins on id only, never on name."

### 3.2 Assessment & Q-matrix — `backend/app/models/assessment.py`

**`assessment`**
- `school_id: FK`, `subject_code: String(32)`, `curriculum_version: String(32)` default `"CBSE-2026-27"`
- `title: String(200)`, `paper_code: String(32) | None` (e.g. `'30(B)'`, `'2/7/3'`)
- `total_marks: Numeric(6,2) | None`
- `paper_kind: String(16)` default `"school"` — `PAPER_KINDS = ("school", "board", "sample")`
- `exam_year: Integer | None` (required by app logic when `paper_kind != "school"`)
- Discovery fields (set at ingest): `source_sha256`, `pdf_page_count`, `logical_page_count`, `imposition: Integer` default `1` (1/2/4-up), `rotation: Integer` default `0` (0/90/180/270), `languages: JSON | None`, `route: String(16)` default `"vision"` (`"vision"|"text"`)
- `declared: JSON | None` — what the paper itself claims (sections, question_count, total_marks)
- `syllabus_scope: JSON | None` — declared chapter codes this test covers (set via `PUT /assessments/{id}/scope`)
- `status: String(24)` default `"ingested"` (progresses through `verified`/`blocked`/`frozen` etc.)
- `qmatrix_frozen_at: String(40) | None`, `qmatrix_version: Integer` default `0`
- `scan_confirmed_at: String(40) | None`, `scan_confirmed_by: String(64) | None`

**`logical_page`** — one real page of the paper after de-imposition: `assessment_id FK`, `index`, `source_pdf_page`, `tile_bbox: JSON | None`, `language: String(8)` default `"en"`, `is_canonical: bool` default `True`, `image_uri: String(500) | None`. Unique `(assessment_id, index)`.

**`question`** — the frozen Q-matrix row, one per address (`section/question_no/sub_part/choice_alt`):
- `assessment_id FK`, `address: String(40)` indexed, `section/question_no/sub_part/choice_alt: String`, `choice_group_id: String(36) | None`
- `max_marks: Numeric(5,2)`, `mark_step: Numeric(3,2)` default `1.0`, `question_type: String(24) | None`
- `stem_text: String(4000) | None`, `stem_hash: String(64) | None`, `logical_page: Integer | None`, `bbox: JSON | None`
- Layer 1 (curriculum): `board_unit_id: FK(taxonomy_node.id)` (**not nullable**), `chapter_id: FK | None`, `curriculum_section: String(32) | None`, `curriculum_section_title: String(200) | None`, `verified_against: String(120) | None`, `verified_at: String(40) | None`
- `concept_family_id: FK(taxonomy_node.id)` (**not nullable**), `concept_variant: String(200)`, `variant_hash: String(64)`
- Layer 2B (judgment; requires two-reviewer agreement gate): `skill_required: String(200) | None`, `complexity: String(16) | None` (`SINGLE_STEP|MULTI_STEP|NOT_APPLICABLE`), `dependency_level: String(16) | None` (`SINGLE_CONCEPT|MULTI_CONCEPT`)
- DB check constraint: `(chapter_id IS NULL) = (curriculum_section IS NULL)` — the "conditional-chapter rule"
- Unique `(assessment_id, address)`
- **Difficulty is deliberately NOT a column** — it's derived analytically from cross-school performance (`app/analysis/difficulty.py`), never tagged.

**`scanned_question`** — pre-mapping staging table, what the paper literally printed, before any curriculum knowledge is attached: `assessment_id`, `address`, `section/question_no/sub_part/choice_alt`, `max_marks: Numeric | None` (nullable, unlike `question`), `stem_text`, `logical_page`, `question_id: FK(question.id) | None` (set once promoted), `blocked_reason: String(500) | None`, `edited_at/edited_by`. Unique `(assessment_id, address)`.

**`question_skill`** — the multi-skill Q-matrix join: `question_id FK`, `node_id FK(taxonomy_node)`, `weight: Float` default `1.0`, `source: String(24)` default `"model"`, `confidence: Float | None`. Unique `(question_id, node_id)`.

**`question_tier`** — append-only cognitive-tier decisions: `question_id FK`, `tier: String(8) | None` (short code, `None`=abstained), `action_class`, `familiarity: Float | None`, `familiarity_bucket: String(1) | None`, `signals: JSON | None`, `conformal_set: JSON | None`, `confidence: Float | None`, `source: String(24)` default `"ensemble"` (`ensemble|human|library`), `model_version`, `rationale: String(2000) | None`.

**`question_placement`** — append-only placement history (current = latest row): `question_id FK`, `chapter_id FK | None`, `board_unit_id FK | None`, `curriculum_section`, `tier: String(48) | None`, `skill_required`, `confidence: Float | None`, `source: String(16)` default `"model"` (`model|blueprint|scope|human`), `needs_review: bool` default `False`, `reviewed_by`, `reasoning: String(1000) | None`, `evidence: JSON | None` (chunk refs), `candidates: JSON | None` (runner-up chapters).

**`question_judgment`** — Layer 2B review trail (append-only, 2+ reviewers required): `question_id FK`, `field: String(24)` (`JUDGMENT_FIELDS = ("skill_required","complexity","dependency_level")`), `value: String(200)`, `reviewer_id`, `is_resolution: bool` default `False`, `note: String(1000) | None`.

**`data_quality_flag`** — verification-gate failures: `assessment_id FK`, `student_id FK | None`, `rule: String(64)`, `severity: String(16)` default `"blocking"`, `detail: String(1000)`, `status: String(16)` default `"open"`.

**`analysis_run`** — `assessment_id FK`, `code_version`, `taxonomy_version`, `model_versions: JSON | None`.

Constants: `TIERS = ("Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating")`, `TIER_ALIASES` mapping to `R&U`/`AP`/`AEC`, `CBSE_TIER_TARGET` (0.54/0.24/0.22 mark-share targets).

### 3.3 Scanned documents, marks, reports — `backend/app/models/documents.py`, `marks.py`

`DOCUMENT_KINDS = ("question_paper", "answer_sheet", "mark_grid")`

**`scan_document`**: `school_id`, `assessment_id`, `student_id: FK | None` (null for question papers/mark grids), `kind`, `page_count`, `sha256: String(64)` indexed, `uploaded_by`, `confirmed_at/confirmed_by`.

**`scan_page`**: `document_id FK CASCADE`, `index`, `content_type` default `"image/jpeg"`, `byte_size`, `quality: JSON | None`, `storage_key: String(255) | None` (S3 key — see §12), `content: LargeBinary | None` (legacy fallback for rows written before object storage existed). Unique `(document_id, index)`.

**`student_report`** — a frozen, issued report: `school_id`, `assessment_id`, `student_id`, `issued_by`, `sha256` (over payload), `earned/available: Numeric(7,2)`, `payload: JSON` (the **entire** report body — never a summary).

**`proposed_mark`** — the staging table for a mark read out of any file, before human confirmation: `school_id`, `assessment_id`, `student_id`, `address: String(64)`, `marks: Numeric(6,2) | None`, `state: String(16)` default `"awarded"`, `source_kind: String(24)` default `"file"` (also `ocr`, `ocr_grid`, `person`), `source_name`, `origin: String(200)` (cell reference, e.g. "row 12, column Q4"), `raw_value: String(64)`, `problem: String(300) | None`, `edited_by`. Unique `(assessment_id, student_id, address)`.

**`grid_sheet_row`** — one student's row on a class mark-entry sheet before resolution to a real student: `school_id`, `assessment_id`, `section_id`, `document_id FK CASCADE`, `roll_no`, `name_as_written`, `student_id: FK | None`, `status: String(16)` default `"unmatched"` (`GRID_ROW_STATUSES = ("unmatched", "name_mismatch", "clean")`), `cells: JSON` (list of `{question_label, raw_value}`), `note`, `suggested_student_id: FK | None`. Unique `(document_id, roll_no)`.

**`grid_sheet_job`** — async job for vision-reading a grid sheet: `school_id`, `assessment_id`, `section_id`, `document_id`, `kind: String(16)` default `"class_photo"` (`GRID_JOB_KINDS = ("class_photo", "single_script")`), `status: String(16)` default `"pending"`, `result: JSON | None`, `error_status/error_detail`, `finished_at`.

**`paper_scan_job`** — async job for reading a scanned/photographed question paper: `school_id`, `assessment_id`, `pdf_bytes: LargeBinary`, `status`, `result: JSON | None`, `error_status/error_detail`, `finished_at`.

**`placement_job`** — async job for classifying every question in a paper: `school_id`, `assessment_id`, `status`, `result: JSON | None`, `error_status/error_detail`, `finished_at`.

**`mark_event`** (`marks.py`) — append-only ground truth: `assessment_id`, `student_id`, `question_id`, `state: String(16)` default `"awarded"` (`MARK_STATES = ("awarded", "absent", "not_offered")`), `marks: Numeric(5,2) | None`, `source: String(16)` indexed (`SOURCE_PRECEDENCE = ("page_ocr", "cover_ocr", "csv", "teacher")` — teacher always wins), `confidence: Float` default `1.0`, `actor_id: String(36) | None`, `model_version`, `provenance: JSON | None` (`{page_id, bbox, crop_uri, row_ref}`), `superseded: bool` default `False`.

### 3.4 Curriculum taxonomy — `backend/app/models/taxonomy.py` (SCD-2, versioned, never hard-deleted)

`NODE_KINDS = ("board", "subject", "grade", "board_unit", "chapter", "subtopic", "concept_family", "skill", "qtype", "tier")` — note `board_unit` is a **sibling** of `chapter`, not a parent (CBSE weightage units can span or omit chapters).

**`taxonomy_node`**: `kind`, `code: String(80)` indexed (e.g. `'X.MATH.REAL.IRRATIONAL'`), `label`, `label_i18n: JSON | None`, `parent_id: FK | None`, `path: String(500)` (materialised path), `curriculum_version` default `"CBSE-2026-27"`, `valid_from/valid_to: Date | None`. Unique `(curriculum_version, code)`.

**`taxonomy_alias`**: `node_id FK`, `alias: String(200)`, `locale` default `"en"`.

**`prerequisite`**: `node_id FK`, `requires_id FK`, `strength: Float` default `1.0`. **Deferred/unused in V1** — table exists, nothing in the reporting path reads it (per docstring).

**`board_unit_weight`**: `curriculum_version`, `board_unit_id FK`, `weight_pct: Numeric(5,2)`, `source_doc_url: String(500) | None`. Unique `(curriculum_version, board_unit_id)`.

**`chapter_board_unit`**: explicit chapter→board-unit mapping (not inferred from tree walk): `curriculum_version`, `chapter_id FK`, `board_unit_id FK`. Unique `(curriculum_version, chapter_id)`.

**`canonical_procedure`** — the "taught-verbatim" set (Bucket T), extracted from NCERT's own labelled theorems/examples: `curriculum_version`, `subject_code`, `chapter_id/subtopic_id: FK | None`, `name` (e.g. "Irrationality of root 5"), `reference` (e.g. "Theorem 1.3"), `canonical_stem: Text`, `stem_hash`, `taught_verbatim: bool` default `True`, `aliases: JSON | None`.

**`book_chunk`** — textbook content split into familiarity buckets: `curriculum_version`, `subject_code`, `node_id: FK | None`, `bucket: String(1)` (`'T'`=taught content, `'E'`=exercise practice), `reference: String(80) | None` (e.g. "Ex 1.2 Q1"), `section_number: String(16) | None` (e.g. "12.2"), `text: Text` (unbounded — a real exercise runs to 8500 chars), `normalised: Text`, `stem_hash`, `embedding: JSON | None` (pgvector in production).

**`concept_family_proposal`** — a proposed concept family, kept whether applied or not (for cost/explicability/rejection-evidence reasons): `curriculum_version`, `subject_code`, `run_id: String(36)`, `source: String(16)` default `"llm"` (`sections|llm`), `model`, `code`, `label`, `chapter_id: FK | None`, `rationale: String(2000) | None`, `evidence: JSON | None`, `from_sections: JSON | None`, `applied_at: String(40) | None`. Unique `(curriculum_version, subject_code, run_id, code)`.

**`book_source`** — what was uploaded for a subject, and the TOC it must agree with: `curriculum_version`, `subject_code`, `edition: String(120) | None`, `expected_sections: JSON` (`{chapter_number: [{number, title}]}`), `expected_chapters: JSON` (`{chapter_number: title}` — used for subjects whose contents page has no section list), `files: JSON` (`{filename: {sha256, chunks, loaded_at}}`). Unique `(curriculum_version, subject_code)`.

**`ingest_job`** — async book-upload job (used for the Hindi OCR path only): `subject_code`, `curriculum_version`, `kind: String(16)` (`contents|chapter`), `filename`, `edition: String(120) | None`, `pdf_bytes: LargeBinary`, `status`, `result: JSON | None`, `error_status/error_detail`, `finished_at`.

**`family_board_frequency`** — materialised: how often/consistently a concept family has appeared on real board papers: `curriculum_version`, `subject_code`, `stream: String(16)` default `"standard"` (`standard|basic`, Maths only splits streams), `concept_family_id FK`, `window_years: JSON` (e.g. `[2021..2025]`), `years_eligible/years_appeared: Integer`, `marks_by_year: JSON`, `marks_range: Float | None`, `base_multiplier/multiplier: Float`, `adjustments: JSON`, `eligibility: JSON | None`, `sets_disagree: JSON | None`, `papers_used: Integer`, `config_version: String(16)`, `computed_at: String(40)`. Unique `(curriculum_version, stream, concept_family_id)`.

**`syllabus_version`** — what an older syllabus did NOT contain (a diff, not a full copy): `curriculum_version`, `subject_code`, `excluded_families: JSON`, `source_doc_url: String(500) | None`, `seeded_at: String(40)`. Unique `(curriculum_version, subject_code)`.

### 3.5 Psychometric interest test — `backend/app/models/psychometric.py` (RIASEC)

**`test_session`**: `school_id`, `student_id`, `instrument_version` default `"riasec-36-v1"`, `locale` default `"en"`, `item_order: JSON | None` (fixed random seed, auditable), `started_at/completed_at: DateTime | None`, `validity: String(16)` default `"pending"` (`valid|suspect|invalid`), `validity_detail: JSON | None`.

**`item_response`**: `session_id FK`, `item_id: String(16)`, `value: Integer` (1–5 Likert), `shown_at/answered_at: DateTime | None` — docstring: "the entire validity layer. They cannot be added later."

**`scale_score`**: `session_id FK`, `scale: String(1)` (R/I/A/S/E/C), `raw`, `centered`, `percentile`, `ci_low`, `ci_high: Float`.

**`profile_result`**: `session_id FK` (unique), `holland_code: String(3) | None`, `differentiation: Float | None`, `consistency: Integer | None`, `stream_fit: JSON | None`, `recommendation_withheld: bool` default `False`, `withheld_reason: String(200) | None`.

### 3.6 `ml_corpus` — separate schema, ML training bridge — `backend/app/models/corpus.py`

Docstring: "the bridge from a paid launch to a free recogniser." Five design rules: every prediction stored (incl. auto-accepted), full distribution stored (not argmax), append-only, `time_taken_ms` on every human label, `consent_class` fixed at capture time.

- **`ml_capture_asset`**: `school_id`, `assessment_id/student_ref` (pseudonymous), `page_index`, `storage_uri`, `sha256`, `device_hint`, `quality: JSON | None`, `ink_profile: JSON | None`, `consent_class: String(32)` default `"operational_only"`.
- **`ml_crop`**: `asset_id`, `kind: String(16)` (`mark|anchor|cell|total`), `layer: String(16)` (`teacher|student|printed`), `bbox: JSON`, `preproc_ver`, `storage_uri: String(500) | None`.
- **`ml_prediction`**: `crop_id`, `backend`, `model_version`, `distribution: JSON` (full, not argmax), `argmax: String(16) | None`, `confidence/calibrated: Float | None`, `latency_ms/cost_micros: Integer | None`, `auto_accepted: bool` default `False`.
- **`ml_human_label`**: `crop_id`, `value: String(16)`, `labeler_id`, `mode: String(16)` (`review|audit|adjudication`), `time_taken_ms: Integer | None`.
- **`ml_disagreement`**: `crop_id`, `source_a/value_a`, `source_b/value_b`, `resolved/resolved_by: String | None`.

This table set is **not wired into any router read in this pass** (no `/corpus` or `/ml` routes were found in `backend/app/api/`) — it appears to be schema-only infrastructure awaiting a producer pipeline. Confirm with a full grep of `backend/app/` before relying on it being live.

---

## 4. API Inventory (by router file)

All routes require `X-API-Key` unless noted. Response shapes are the literal dict/Pydantic-model keys from the route bodies — field names are exact.

### `backend/app/api/admin.py` (`prefix=/admin`)
- `GET /admin/me` → `{school_id, name, board, state, training_consent, role, scope, can:{read_results, scan_papers, enter_marks, manage_roster, manage_schools}}` — `require_staff`
- `GET /admin/staff` → `[{id, role, label, created_at, revoked_at}]` — `require_reader`
- `GET /admin/overview` → `{school:{id,name,state}, sections:[{section_id,label,grade,name,student_path,students,completed,flagged}], totals:{students,completed,flagged}, assessments:[{id,title,paper_code,subject_code,status,total_marks,frozen}]}` — `require_reader`
- `GET /admin/dashboard` → `{school, counts:{students,classes,papers,papers_read,question_papers_stored,scripts_stored,reports_issued,questions_total,questions_mapped}, papers:[...top 6...], students:[...top 6 by papers_marked...], recent_scripts:[...top 5...]}` — `require_reader`
- `GET /admin/sections/{section_id}/students` → roster with interest-test status, `holland_code`, `top_stream`, `papers_marked` per student — `require_reader`
- `POST /admin/sections/{section_id}/students` (201) → `{student_id, name, roll_no}` — `require_scanner` (principal-allowed)
- `PATCH /admin/students/{student_id}` → `{student_id, changed:[...]}` — `require_scanner`
- `DELETE /admin/students/{student_id}` (204) — hard delete cascading to `TestSession/ItemResponse/ScaleScore/ProfileResult/MarkEvent/StudentReport/ProposedMark/DataQualityFlag/ScanDocument` — `require_scanner`
- `GET /admin/cohort/{section_id}` → `{holland:{R:n,...}, streams:{...}, counted, withheld}` — `require_reader`
- `GET /admin/subjects` → `{subjects:[{subject_code,label,grade,chapters,board_units,book_loaded,chunks,chunks_embedded}]}` — `current_staff` (any staff, not school-scoped)

### `backend/app/api/marks.py` (`prefix=/assessments`)
- `POST /assessments` → `{assessment_id, status}` — `require_scanner`
- `GET /assessments` → `{assessments:[{id,title,subject_code,paper_code,total_marks,created_at,stage,scanned_questions,questions,mapped_questions,students_with_marks,ready_for_answer_sheets}]}` — `require_reader`
- `PATCH /assessments/{id}` → rename/correct metadata (refused once `scan_confirmed_at` set) — `require_scanner`
- `DELETE /assessments/{id}` (204) — hard delete of everything under the paper — `require_admin`
- `POST /assessments/{id}/questions` → import a Q-matrix directly (variant-reuse guarded) → `{created, total_addresses, choice_groups}` — `require_admin`
- `POST /assessments/{id}/verify` → the "four gates" data-quality check → verification report dict — `require_admin`
- `POST /assessments/{id}/freeze` → `{frozen_at, version}` — `require_admin`
- `POST /assessments/{id}/marks` → raw batch mark write → `{written, rejected:[...]}` — `require_admin`
- `POST /assessments/{id}/reconcile` → constraint-solver over per-question probability distributions → `{feasible, assignment, mean_logp, failed_constraint, detail}` — `require_admin`
- `POST /assessments/{id}/scan` (201 or 202) — upload a question paper (PDF or photos); text-layer PDFs return synchronously, scanned/photographed papers **queue a `PaperScanJob` and return 202** `{job_id, status:"pending", next}` — `require_scanner`
- `GET /assessments/{id}/scan/jobs/{job_id}` — poll — `require_scanner`
- `GET /assessments/{id}/scan` → staged questions + mapping/tier/review state — `require_reader`
- `PATCH /assessments/{id}/scan/{address}` → correct a staged (unconfirmed) question — `require_scanner`
- `POST /assessments/{id}/scan/confirm` → human confirms the extraction (blocked if marks don't sum to declared total) → `{assessment_id, confirmed_at, confirmed_by, questions, edited, total_marks, next}` — `require_scanner`
- `POST /assessments/{id}/map` → place staged questions against the loaded book (lexical/hybrid retrieval) → `{assessment_id, retrieval, mapped, board_frequency, blocked, context_stems, with_topic, blocked_addresses, needs_review, next}` — `require_scanner`
- `GET /assessments/{id}/answers/{student_id}` → per-question sheet with current marks — `require_reader`
- `POST /assessments/{id}/answers/{student_id}/confirm` → write `MarkEvent`s as `source="teacher"` → `{written, rejected, scored, available, remaining, complete}` — `require_scanner`

### `backend/app/api/reading.py` (`prefix=/assessments`) — file/OCR-based mark reading (3-step: read→review→confirm)
- `POST /assessments/{id}/answers/{student_id}/read` (201) → parse a file (spreadsheet/CSV/PDF/photos) into `ProposedMark` rows, nothing counted yet → `{read, unmatched, questions_on_paper, rolls_in_file, problems, source, used_ocr, note, next}` — `require_scanner`
- `GET /assessments/{id}/answers/{student_id}/reading` → review proposals → `{assessment, student, questions:[...], read, missing, blocked, can_confirm}` — `require_scanner`
- `PATCH /assessments/{id}/answers/{student_id}/reading/{address}` → correct one proposal — `require_scanner`
- `POST /assessments/{id}/answers/{student_id}/reading/confirm` → turn proposals into `MarkEvent`s → `{written, confirmed_by}` — `require_scanner`
- `POST /assessments/{id}/sections/{section_id}/reading/confirm-class` → confirm every clean student's reading in one call → `{confirmed:[...], skipped:[...], confirmed_by}` — `require_scanner`

### `backend/app/api/gridsheets.py` (`prefix=/assessments`) — class-photo mark entry (4-step: upload→review→resolve→confirm)
- `POST /assessments/{id}/sections/{section_id}/gridsheet` (202) — whole-class photo, vision job → `{job_id, status, document_id, next}` — `require_scanner`
- `POST /assessments/{id}/sections/{section_id}/script` (202) — one student's own script photo — `require_scanner`
- `GET /assessments/{id}/gridsheet/jobs/{job_id}` — poll — `require_scanner`
- `GET /assessments/{id}/gridsheet/{document_id}` → every row + `can_confirm` — `require_scanner`
- `POST /assessments/{id}/gridsheet/{document_id}/rows/{row_id}/resolve` → point unmatched/mismatched row at a student (existing/create/accept-suggestion) → `{row_id, student_id, status}` — `require_scanner`
- `POST /assessments/{id}/gridsheet/{document_id}/confirm` → confirm all clean rows → `{confirmed:[...], skipped:[...], confirmed_by}` — `require_scanner`
- `POST /assessments/{id}/sections/{section_id}/gridsheet/file` (201) — spreadsheet/text-PDF naming several students, synchronous (no vision call) — `require_scanner`

### `backend/app/api/placement.py` (`prefix=/assessments`) — LLM chapter/tier classification
- `PUT /assessments/{id}/scope` → declare which chapters a test covers → `{assessment_id, scope, chapters}` — `require_admin`
- `POST /assessments/{id}/place` (202) → queue the classifier (Anthropic judge) over every question → `{job_id, status, next}` — `require_scanner`
- `GET /assessments/{id}/place/jobs/{job_id}` — poll; result includes `spend:{model,effort,calls,input_tokens,output_tokens,...}`, `grounding_violations`, `scope_source` — `require_scanner`
- `GET /assessments/{id}/review` → questions still needing human review, sorted by ascending confidence → `{assessment_id, total_placed, pending, questions:[...], chapters:[...]}` — `require_reader`
- `POST /assessments/{id}/review/{question_id}` → human settles chapter/section/tier → `{question_id, chapter, remaining}` — `require_admin`

### `backend/app/api/board.py` — board-paper registry & frequency/urgency table
- `POST /board-papers` (201) → register a real CBSE board/sample paper (then it walks the normal scan→confirm→map pipeline) — `require_scanner`
- `GET /board-papers` → every board/sample paper across **all schools** (shared evidence pool) — `require_reader`
- `POST /board-frequency/recompute` → manual rebuild of the frequency table — `require_scanner`
- `GET /board-frequency` → per-family multiplier/urgency with full evidence (`marks_by_year`, `adjustments`, `eligibility`, config) — `require_reader`

### `backend/app/api/reports.py` (`prefix=/reports`) — "principal-only reporting"
- `GET /reports/cohort/{assessment_id}` → class-level report: `band_counts/band_pct`, `section_bars`, `subject_bars` (+ `subject_bars_note` disclaiming the "shared test occasion" concept doesn't exist in-schema), `top_losses` — `require_reader`
- `GET /reports/student/{student_id}/assessments` → papers this student has marks for — `require_reader`
- `GET /reports/student/{student_id}?assessment_id=...` → the full diagnosis: `total`, `topic_axis`, `topics`, `strengths`, `focus` (board-urgency-ranked), `tier_summary`, `findings`, `all_crosstab`, `board_weighted_indicators`, `coverage_gaps`, `board_urgency`, `not_offered` — every finding carries a `proof` object down to `mark_source`/`placement.reasoning`/`book_evidence` — `require_reader`
- `POST /reports/student/{student_id}/issue` → freeze the current diagnosis as a `StudentReport` — `require_reader` (deliberately — a principal issuing a report is allowed even though nothing else they do writes marks)
- `GET /reports/student/{student_id}/issued` → list issued reports — `require_reader`
- `GET /reports/issued/{report_id}` → a frozen report, never recomputed — `require_reader`
- `GET /reports/issued/{report_id}/pdf` → the same, as a generated PDF (fpdf2; 501 if not installed) — `require_reader`
- `GET /reports/paper/{assessment_id}` → item analysis, Cronbach's alpha, typology alignment, `diagnostic_strength` — `require_reader`
- `GET /reports/interest/{student_id}` → RIASEC profile — **principal/admin only, never on a student route** — `require_reader`

### `backend/app/api/interest.py` (`prefix=/t`) — unauthenticated student surface
- `GET /t/classes` → public class directory `[{class_code, label, grade, school}]`
- `POST /t/{class_code}/start` → self-register/resume, rate-limited per IP → `SessionOut{session_id, locale, total_items, screens}`
- `POST /t/session/{id}/responses` → idempotent per-item save → `{saved, answered, total_items}`
- `POST /t/session/{id}/complete` → score, but **never return** the score → `CompletionOut{message, submitted}`

### `backend/app/api/platform.py` (`prefix=/platform`, all behind `require_platform_admin`)
- `GET /platform/me` → `{role:"platform_admin"}` (rate-limited sign-in check)
- `GET /platform/schools` → all schools, never carrying `api_key`
- `GET /platform/overview` → every school's counts in one call (students, papers, answer_scripts, reports_issued, admin_keys, principal_keys) + `cross_school_admin_keys`
- `POST /platform/schools` (201) → create school + sections + its admin key, **shown once**
- `POST /platform/schools/{id}/sections` (201)
- `GET /platform/keys` / `POST /platform/keys` (admin keys, school_id=None) / `POST /platform/keys/{id}/revoke`
- `GET /platform/schools/{id}/keys` / `POST /platform/schools/{id}/keys` (issue principal or admin key for a school) / `POST /platform/schools/{id}/keys/{id}/revoke`
- `POST /platform/schools/{id}/rotate-key` — immediate, total; old key stops working

### `backend/app/api/books.py` (`prefix=/platform/books`, behind `require_platform_admin`) — curriculum/RAG book ingest
- `POST /{subject}/curriculum` — seed board units/weightage/chapters from `CURRICULA` (or record an older syllabus's exclusions)
- `GET /{subject}` — ingest status: `contents_uploaded`, `expected_chapters`, `loaded_chapters`, `missing_chapters`, `chunks/embedded`, per-chapter `coverage`
- `POST /{subject}/contents` (201 or 202 for Hindi) — the prelims/TOC file, becomes the verification oracle
- `POST /{subject}/chapters` (201 or 202 for Hindi) — one chapter, verified against TOC before writing anything
- `GET /{subject}/jobs/{job_id}` — poll Hindi OCR ingest jobs
- `POST /{subject}/probe` → push real exam questions through retrieval to sanity-check the loaded book → hit rate, per-question `familiarity` classification, `runners_up`
- `GET /{subject}/concept-families` → proposed families (from stored LLM run + section-heading fallback), flagging `possible_duplicates`/`without_a_section`
- `POST /{subject}/concept-families` (201) → create reviewed families (additive-only, never renames)
- `GET /{subject}/concept-families/audit` / `POST /audit/apply` — find/remove wrong-subject or empty-code families
- `POST /{subject}/concept-families/merge` — fold duplicate families into a survivor, re-pointing every `Question`/`QuestionPlacement`/proposal
- `GET /audit` (all subjects) / `POST /audit/apply` (all subjects)
- (Truncated in this pass past line ~1390 of a 1774-line file — `propose-llm` and `/embed` endpoints referenced by `frontend/lib/api.ts` — `proposeFamiliesWithModel`, `embedBatch` — exist further in the file; not fully re-verified line-by-line here.)

### `backend/app/api/documents.py`, `upload.py`, `matching.py`, `schemas.py`
Not fully re-read line-by-line in this pass; `documents.py` supplies `store_document`/`content_type_for`/`read_page_bytes` helpers used throughout the routers above, plus (per `main.py` router registration and `api.ts`'s `deleteDocument`/`pageBlob`/`studentDocuments` calls) `DELETE /documents/{id}`, `GET /documents/{id}/pages/{index}`, `GET /students/{id}/documents`. `upload.py` supplies `pages_to_pdf`/`to_tempfile`/`IMAGE_SUFFIXES`. `matching.py` supplies `match_address`. `schemas.py` holds the shared Pydantic request models (`AssessmentIn`, `QuestionBatchIn`, `MarkBatchIn`, `ReconcileIn`, `StudentCreateIn`, `StudentUpdateIn`, `ProfileIn`, `ResponseBatchIn`, `SessionOut`, `CompletionOut`).

---

## 5. End-to-End Flows

### 5.1 Student interest-test flow (unauthenticated, "use case 1")
1. Student opens `/t` → `GET /t/classes` lists every section across every school.
2. Picks a class → `/t/[classCode]` → enters name/roll → `POST /t/{class_code}/start` (rate-limited per IP). Server finds-or-creates the `StudentProfile`, resumes an in-progress `TestSession` by `(student_id)` or starts a new one with a fixed random seed for item order.
3. `/t/[classCode]/test` renders `screens` (grouped Likert items) from the response; `POST /t/session/{id}/responses` saves each answer immediately (idempotent per item, with `shown_at`/`answered_at` timestamps feeding the validity screen).
4. `POST /t/session/{id}/complete` scores the RIASEC instrument, runs a validity screen (`valid|suspect|invalid`), writes `ScaleScore`×6 and one `ProfileResult` (unless invalid) — but returns **only** a thank-you message and count. Student lands on `/t/thanks`.
5. Staff later see the result via `GET /admin/sections/{id}/students` (roster status) or `GET /reports/interest/{student_id}` (full RIASEC profile) — never the student themselves.

### 5.2 Paper ingest → mark entry → report flow ("use case 2")
1. **Book must be loaded first** (operator, `/platform/books/*`): curriculum seeded → contents/TOC uploaded → chapters uploaded (verified against TOC) → concept families proposed and created → optionally embedded for semantic retrieval.
2. **Create an assessment**: `POST /assessments`.
3. **Scan the paper**: `POST /assessments/{id}/scan` — text-layer PDF returns synchronously; a photo/scan queues a `PaperScanJob`, polled via `GET .../scan/jobs/{job_id}`. Writes `ScannedQuestion` rows (not yet `Question`).
4. **Review & edit staged questions**: `GET /assessments/{id}/scan`, `PATCH .../scan/{address}` for corrections.
5. **Confirm**: `POST /assessments/{id}/scan/confirm` — a human puts their name to the extraction; blocked if any mark is missing or the sum disagrees with the declared total.
6. **Map to the book**: `POST /assessments/{id}/map` — lexical/hybrid retrieval places each staged question against a chapter+board-unit+concept-family, promoting `ScannedQuestion → Question`. Optionally, **place**: `POST /assessments/{id}/place` (202, background) runs the Anthropic judge per question for a higher-confidence chapter/tier/skill read, writing append-only `QuestionPlacement`/`QuestionTier` rows.
7. **Human review of low-confidence placements**: `GET /assessments/{id}/review` → `POST /assessments/{id}/review/{question_id}` to settle.
8. **Verify/freeze** (optional/admin): `POST /assessments/{id}/verify` (four-gate arithmetic check) → `POST /assessments/{id}/freeze` (locks the Q-matrix).
9. **Mark entry** — three independent paths, all converging on `MarkEvent`:
   - Per-student answer sheet: `GET/POST /assessments/{id}/answers/{student_id}` (+ `/confirm`).
   - File/OCR read for one student: `POST .../read` → `GET .../reading` → `PATCH` corrections → `POST .../reading/confirm` (or class-wide `confirm-class`).
   - Class-photo grid sheet: `POST .../gridsheet` (202, vision job) → `GET .../gridsheet/{document_id}` review → `POST .../rows/{row_id}/resolve` for unmatched/mismatched rolls → `POST .../gridsheet/{document_id}/confirm`.
10. **Reports**: `GET /reports/student/{id}?assessment_id=...` (live, regenerable diagnosis) → `POST /reports/student/{id}/issue` (freezes it) → `GET /reports/issued/{id}` or `/pdf` (never recomputed once issued). Class-level: `GET /reports/cohort/{assessment_id}`. Paper-level psychometrics: `GET /reports/paper/{assessment_id}`.

### 5.3 Board-paper evidence flow (feeds "board urgency")
`POST /board-papers` registers a real CBSE exam paper (year/set/stream), then it walks the **identical** scan→confirm→map pipeline as any school test. Once mapped, `FamilyBoardFrequency` is rebuilt automatically (or via `POST /board-frequency/recompute`), and every student report's `focus`/`findings` ranking incorporates `board_weight_pct × frequency_multiplier` as `urgency`.

---

## 6. Navigation / Information Architecture per Role

**Public / student** (`frontend/app/`): `/` (landing) → `/t` (class picker) → `/t/[classCode]` (name/roll entry) → `/t/[classCode]/test` (Likert screens) → `/t/thanks`.

**School staff** (`/admin/*`, gated by `X-API-Key` sign-in stored client-side, permissions confirmed server-side via `/admin/me`):
- `/admin` — dashboard (overview, sections, recent scripts, top students)
- `/admin/sections/[sectionId]` — class roster, interest-test status, cohort chart
- `/admin/students/[studentId]` — one student: interest report, papers sat, diagnosis, issued reports (+ PDF download), documents
- `/admin/paper` — the assessment pipeline UI: create/scan/confirm/map/place/review a paper
- `/admin/answers` — per-student answer-sheet mark entry (camera capture supported)
- `/admin/gridsheet` — class-photo mark-entry sheet reading/review/resolve/confirm
- `/admin/boardx` — "cohort intelligence" dashboard: paper report + cohort report side by side

**Platform operator** (`/platform/*`, gated by `X-Platform-Key`):
- `/platform` — schools list, overview counts, school creation, key issuance/revocation/rotation
- `/platform/books` — per-subject book ingest status, contents/chapter upload, concept-family review
- `/platform/books/bulk` — (present, 493 lines — likely batch/bulk chapter upload UI; not read line-by-line this pass)
- `/platform/probe` — push real questions through the loaded book to sanity-check retrieval

---

## 7. Every Page/Screen — Build Status

Status determined by cross-referencing each `page.tsx`'s `api.*` calls against `frontend/lib/api.ts` and confirming the calls reach real, implemented backend routes (not stubs).

| Route | File | Lines | Status | Evidence |
|---|---|---|---|---|
| `/` | `app/page.tsx` | 170 | **Fully built** | Landing page |
| `/t` | `app/t/page.tsx` | 84 | **Fully built** | Calls `api.classes()` → `GET /t/classes` |
| `/t/[classCode]` | `app/t/[classCode]/page.tsx` | 119 | **Fully built** | `api.startSession` → `POST /t/{code}/start` |
| `/t/[classCode]/test` | `app/t/[classCode]/test/page.tsx` | 193 | **Fully built** | `saveResponses`/`complete` wired |
| `/t/thanks` | `app/t/thanks/page.tsx` | 40 | **Fully built** | Static confirmation |
| `/admin` | `app/admin/page.tsx` | 389 | **Fully built** | Dashboard, real data |
| `/admin/sections/[sectionId]` | `app/admin/sections/[sectionId]/page.tsx` | 323 | **Fully built** | `api.roster`, `api.cohort`, CRUD student calls all wired to live routes |
| `/admin/students/[studentId]` | `app/admin/students/[studentId]/page.tsx` | 357 | **Fully built** | `interestReport`, `studentDocuments`, `issuedReports`, `issueReport`, `issuedReportPdf`, `studentDiagnosis` all wired |
| `/admin/paper` | `app/admin/paper/page.tsx` | 1027 | **Fully built** (largest page in the app) | scan/confirm/map/place/review pipeline UI, job polling |
| `/admin/answers` | `app/admin/answers/page.tsx` | 714 | **Fully built** | camera capture + mark entry + reading review/confirm |
| `/admin/gridsheet` | `app/admin/gridsheet/page.tsx` | 601 | **Fully built** | upload/review/resolve/confirm grid pipeline |
| `/admin/boardx` | `app/admin/boardx/page.tsx` | 453 | **Fully built** | `api.overview`, `api.paperReport`, `api.cohortReport` all wired |
| `/platform` | `app/platform/page.tsx` | 524 | **Fully built** | schools/overview/keys CRUD |
| `/platform/books` | `app/platform/books/page.tsx` | 491 | **Fully built** | ingest status, contents/chapter upload, concept-family flows |
| `/platform/books/bulk` | `app/platform/books/bulk/page.tsx` | 493 | **Present, substantial — not deep-verified this pass** | file exists and is non-trivial in size; its exact `api.*` call list was not individually traced in this research pass |
| `/platform/probe` | `app/platform/probe/page.tsx` | 200 | **Fully built** | `api.probe` wired |

**No stub/placeholder pages were found** — every route under `frontend/app/` that exists has a substantial, wired implementation. There is **no dedicated screen for**:
- The `POST /assessments/{id}/marks` raw batch endpoint or `/reconcile` (constraint solver) — no UI calls found for these in `api.ts`'s exported surface as read (they may be intended as API-only/scripted paths).
- `/admin/staff` (list staff) is exposed as an API route (`GET /admin/staff`) but no dedicated frontend page was found reading `listStaff` outside what may be embedded elsewhere — verify before assuming it's unused.

---

## 8. Sample Data (from real test fixtures — cited)

From `backend/tests/conftest.py`:

**School fixture** (`school` fixture, session-scoped):
```json
{
  "name": "Bharath International Sr. Sec.",
  "api_key": "test-key-123",
  "state": "Tamil Nadu",
  "training_consent": "training_permitted"
}
```
> Note: `"training_permitted"` here is **not** one of the three values `platform.py`'s Pydantic validator actually accepts (`operational_only|improve_models|research`) — this fixture bypasses that validation by constructing the ORM object directly rather than going through the API. Flagged for awareness; not a bug in the app, just a reminder that DB-level and API-level validation diverge here.

Section: `grade=10, name="A"` under that school.

**Book fixture** (`book` fixture, from `conftest.py`) — five real `BookChunk` rows seeded across Maths chapters:
```
X.MATH.STATS / S13_2 — "Mean of Grouped Data" — "The mean of grouped data by the
  step-deviation method uses an assumed mean and a common class size h..."
X.MATH.STATS / S13_3 — "Mode of Grouped Data" — "The modal class is the class with
  the greatest frequency..."
X.MATH.CIRCLE / S10_1 — "Tangent to a Circle" (Theorem 10.1) — "The tangent at any
  point of a circle is perpendicular to the radius through the point of contact."
X.MATH.REAL / S1_2 — "Fundamental Theorem" (Theorem 1.1) — "Every composite number
  can be expressed as a product of primes..."
X.MATH.AP / S5_2 — "nth Term of an AP" (Section 5.2) — "...the nth term is given by
  a plus n minus one times d."
```
A concept family `X.MATH.CF.VOLUME` ("Volume of Composite Solids") is seeded under chapter `X.MATH.SAV`.

**Constructed samples** (real field names, built from the schema since no ready-made fixture matched exactly — noted as constructed, not pulled verbatim):

A `Question` row shape (from `assessment.py` + `marks.py` routes):
```json
{
  "address": "B/13/S/b",
  "section": "B", "question_no": "13", "sub_part": null, "choice_alt": "b",
  "max_marks": 3.0, "mark_step": 1.0,
  "board_unit_id": "<taxonomy_node.id for X.MATH statistics unit>",
  "chapter_id": "<taxonomy_node.id for X.MATH.STATS>",
  "curriculum_section": "13.2",
  "concept_family_id": "<taxonomy_node.id for X.MATH.CF.MEAN>",
  "concept_variant": "step-deviation method with class size 10 and assumed mean 47.5"
}
```

A `MarkEvent` shape (from `marks.py`'s `confirm_answer_sheet`):
```json
{
  "assessment_id": "...", "student_id": "...", "question_id": "...",
  "state": "awarded", "marks": 2.5,
  "source": "teacher", "confidence": 1.0, "actor_id": "Mrs. Lakshmi",
  "provenance": {"confirmed_by": "Mrs. Lakshmi"}
}
```

A `StaffKey` issuance response shape (from `platform.py::issue_staff_key`):
```json
{
  "id": "...", "role": "principal", "label": "Front office", "school_id": "...",
  "created_at": "2026-06-01T08:00:00Z", "revoked_at": null,
  "api_key": "AbCdEf1234567890...", "api_key_notice": "Shown once. Give it to..."
}
```

---

## 9. Existing Frontend Inventory

- **Framework:** Next.js App Router, TypeScript, no `pages/` router in use.
- **`frontend/lib/api.ts`** (~1405 lines) — the entire backend surface as a single typed object `export const api = {...}`, grouped by domain (student test, dashboard, operator console, knowledge base, question papers, gridsheet, reports, board intelligence). Includes hand-rolled `pollJob`/`postAndPoll` helpers for the 202-job pattern, `uploadMany`/`upload` multipart helpers, `pageBlob`/`issuedReportPdf` blob-fetch helpers (because `<img src>`/plain links can't carry the `X-API-Key` header).
- **`frontend/lib/session.ts`** — `localStorage`-only auth state, two independent credential stores (school-staff vs. platform operator), with an explicit comment that server-side `/admin/me` is the actual authority and client-cached role is only a rendering convenience.
- **Components:** `frontend/components/` exists (not enumerated exhaustively in this pass — referenced by page files); no external component library.
- **Recently added, narrowly-scoped dependencies (per system context):** `lucide-react`, `framer-motion`, `blobs` — confirmed present as small additions, not a UI-kit swap.
- No test files were found under `frontend/` in this pass (backend has the full pytest suite; frontend appears untested at the unit level as of this snapshot — verify with a dedicated search if this matters).

---

## 10. Existing Design System

From `frontend/app/globals.css` (~831 lines):

- **Color tokens** (light-first, dark overrides under `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])`, per the artifact dark-mode convention — though this is app code, not an Artifact):
  - `--mark` / `--mark-2` / `--mark-soft` — violet brand accent (`#6d5be0` light / `#a596f2` dark)
  - `--verify` / `--verify-2` / `--verify-soft` — green, "this is right/confirmed" (`#0f9d72` light)
  - `--warn` / `--warn-soft` — amber, caution (`#b8790a` light)
  - `--info` / `--info-soft` — blue, informational (`#2f6fed` light)
  - `--risk` / `--risk-soft` — pink, "this is wrong/blocked/an error" (`#d1447a` light) — deliberately kept separate from `--warn`, per the CSS comment
  - Shadow/glow tokens: `--glow-mark`, etc.
- **Typography:** `--font-display` (Manrope), `--font-body` (Source Sans 3), `--font-mono` (JetBrains Mono, used for the `.mono` utility class — likely IDs/addresses/API keys).
- **No component library** — cards, buttons, tables, badges are all hand-built CSS classes (`.accentbar`, `.brand`, etc.) plus per-page `styled-jsx`.
- **Icons:** `lucide-react`.
- **Animation:** `framer-motion`.
- **Decorative backgrounds:** `blobs` package.

---

## 11. UI Constraints Discovered

- **Permission is server-authoritative, never client-inferred.** Every gated action re-checks against `/admin/me`'s `can` object or the actual endpoint's own auth dependency; the frontend's cached `StaffRole` is explicitly documented (in `session.ts`) as a rendering convenience only.
- **Async job polling is a first-class UI pattern.** Three separate flows (`scanPaper`, `placePaper`, `uploadGridSheet`/`uploadSingleScript`) return HTTP 202 with a `job_id` for vision/LLM calls that exceed the hosting platform's request timeout (Render). The frontend's `onJobQueued` callback pattern exists specifically so a lost connection can **resume watching** an in-flight job rather than resubmitting (and double-billing) the same vision call — this is a deliberate, documented constraint (see comments in `api.ts` around `scanPaper`/`placePaper`).
- **Blob-fetch pattern for authenticated binary downloads.** Page images and issued-report PDFs cannot be linked directly (`<img src>` / `<a href>` send no custom headers), so `api.pageBlob`/`api.issuedReportPdf` fetch with the API key and hand back an object URL/Blob.
- **Multi-credential, multi-tenant header scheme.** `X-API-Key` (school/staff) and `X-Platform-Key` (operator) are entirely separate storage keys and never conflated; an admin `StaffKey` additionally requires `X-School-Id` to say which school a request is about.
- **Append-only / immutable-history UI implications.** Because `QuestionPlacement`, `QuestionTier`, `MarkEvent`, and `GridSheetRow` resolution are all append-only, screens that show "current state" (e.g. `/admin/paper`'s review queue) must always resolve "latest row per key" rather than reading a single mutable row — this is visible in both the backend aggregation logic (`_current_marks`, `_latest_placements` in `reports.py`) and presumably mirrored in how the frontend renders history/audit trails (not independently verified against every page's rendering logic in this pass).
- **Once issued, a report never recomputes** (`GET /reports/issued/{id}` returns the frozen `payload` verbatim) — the UI must distinguish "live diagnosis" (`GET /reports/student/{id}`) from "issued report" (`GET /reports/issued/{id}`) as two different data sources, not one screen re-fetching the same endpoint.

---

## 12. Open Questions, Gaps, and Product-vs-Code Mismatches

### 12.1 Naming: "Avai" vs. "Yaadhum" — **confirmed mismatch**
The product brief given to research this codebase refers to the product as **"Avai."** A full-text search of `backend/` and `frontend/` (source, config, docstrings, FastAPI `title=`, package names) finds **zero occurrences of "Avai."** The codebase, its API title, its module docstrings, its database naming, and its schema (`ml_corpus` bridge, `YAADHUM_*` env-var prefix) are all named **Yaadhum** throughout, consistently and deliberately (e.g. `app/main.py:49 title="Yaadhum"`, every settings env var is `YAADHUM_...`). If "Avai" is a real external/marketing brand for this same product, it is **not reflected anywhere in code** — there is no rebrand-in-progress artifact (no half-renamed strings, no `AVAI_` env vars, no commented-out old name). Treat "Avai" as an external-only label until told otherwise; do not assume the two names are used interchangeably in the code.

### 12.2 Whole-grade billing / 60-student minimum / consent tiers — **partially implemented, billing itself absent**
- `training_consent` **does exist** as a real column (`School.training_consent`, `String(32)`, default `"operational_only"`) and is validated server-side in `platform.py`'s `SchoolIn` Pydantic model to exactly three values: `"operational_only" | "improve_models" | "research"`. It is set at school-creation time and surfaced read-only via `GET /admin/me` and `GET /platform/overview`/`/platform/schools`.
- **No billing, headcount-minimum, or pricing logic of any kind exists anywhere in the codebase.** There is no `billing.py`, no invoice/subscription model, no "60-student minimum" constant or check, no per-grade or whole-grade enrollment gate found in any router or model. `platform.py`'s `create_school` accepts any number of sections/students with no floor. **This is aspirational/business-layer scope not represented in code — flag explicitly if the product description implies it is enforced.**
- The `ml_corpus` schema (`corpus.py`) implements the *mechanics* consent tiers would need to gate (per-row `consent_class`), but nothing in the routers currently reads `training_consent` to decide what does or doesn't flow into `ml_capture_asset`/`ml_prediction` — that wiring, if it exists, was not found in this pass (no producer code writing into `ml_corpus` tables was located under `backend/app/api/` or `backend/app/ingest/`). **Recommend a follow-up grep of the whole `backend/app/` tree for `ml_capture_asset`/`consent_class` writers before asserting this pipeline is live.**

### 12.3 30-day scorecard image retention — **documented intent, no configured infrastructure**
`backend/app/storage.py`'s module docstring states plainly: *"A page's bytes live in object storage (`storage.py`, an S3 bucket with a 30-day lifecycle rule in production)."* However:
- No Terraform, CloudFormation, or any infra-as-code directory was found in this repository (no `infra/`, `terraform/`, or `.tf` files located).
- No CLI script, migration, or application code sets an S3 lifecycle policy — `storage.py`'s `ObjectStore` protocol implements `put`/`open`/`delete`/`exists` only; there is no `set_lifecycle`/`configure_bucket` call anywhere.
- The 30-day retention is **a documented operational intention/runbook item, not something this codebase configures or enforces**. If a lifecycle rule exists, it was set manually/out-of-band against the actual AWS/R2 bucket, outside this repo's tracked configuration. **Flag clearly: retention is a claim in a comment, not a verifiable, code-enforced guarantee.**
- Separately, `ScanPage.storage_key` is nullable specifically because older rows still carry bytes directly in Postgres (`content: LargeBinary | None`, the pre-object-storage fallback) — so even the migration to object storage itself is only partially complete for historical rows, by design (documented, not a bug).

### 12.4 Other gaps and things to verify further
- **`ml_corpus` tables appear unused by any router** read in this pass — confirm with a full-repo grep before describing the "free recogniser" training pipeline as operational versus schema-only.
- **`/platform/books/bulk` page (493 lines)** was not individually traced against `api.ts` calls in this pass — confirm its exact feature set before describing it definitively.
- **`backend/app/api/documents.py`, `upload.py`, `matching.py`, `schemas.py`** were referenced and partially inferred from their call sites in other routers but not read end-to-end in this pass — their exact full route lists (documents.py in particular, which owns page-serving and deletion) should be re-verified if a precise document/page API contract is needed.
- **`backend/app/api/books.py` is 1774 lines**; this document covers roughly the first 1390 lines read directly (curriculum setup, ingest, probe, concept-family CRUD/audit/merge). The remainder (~380 lines, including `propose-llm` and `/embed` endpoints that `frontend/lib/api.ts` references as `proposeFamiliesWithModel` and `embedBatch`) exists and is called by the frontend, but was not read line-by-line — confirm exact behavior/response shape before citing it precisely.
- **No dedicated `GET /admin/staff` frontend consumer was confirmed** in the pages traced — the API route exists and is presumably used somewhere (perhaps within `/platform` or a staff-management modal not enumerated here); worth a targeted grep if staff-key visibility UX matters to the requester.
- **Frontend has no automated test suite found** in this pass (`frontend/` — no `*.test.ts(x)` files located), in contrast to the backend's extensive pytest coverage. Confirm with a dedicated search if frontend test coverage is a decision input.
