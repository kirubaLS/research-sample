# Question-mapping pipeline: read-only investigation report

**Scope.** How a scanned question paper becomes a mapped question (chapter, topic/section, concept family, tier) in this repository, with emphasis on Class X Social Science (`X.HIST`, `X.GEO`, `X.POL`, `X.ECO`, assessments under the `X.SST` group).

**Code version.** Branch `claude/pilot-architecture-production-62or5m`, commit `4e97dfa`. All paths are relative to the repository root. Backend paths start with `backend/`.

**Method.** Read-only reading of the source, plus read-only inspection of the reference book-map JSON. No code, config, data or migration was changed. No job, test, migration or model call was run. The only database reachable from this environment is a local SQLite development file, which does not contain the production rows asked about (see section 3).

**Conventions.** Every claim cites `file:line`. **INFERRED** marks a conclusion drawn from reading code rather than seen directly. **UNKNOWN** marks something the code cannot settle, with what would settle it. Secrets are never shown; env var names are given instead.

---

## 0. Summary

A teacher uploads a question paper. If the PDF has a usable text layer and its marks add up, a regex extractor reads it inline; otherwise each page is read by Claude (Opus 5) as an image, with the previous page alongside for context. The rows land in `scanned_question`, keyed by an address `SECTION/QNO/SUBPART/CHOICE`. With the zero-touch flag on (the default), the server then confirms the scan itself (filling any missing marks), and queues two jobs: **map** and **place**. **Map** runs hybrid retrieval (TF-IDF plus Jina embeddings, fused by reciprocal rank) against the NCERT book chunks, picks a chapter from the retrieval winner, picks a section from retrieval, chooses or auto-creates a concept family, and creates the `question` row with one `question_placement` and one `question_skill`. **Place** then re-reads every question with a chapter judge (Claude Sonnet 5, one call per question, sometimes two passes), reconciles against any declared blueprint, and runs a topic judge (Sonnet 5, 2–8 calls per question over the whole chapter text, prompt-cached, batched at half price) that decides the section; it appends a second `question_placement`, a `question_tier`, and rewrites the topic in `question_skill`. The teacher's screen shows the chapter from `question.chapter_id`, the topic from the heaviest `question_skill` row, the tier from an unordered pass over `question_tier`, and the review flag and explanation from the newest `question_placement`. For Social Science, the section letter A/B/C/D narrows each question to History/Geography/Political Science/Economics; the chapter named in a section header is not stored or used.

| Stage | Entry point (file:function) | Model + effort / params | Calls | Tables read | Tables written |
|---|---|---|---|---|---|
| Book ingestion, PDF | `backend/app/api/books.py:upload_chapter` → `_process_chapter` → `_load` | None for English-script books (PyMuPDF). Hindi: Sarvam, Tesseract or Gemini `gemini-3.6-flash` temp 0. Tamil: Tesseract fallback | Gemini: 1 per page (Hindi only) | `taxonomy_node`, `book_source`, `chapter_board_unit` | `taxonomy_node` (chapter, subtopic), `book_chunk`, `canonical_procedure`, `book_source.files` |
| Book ingestion, book map (SST, Science) | `backend/scripts/import_book_map.py:main` → `_apply_subject` | None | 0 | reference JSON/MD, `taxonomy_node`, `question` | deletes then inserts `book_chunk`, `concept_family_proposal`; upserts concept-family `taxonomy_node` |
| Embedding | `backend/scripts/embed_kb.py`, `POST /platform/books/{subject}/embed` | Jina `jina-embeddings-v4`, 512 dims | 1 request per ≤32 chunks | `book_chunk` | `book_chunk.embedding` (JSON) |
| Paper scan, text route | `backend/app/api/marks.py:scan_paper` → `backend/app/extraction/paper.py:extract_paper` | None (regex) | 0 | — | `scanned_question`, `assessment`, `scan_document`, `scan_page` |
| Paper scan, vision route | `marks.py:_run_paper_scan_job` → `backend/app/extraction/paper_vision.py:read_paper_vision` | `claude-opus-5` (`model_high_stakes`), max_tokens 16000, no effort sent, structured output | 1 per page (≤2 images each) | `paper_scan_job` | `paper_scan_job`, `scanned_question`, `assessment`, `scan_document`, `scan_page` |
| Subject check | `marks.py:check_paper_subject` | None (lexical retrieval) | 0 | `book_chunk` | — |
| Auto-confirm | `marks.py:auto_confirm_scan` | None | 0 | `scanned_question` | `scanned_question.max_marks`, `assessment.scan_confirmed_*` |
| Map | `marks.py:_run_map_job` → `_map_paper` | Retrieval only in zero-touch; topic judge (Sonnet 5, medium) only on a manual map; `auto_resolve` Sonnet 5 medium, 4000 tokens | Jina: 1 per question. LLM: 0–1 per question (`auto_resolve`); 2–8 per question if topic judge runs | `scanned_question`, `book_chunk`, `taxonomy_node`, `concept_family_proposal`, `chapter_board_unit` | `question`, `question_placement`, `question_skill`, `scanned_question.question_id/blocked_reason`, auto `taxonomy_node` families, `concept_family_proposal`, `placement_job` |
| Place: chapter judge | `backend/app/api/placement.py:_run_placement_job` → `backend/app/classify/pipeline.py:place_paper` | `claude-sonnet-5` (`model_classifier`), effort `medium`, max_tokens 16000, live by default | 1 per question per pass; 2 passes when scope is inferred | `question`, `book_chunk`, `taxonomy_node` | — (in memory) |
| Place: topic judge | `backend/app/classify/topic.py:choose_topic` | `claude-sonnet-5`, effort `medium`, max_tokens 8000 (reads) / 2000 (answerability), prompt-cached chapter, Batches API by default | 2–8 per question, typically 3–4 | `book_chunk` | — (in memory) |
| Place: write | `placement.py:_run_placement_job` (write phase) | `auto_resolve` as above when a family is blocked | 0–1 per question | `question`, `concept_family_proposal` | `question`, `question_placement`, `question_tier`, `question_skill`, `concept_family_proposal`, `placement_job` |
| Human review | `placement.py:confirm` | None | 0 | — | `question_placement` (source `human`), `question`, `question_skill`, `question_tier`, `concept_family_proposal` |
| Display | `marks.py:read_scan` (`GET /assessments/{id}/scan`) | None | 0 | `scanned_question`, `question`, `question_skill`, `question_tier`, `question_placement`, `taxonomy_node` | — |

---

## 1. Repo map

**Languages and frameworks.**
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, pydantic-settings, psycopg (`backend/pyproject.toml`). Other packages: numpy, scipy, httpx, pymupdf, anthropic, sarvamai, openpyxl, fpdf2. Optional extras `vision` (opencv, pyzbar, img2pdf, pikepdf), `storage` (boto3), `dev`.
- Frontend: Next.js 15, React 18, framer-motion, lucide-react, dexie, zod; vitest (`frontend/package.json`).

**Where things live.**
- API routers: `backend/app/api/*.py`, mounted in `backend/app/main.py:111-127` (admin, academics, exams, teacher_academics, interest, marks, books, placement, platform, reports, documents, reading, gridsheets, board, remediation, student).
- Mapping pipeline: `backend/app/api/marks.py` (scan, confirm, map, display), `backend/app/api/placement.py` (place, review), `backend/app/classify/*` (judges, grounding, reconcile, scope, topic), `backend/app/mapping/*` (family choice, auto-resolve, topic nodes), `backend/app/ingest/probe.py` (retrieval), `backend/app/extraction/*` (paper reading).
- LLM and external clients: Anthropic in `backend/app/classify/anthropic_judge.py`, `backend/app/classify/topic.py`, `backend/app/extraction/paper_vision.py`, `backend/app/extraction/gridsheet.py`, `backend/app/mapping/auto_resolve.py`, `backend/app/curriculum/llm_families.py`. Shared options in `backend/app/llm.py`; Batches API wrapper in `backend/app/llm_batch.py`. Jina in `backend/app/ingest/jina.py`. Gemini in `backend/app/ingest/gemini_ocr.py`. Sarvam in `backend/app/ingest/sarvam_ocr.py`.
- DB models: `backend/app/models/` (`assessment.py`, `taxonomy.py`, `documents.py`, `marks.py`, `core.py`, others). Migrations: `backend/migrations/versions/` (about 37 Alembic revisions), config `backend/alembic.ini`. Outside production, `init_db()` runs at startup (`backend/app/main.py:43-50`).

**How jobs run.** FastAPI `BackgroundTasks` only, in the API process. There is no queue, worker or cron in the application code. Job state is stored in tables: `placement_job` (kinds `map` and `place`, `backend/app/models/documents.py:348-389`), `paper_scan_job` (`documents.py:317-345`), `grid_sheet_job` (`documents.py:272`), `ingest_job` (`backend/app/models/taxonomy.py:248-281`). The zero-touch chain runs synchronously inside the scan job's background task (`marks.py:1053-1063`). Inside a place job, batched judges fan out over a thread pool of up to 64 workers (`pipeline.py:214-225`, `placement.py:461-469`). Redis appears in the root `docker-compose.yml` but nothing in `backend/app` uses it.

**Hosting and deploy (names only).**
- `infra/docker-compose.yml`: services `postgres` (postgres:16-alpine), `backend`, `frontend`, `caddy` (caddy:2-alpine). Backend reads `infra/.env` ([REDACTED]).
- `infra/Caddyfile`: placeholder domains routing to `frontend:3000` and `backend:8000`.
- `infra/README.md`: an AWS Lightsail VM plus an S3 bucket in `ap-south-1`. `infra/s3-lifecycle.json` expires scanned pages after 30 days. `infra/backup-postgres.sh` runs a nightly `pg_dump` to S3 from cron.
- `backend/Dockerfile`: python:3.12-slim with Tesseract (eng, hin, tam); runs `alembic upgrade head && uvicorn ... --workers ${UVICORN_WORKERS}` with `UVICORN_WORKERS=2`.
- `frontend/Dockerfile`: node:22-slim.
- `render.yaml`: services `yaadhum-api` and `yaadhum-hindi-ingest`; env values [REDACTED].
- CI: `.github/workflows/ci.yml`.
- Env vars use the prefix `YAADHUM_` (`backend/app/config.py:38`). Secrets relevant here: `YAADHUM_ANTHROPIC_API_KEY`, `YAADHUM_JINA_API_KEY`, `YAADHUM_GEMINI_API_KEY`, `YAADHUM_SARVAM_API_KEY`, `YAADHUM_DATABASE_URL`, `YAADHUM_MIGRATION_DATABASE_URL`, `YAADHUM_PLATFORM_ADMIN_KEY` — all [REDACTED].

---

## 2. Stage-by-stage walkthrough

### 2.1 Book ingestion

There are two independent ways book text reaches `book_chunk`. Social Science and Science are expected to use the **book-map import**; Maths, English, Hindi and Tamil use the **PDF path**.

#### 2.1.1 PDF path

**Trigger.** Platform routes in `backend/app/api/books.py`:

| Route | Lines | Behaviour |
|---|---|---|
| `POST /{subject}/contents` (`upload_contents`) | 898-933 | Hindi (`X.HIN*`): creates `IngestJob(kind="contents")`, queues `_run_ingest_job`, returns 202. Others: `_process_contents` inline. |
| `POST /{subject}/chapters?locate_known_sections=` (`upload_chapter`) | 936-978 | Same Hindi/background split; others run `_process_chapter` inline. |
| `GET /{subject}/jobs/{job_id}` | 981-994 | Poll; failure raised from `error_status`/`error_detail`. |
| `POST /{subject}/expected-sections` | 652-716 | Hand-typed section list merged into `book_source.expected_sections`. |
| `POST /{subject}/embed?limit=32` | 2203-2260 | Embedding backfill, at most 64 per call. |

`curriculum_version` is hard-coded to `"CBSE-2026-27"` (`books.py:689, 912, 954`).

**Text extraction.**
- English-script books (Maths, Science, SST, English): PyMuPDF `page.get_text()`, then `_collapse_vertical` and `_collapse_bold` (`backend/app/ingest/book.py:348-364`).
- Hindi (`backend/app/ingest/hindi_text.py:29-49`), first available of: Sarvam Document AI (`sarvam_ocr.py:23-106`; `doc_ai.digitise`, markdown output, ≤10 pages per job, 600 s timeout); Tesseract `-l hin --psm 6` at 300 DPI (`hindi_ocr.py:32-49, 91-100`); Gemini (`gemini_ocr.py`).
- Tamil (`tamil_text.py:146-162`): PyMuPDF text, then `clean_tamil_text`; a page flagged corrupted by `tamil_text_is_corrupted` (86-119) is re-read with Tesseract `-l tam` (`tamil_ocr.py:33-49, 71-95`).
- Gemini call (`backend/app/ingest/gemini_ocr.py`): `generateContent` on `gemini-3.6-flash` by default (`config.py:176`), `temperature: 0.0`, one call per page as a 300-DPI PNG, 3 retries with `2**attempt` backoff on 429/5xx/transport errors (lines 40, 65-98, 121-133). Prompt, verbatim (`gemini_ocr.py:50-54`):

```text
Transcribe the Hindi (Devanagari) text of this page image exactly as printed, in reading order. Output ONLY the transcribed text -- no summary, no translation, no commentary, no markdown formatting. If the page has no readable text, output nothing.
```

No LLM is used for chunking or for section detection.

**Section detection (`extract_chapter`, `book.py:1978-2000`).**

```python
if known_section_titles is not None:
    sections, missing = _locate_known_sections(path, text, known_section_titles)
elif single_section:
    sections = [Section("1", resolved_title, 0, len(text))]
elif bare_headings:
    sections = _sections_by_boldness(path, text, resolved_title)
else:
    sections = extract_sections(text, number, path=path)
    if not sections:
        sections = _sections_by_boldness(path, text, resolved_title)
```

- `single_section` for English, Hindi and Tamil books; `bare_headings` for History; `body_bucket="E"` only for `X.ENG.WB` (`books.py:793-800`).
- `extract_sections` (`book.py:915-1032`): regex `{chapter}\.\d+(\.\d+)?` on the text (Maths, Science). Font size only merges wrapped titles.
- `_sections_by_boldness` / `_pick_sections` (`book.py:1131-1684`): bold or larger spans. Numbering is the book's printed numbering when it appears at least twice (History), otherwise **reading order** `"1"`, `"2"`, ... (`book.py:1601-1604`) or invented `major.minor` (1584-1599). The docstring at `book.py:1632-1633` says the numbers are "just 1, 2, 3... in reading order".
- `_locate_known_sections` (`book.py:1777-1915`), used with `?locate_known_sections=true`: matches the typed titles from `book_source.expected_sections` against PDF spans and numbers them by position (`book.py:1911-1914`).
- `book_source.expected_sections` is otherwise only a verification oracle: `verify_against_toc` compares by number (`book.py:2015-2046`, called from `books.py:819-821`). It comes from the contents-page parser `parse_toc` (`book.py:420-444`, Maths only in practice), from `POST /expected-sections`, or from `backend/scripts/load_expected_sections.py`.

**Chunking (`extract_chunks`, `book.py:1687-1774`).**
- Markers start a chunk: `Theorem N.N`, `Activity N.N`, `Example N` (bucket T); `EXERCISE N.N` and drill labels such as QUESTIONS, EXERCISES, "Let's work these out", "Think about it" (bucket E); Hindi "अभ्यास" and Tamil "கற்பவை கற்றபின்" labels; numbered questions in single-section books (`book.py:31-41, 1703-1740`).
- Text from a section heading to its first marker becomes a body chunk with reference `"Section {number}"` if it is at least `MIN_BODY_CHARS = 200` (`book.py:1036, 1763-1766`).
- A chunk over `MAX_CHUNK_CHARS = 6000` is split on blank-line paragraphs with `" (part i)"` appended (`book.py:1048-1079`).
- No fixed-size or overlapping windows.
- **Bucket.** Fixed per marker kind: T for theorem/activity/example and body, E for exercise and drill labels; body is E only for `X.ENG.WB`.
- The labels "(caption)", "(box)", "(activity)", "(glossary)", "(source)", "(map)" and "Exercise Qn" are **never** produced on this path.
- **Why some text has no section.** Text before the first detected heading is outside every section span and is not chunked at all (**INFERRED** from `book.py:1759-1763`). `section_number` is `None` only on rows loaded before the column existed; migration `backend/migrations/versions/a1c4f7e920b3_book_chunk_section.py:27-45` back-filled them from `reference`.

**`_load` (`books.py:997-1114`)** writes the rows:
- Chapter node: reuses a chapter whose label matches the extracted title; otherwise creates `{subject}.CH{nn}` (997-1014).
- Subtopic node per section: code `{chapter}.S{number with "." → "_"}`, label = heading text without number; relabelled in place if the code exists (1016-1030).
- `book_chunk` rows, deduplicated on (`stem_hash`, `curriculum_version`, `node_id`); `normalised` is not lowercased on this path (1042-1049); `section_number` corrected in place on existing rows, keeping their embedding (1051-1067); stale chunks deleted (1094-1106).
- `canonical_procedure` rows for theorem/activity/example (1068-1079).
- `book_source.files[name] = {chapter, sha256, chunks, loaded_at}` (870-877).

#### 2.1.2 Book-map path (Social Science and Science)

**Trigger.** `python -m scripts.import_book_map --apply` (dry-run by default). `SUBJECT_FILES` (`backend/scripts/import_book_map.py:58-64`):

```python
"X.HIST": "book_map/history/history_units.json",
"X.GEO": "book_map/geography/geography_units.json",
"X.POL": "book_map/politics/politics_units.json",
"X.ECO": "book_map/economics/economics_units.json",
"X.SCI": "book_map_science/science_units.json",
```

**Input.** `backend/reference/book_map/*/*_units.json`: a list of chapters `{code, title, pages, units[], exercise{...}, unknown}`. A unit is `{id, kind, number, title, parent, pages, body[{page, col, y0, y1, band, text, ...}], terms[{term, definition}], key_terms, boxes[{label, title, page, text[]}], sources[...], activities[...], captions[{page, text}], flags, catalog}`. Geography units also carry "CBSE map items linked to this unit" lines in the chapter `.md` files only.

**Processing (`_apply_subject`, `import_book_map.py:237-319`).**
1. Deletes every `book_chunk` and `concept_family_proposal` row of the subject, and stale concept-family nodes that have no questions (with their `taxonomy_alias` rows). Families that have questions are kept and reported (212-217, 241-249).
2. For each unit with a `catalog` code (units without one are skipped, 268-270), `_text_chunks` (114-163) emits one chunk per item, all bucket **T**, `reference[:80]`:

| Item | Reference |
|---|---|
| each `body[]` paragraph | `"{number} {title}"` (or title if no number) |
| `terms[]` | `"{label} (glossary: {term})"`, text `"term -- definition"` |
| `boxes[]` | `"{label} (box: {title})"` or `"(box)"` |
| `sources[]` | `"{label} (source: {title})"` or `"(source)"` |
| `activities[]` | `"{label} (activity)"` |
| `captions[]` | `"{label} (caption)"` |
| map items (from `.md`) | `"{label} (map)"`, text "Map work for this section. Shown on the map of India under this topic: …" (68-111) |

3. Exercises: each string of `chapter.exercise.text[]` becomes bucket **E**, `reference=f"Exercise Q{i}"` where `i` is the list index (not the printed question number), `section_number=None` (285-296).
4. `section_number = unit["number"]`, the printed number from the curated JSON. Units with no number get `None`: introductions (`*.0`) and summary/conclusion units (Science 25 such units, History 7, Geography 7).
5. `normalised = normalise(text).lower()`; **no embedding is set**.
6. No size cap on this path. `intext_questions`, `key_terms`, `flags` and `unknown` are never read.
7. Concept-family nodes and proposals: see 2.2.4.

**Subtopic nodes are never touched by this import** (docstring at `import_book_map.py:5-8`; nothing in `_apply_subject` queries them).

#### 2.1.3 Embeddings

- Model and size: `embedding_model="jina-embeddings-v4"`, `embedding_dimensions=512` (`backend/app/config.py:162, 189`; same defaults in `backend/app/ingest/jina.py:24, 79-80`).
- Request: `POST https://api.jina.ai/v1/embeddings` with `task` `"retrieval.passage"` for chunks and `"retrieval.query"` for questions (`jina.py:122-129`). Batched under a 12000-character budget; longer texts truncated (37, 108-116). At most 2 concurrent requests process-wide; 429 retried up to 6 times, 5xx up to 3 (`jina.py:45-46` and the retry loop).
- Storage: `book_chunk.embedding` is a **JSON column** of floats, not pgvector (`backend/app/models/taxonomy.py:162`, comment "pgvector in production" only; migration `5a1ebe98e396…py:189` uses `sa.JSON()`). Cosine is computed in Python (`backend/app/ingest/embed.py:38-44`, `backend/app/ingest/probe.py:150-170`).
- When: **never at ingest.** Only `backend/scripts/embed_kb.py` (`--subject`, `--re-embed`, `--dry-run`, batches of 32, rows with no embedding, lines 39-77) and `POST /{subject}/embed` (`books.py:2203-2260`) write vectors.
- **Why X.SCI chunks have no embeddings (INFERRED).** `import_book_map --apply` deletes every chunk of each subject in `SUBJECT_FILES`, including X.SCI, and inserts new rows with `embedding` NULL (`import_book_map.py:241, 278-296`). Nothing in the import embeds. Unless `embed_kb --subject X.SCI` was run afterwards, Science has no vectors; the same holds for each SST subject after every re-import. With no vectors, `SemanticIndex` keeps no chunks (`probe.py:158`) and retrieval is lexical only. **UNKNOWN** whether `embed_kb` was run in production; a `SELECT subject_code, count(*) FILTER (WHERE embedding IS NOT NULL) FROM book_chunk GROUP BY 1` would settle it.

**Tables written.** See the summary table. `GET /books` reports `book_loaded = embedded > 0` (`books.py:104-118`), so a freshly imported, unembedded subject shows as not loaded (**INFERRED**).

### 2.2 Taxonomy and topics

#### 2.2.1 How each node kind is created

`TaxonomyNode` (`backend/app/models/taxonomy.py:39-51`, table `taxonomy_node`): `kind`, `code` (String 80), `label`, `label_i18n`, `parent_id`, `path`, `curriculum_version` (default `"CBSE-2026-27"`), `valid_from`, `valid_to`; unique on (`curriculum_version`, `code`). Every creation site sets `path = code`.

| Kind | Code path | Code format | Label | Parent |
|---|---|---|---|---|
| subject | `backend/app/curriculum/apply.py:18-26`, from `CURRICULA` (`backend/app/curriculum/__init__.py:535-550`), via `POST /{subject}/curriculum` (`books.py:362-434`) or `scripts/seed.py` | `X.POL` | `subject_label` | none |
| board_unit | `apply.py:28-40` (also `board_unit_weight`) | `X.POL.U.WHOLE` | unit label | subject |
| chapter | `apply.py:42-51` (also `chapter_board_unit`, 52-64); fallback `books.py:997-1014` | `X.POL.PARTIES`; fallback `{subject}.CH{nn}` | chapter label | subject |
| subtopic | (A) `books.py:_load` 1016-1030 at PDF ingest; (B) `backend/app/mapping/topic_node.py:topic_node` 118-137 at map/classify/review | `{chapter}.S{n_n}` in both | (A) heading only; (B) caller's label, for book-map subjects `"{number} {title}"` | chapter |
| concept_family | curated (`apply.py:66-73`, Maths only); `books.py:create_families` 1586-1590; `import_book_map.py` 298-310; `marks.py:_ensure_family` 1860-1897 | curated code; request code; unit `catalog` code; `{chapter}.CF.AUTO_S{n_n}` or `.CF.AUTO_CHAPTER` | as given; unit title; heading / "Section X" / chapter label | chapter |

All lookups are by `code` with no version filter (`apply.py:13-14`, `books.py:1018`, `topic_node.py:121`).

#### 2.2.2 Why Political Parties has both `S1_2` "1.2 Functions" and `S4` "Functions"

Two writers create subtopic nodes under the same chapter with different numbering, and nothing reconciles them.

1. **PDF ingest (path A) numbers by reading order.** Political Parties prints no `4.x` numbers, so `_sections_by_boldness` or `_locate_known_sections` numbers sections 1, 2, 3, … in reading order. The hand-typed oracle for this chapter (`backend/scripts/load_expected_sections.py:256-284`) is:

```text
"4": [  # jess404.pdf -- Political Parties -- proven against the real file
    {"number": "1", "title": "Overview"},
    {"number": "2", "title": "Why do we need political parties?"},
    {"number": "3", "title": "Meaning"},
    {"number": "4", "title": "Functions"},
    {"number": "5", "title": "Necessity"},
    {"number": "6", "title": "How many parties should we have?"},
    {"number": "7", "title": "Popular"},
    {"number": "8", "title": "National parties"},
    {"number": "9", "title": "State parties"},
    {"number": "10", "title": "Challenges to political parties"},
    {"number": "11", "title": "How can parties be reformed?"},
```

   `set_expected_sections`'s docstring requires reading-order numbers for books with no numbering (`books.py:674-680`). So ingest created `X.POL.PARTIES.S1` "Overview" … `S4` "Functions" … `S7` "Popular", `S8` "National parties" … `S11` (**INFERRED** from the oracle and `_load`; the DB was not available).
   - "Overview" is a size-based heading (`book.py:1628-1630, 1660-1663`).
   - "Popular" is a word-order truncation of a box heading "Popular participation in political parties" (`load_expected_sections.py:24-31, 276-282`). In the book map it is only a box title (`backend/reference/book_map/politics/4_political_parties.md:79`, `#### Box: Popular`).
   - An earlier six-section pass existed (`load_expected_sections.py:26-31, 263-269`), which would have produced a third numbering (**INFERRED**).

2. **Mapping and classify (path B) number by the book map's printed numbers.** The book-map units for this chapter are `0` (no number) "Overview", `1` "Why do we need political parties?", `1.1` "Meaning", `1.2` "Functions", `1.3` "Necessity", `2`, `3` "National parties", `4` "State parties", `5`, `6`. `import_book_map` stores `reference = "1.2 Functions"`, `section_number = "1.2"` (`import_book_map.py:123-131, 275-283`). At mapping time, `section_headings` uses `book_map_topic_label` for book-map subjects (`topic_node.py:56-69, 84-100`), which returns `"1.2 Functions"`, and `marks.py:2384-2389` calls `topic_node(db, chapter, "1.2", "1.2 Functions")`. That produces code `X.POL.PARTIES.S1_2`, which no ingest node has, so a new subtopic is created.

3. **Collisions relabel ingest nodes.** For printed section `3`, `topic_node` computes `X.POL.PARTIES.S3`, which already exists as the ingest node "Meaning". Because the new label differs and is not a bare number, `topic_node.py:131-136` relabels it to "3 National parties". So `S3` reads "3 National parties" while `S8` still reads "National parties", and "Meaning" is lost (**INFERRED**). The same can happen to `S1`, `S2`, `S4`, `S5`, `S6`.

4. **"Overview" and "Popular" survive** because no book-map section number points at them (Overview has no number; Popular is a box) and no code path deletes subtopic nodes.

5. **Compounding paths.**
   - `marks.py:2221-2229` builds `topics[(chapter_id, section)]` from all subtopic nodes by parsing the code tail, and falls back to it when `topic_node` is not reached (`marks.py:2390-2391`), so a stale ingest node with a matching number can be written as the topic.
   - `books.py:propose_families` (1414-1429) proposes heading families from every subtopic node, including stale ones (**INFERRED**).
   - `backend/scripts/diagnose_duplicate_subtopics.py:1-8` groups by label only and would not pair "1.2 Functions" with "Functions".
   - `topic_node.py:24-31` states the two numberings are unrelated: "a number-match between the two is a coincidence, not a join".

#### 2.2.3 `book_source.expected_sections` and `expected_chapters`

`BookSource` (`taxonomy.py:217-245`, table `book_source`, unique on version + subject): `expected_sections` JSON `{chapter_number: [{"number","title"}]}`, `expected_chapters` JSON `{chapter_number: title}`, `files` JSON.

- **Producers.** `_process_contents` (`books.py:534-635`): `parse_toc` / `parse_toc_chapters`, merging `expected_sections` per chapter and replacing `expected_chapters` (586-613). `set_expected_sections` (`books.py:652-716`), additive per chapter. `scripts/load_expected_sections.py:938-990`, which calls `set_expected_sections` in-process with the hard-coded `EXPECTED_SECTIONS`.
- **Readers.** `_process_chapter` (`books.py:719-885`): titles for `_locate_known_sections` (778-788), the `verify_against_toc` oracle (804-821), the chapter-title check from `expected_chapters` (846-857). `status_for` (`books.py:437-531`) for progress counts. **Mapping does not read either field.**

#### 2.2.4 Concept families: proposal, application, and the link to a section

**Heading proposals.** `backend/app/curriculum/families.py:propose` (135-186) emits one proposal per subtopic heading with code `{subject}.CF.{slugify(label)}`. Served by `GET /{subject}/concept-families` (`books.py:1389-1539`), merged with stored proposals and deduplicated.

**LLM proposals.** `POST /{subject}/concept-families/propose-llm` (`books.py:2338-2472`) uses `AnthropicFamilyProposer` (`backend/app/curriculum/llm_families.py`) with `model=settings.model_high_volume` (`claude-haiku-4-5`, `config.py:83`), effort from `settings.model_effort` only if the model accepts effort (`backend/app/llm.py:20-52`; `claude-haiku-4-5` is not in `EFFORT_CAPABLE`, so no effort is sent), `max_tokens=16000`, structured output `ChapterFamilies` (`llm_families.py:45-67`; fields `label`, `code_label`, `rationale`, `evidence[]`, `from_sections[]`). Passages are `(reference, section_number, text)` capped at 1200 characters each and subsampled to a 150000-token budget (`llm_families.py:38, 112-140`). `ground()` (220-276) drops families with unresolvable citations and caps at 12; **`from_sections` is not validated**. Rows are stored with `source="llm"`, `applied_at` NULL (`books.py:2415-2429`). This route is not part of the mapping pipeline.

SYSTEM prompt (`backend/app/curriculum/llm_families.py:70-93`):

```text
You divide a school textbook chapter into concept families.

A concept family is one thing a student can be separately good or bad at, and that a
teacher would reteach as a unit. It is the row label on a diagnostic report.

Rules, all of them absolute:
- Propose families ONLY for material in the passages you are shown. Never add a topic
  because you know the subject; if it is not in the passages, it does not exist here.
- Every family must cite the references of the passages it rests on, copied EXACTLY as
  they appear. Do not invent a reference. Do not cite a passage you were not shown.
- Prefer the chapter's own section headings. Split one only when the passages show the
  section drilling genuinely different procedures -- different worked methods, or
  exercises that require different steps. Say so in the rationale when you split.
- Merge two headings only when the passages show them requiring the same procedure.
- Do not propose a family for an introduction, a summary, or a list of formulae. A
  student is not weak at "Introduction".
- Do not judge difficulty, importance, or how often something is examined. You cannot
  know those from the book, and guessing them is the failure this task must avoid.

Return between 1 and 12 families. Fewer, well-chosen families are better than many.

Write the label in the language of the book, so a teacher of that book recognises it. Put
an English (or transliterated) version in code_label: the code that outlives the label is
built from that, and a label in Devanagari or Tamil script alone cannot become one.
```

User prompt template (`backend/app/curriculum/llm_families.py:143-165`):

```python
def build_prompt(chapter_label: str, passages: list[tuple[str, str, str]]) -> str:
    """``passages`` is (reference, section number, text).

    Every passage is printed with its tag, and the model is told to cite tags. The tag is
    what makes a fabricated citation detectable rather than merely suspected.
    """
    parts = [
        f"Chapter: {chapter_label}",
        "",
        "Passages from this chapter, each with a tag in [brackets].",
        "Cite the TAGS -- e.g. \"evidence\": [\"P3\", \"P7\"] -- not the passage text.",
        "",
    ]
    for i, (reference, section, text) in enumerate(passages, start=1):
        body = text.strip()
        if len(body) > CHUNK_CHARS:
            body = body[:CHUNK_CHARS] + " ..."
        parts.append(f"[{tag(i)}] {reference} (section {section or '?'})\n{body}\n")
    parts.append(
        "Propose the concept families for this chapter. Put the tags of the passages each "
        "family rests on in its evidence list."
    )
    return "\n".join(parts)
```

**Applying families.**
- `create_families` (`books.py:1542-1619`): creates the family node; sets `applied_at` on a matching proposal, or inserts a `source="headings"` proposal with `from_sections` and `applied_at`.
- `scripts/apply_concept_families.py` and `POST /concept-families/auto-apply` (`books.py:2146-2200`) dedupe and call the same creation logic.
- `import_book_map` (`import_book_map.py:298-319`): one family per unit `catalog` code (label = first unit's title; sections = the set of unit numbers sharing the code), upserted as a node, plus a `concept_family_proposal` with `run_id="book_map_import_v1"`, `source="book_map"`, `evidence = from_sections = printed numbers`, `applied_at` not set. Example: `X.POL.CF.FUNCTIONS` with `["1.2"]`.

**Link to a section.** There is no section column on the family node. The link is `concept_family_proposal.from_sections`.
- `sections_of` in map and place is a dict comprehension over all proposal rows of the subject, with no `ORDER BY`, so when several rows share a code the last returned wins (`marks.py:2237-2242`, `placement.py:373-378`). `auto_resolve.py:371-374` builds a union instead. `clean_sections` keeps only values like `1`, `1.2`, `12.3.1` (`books.py:1252-1262`).
- `record_family_section` (`backend/app/mapping/auto_resolve.py:143-173`) adds a section to every row of a code, seeded from the first matching row; inserts a new proposal if none exists.
- `_ensure_family` (`marks.py:1860-1897`), zero-touch only: code `{chapter.code}.CF.AUTO_{S1_2 | CHAPTER}`, label from the heading (for book-map subjects possibly "1.2 Functions"), recorded via `record_family_section(model="auto", source="auto_pipeline")`. These codes are not under the `{subject}.CF.` prefix that the book-screen routes filter on (e.g. `books.py:1360`), so those screens would not list them (**INFERRED**).

### 2.3 Question-paper scan / OCR

**Trigger.** `POST /assessments/{id}/scan` → `scan_paper` (`backend/app/api/marks.py:1066-1166`), from the teacher dashboard upload buttons (`frontend/lib/usePaperScan.ts:submitScan`, 361-438).

**Steps.**
1. 409 if the Q-matrix is frozen (`marks.py:1092-1093`).
2. `_supersede_pending_paper_jobs` fails every pending `paper_scan_job` for the assessment with 409 (`marks.py:766-790`).
3. Uploads are merged into one PDF (`pages_to_pdf`); `extract_paper(path, subject_code=...)` runs; `source_sha` = sha256 of the merged PDF (`marks.py:1105-1120`).
4. `check_paper_subject` (`marks.py:1529-1596`) may refuse with 422 before anything is stored. It is lexical retrieval against the book (no LLM), comparing at group level.
5. Route decision (`marks.py:1133-1135`):

```python
unreliable_text = extract.route == "text" and not _text_route_is_confident(extract)
if extract.route == "vision" or unreliable_text:
```

   `_text_route_is_confident` (`marks.py:732-763`) is False when the declared total differs from the read total by more than `max(2.0, 2%)` or any non-context row lacks marks. `extract_paper` returns `route="vision"` for scans (`backend/app/extraction/paper.py:490`, fewer than 25 characters per page with images).
6. Vision: sets `assessment.route="vision"`, inserts `paper_scan_job` with the PDF bytes, queues `_run_paper_scan_job`, returns 202. Text: `_finish_paper_scan` inline, then the auto pipeline if enabled (`marks.py:1136-1165`).

**Vision job (`_run_paper_scan_job`, `marks.py:940-1063`).** Rasterises the PDF (JPEG quality 85, long edge about 1568 px, DPI 100–220, `paper_vision.py:447-472`), calls `read_paper_vision(..., model=settings.model_high_stakes, page_concurrency=settings.vision_page_concurrency)`, re-runs `check_paper_subject` on the result, re-reads the job `FOR UPDATE` and writes only if still pending, calls `_finish_paper_scan`, then the auto pipeline.

**Model call (`AnthropicPaperVisionReader._read_page`, `backend/app/extraction/paper_vision.py:217-269`).**
- Model `claude-opus-5` (`config.py:82`). `max_tokens=16000`. **No effort parameter** is passed. Structured output `output_format=_PaperOut`.
- One call per page, up to 4 pages concurrently (`vision_page_concurrency=4`, `config.py:93`; `paper_vision.py:308`).
- Images per call: page 0 sends its own image; page *i*>0 sends `PREVIOUS_PAGE_NOTE`, the previous page's image, the line "That was the previous page, for context only. Below is the page to actually read:", the current image, then the per-page prompt.
- Per-page prompt (`paper_vision.py:304`): `"Read every question on this page, in order."`
- **Retries: none in this code.** `anthropic.APIStatusError` becomes `RuntimeError("(status) message")`, recorded as a per-page problem (`paper_vision.py:260-268, 319-322, 371-373`). The SDK client is built without `max_retries` (`paper_vision.py:213`), so SDK defaults may apply (**UNKNOWN**).
- A page whose output fails validation surfaces the same way; a paper with no questions at all is `refused` and the job fails 422.

Output schema (`paper_vision.py:46-74`):

```python
class _QuestionOut(BaseModel):
    section: str = ""
    question_no: str
    sub_part: str = ""
    choice_alt: str = ""
    max_marks: float | None = None
    stem_text: str = ""
    logical_page: int = 1
    is_context: bool = False
    attempt_required: int = 0

class _DeclaredOut(BaseModel):
    sections: dict[str, float] = {}
    question_count: int | None = None
    total_marks: float | None = None

class _PaperOut(BaseModel):
    questions: list[_QuestionOut] = []
    declared: _DeclaredOut = _DeclaredOut()
```

SYSTEM prompt (`backend/app/extraction/paper_vision.py:77-160`):

```text
You are reading a scanned or photographed CBSE question paper -- a picture of a page, not a text document -- in any of the languages CBSE Class X sets one in (English, Hindi, Tamil, or a bilingual paper printing both). 

GUARDRAIL, more important than completeness: this paper is being read to build a school's official record of marks. A confident wrong answer is worse than an honest gap. Never invent, estimate, or round a value you cannot actually see. Every number and every word of stem text must be traceable to ink on the page. If a mark, a question number, or any other field is not legible, leave it blank -- do not fill it in from what a typical CBSE paper usually has. Do not let familiarity with common paper patterns substitute for what THIS paper actually shows.  

Extract every question in the order it is printed: its section letter if the paper has sections (A, B, C...), its question number, a sub-part letter if it has one (i, ii, iii or a, b, c), an internal-choice letter if this is the alternative offered after the word OR (the first of a pair is blank, the alternative is 'b'), how many marks it is worth, its stem text (the question exactly as printed, transliterated faithfully if not in English -- never your summary or translation of it), and the page it is on. A bilingual paper prints each question twice, once in Hindi (or Tamil) and once in English -- extract only the English copy, never both, and never invent an English translation of a question that was only printed in the other language. A map-skill or other question sometimes carries a second printing right after it, introduced by a note such as 'The following questions are for the Visually Impaired Candidates only, in lieu of Q. No. 19' -- this restates the SAME sub-items in words instead of 'locate and label', worth the same marks, not a second, later part of the question and not additional sub-items. Extract only the original block's sub-items (the one the note is 'in lieu of'), exactly like the bilingual duplicate above -- never both printings, and never let seeing two blocks that reuse the same sub-item numbers (19.1, 19.2, ...) cause you to drop or truncate the original block's own items instead. A case-study or comprehension question prints a shared paragraph before several numbered sub-questions: extract that paragraph as its own row with is_context=true and no marks of its own; the marks belong to its sub-parts. Read marks exactly as printed (often in brackets at the right margin, like [2] or (3)) -- do not compute or guess a total. If a question's marks are not legible, leave max_marks blank rather than guessing. 

GROUP MARKS, a second printed shape and not a rarer version of the first: some questions print a numbered list of sub-items with NO mark label on any individual item, introduced instead by an instruction that names how many of them must be attempted -- 'answer any three of the following five', 'attempt any 2', or the same idea in Hindi or Tamil -- naming a required count that is LESS than how many items are actually printed. Near that instruction, the paper prints the group's own arithmetic once, in the form 'N x M = Total' (e.g. '3 x 1 = 3', '2 x 4 = 8'), where the first number is how many are required, the second is the per-item mark, and the third is their product -- do not confuse this with the required count from the instruction sentence, which is a separate number that may or may not equal the first number here. When you see this shape: read the per-item mark (the middle number of that printed expression) exactly as printed, the same no-computing discipline as any other mark, and set it as max_marks on EVERY sub-item in the list, not only the ones a student happens to attempt -- all of them are printed questions, each legitimately worth that many marks, and it is the later grouping logic's job to count only the required number of them once graded. Also set attempt_required on every sub-item in that list to the required count the instruction states -- never left as a guess, and never set at all if the instruction does not actually state a number smaller than how many items are printed. This is different from an internal choice ('answer (a) OR (b)'): there is no OR marker, and choice_alt stays blank on these rows -- use attempt_required for this shape, choice_alt for that one, never both on the same row. 

A third shape looks like the OR case but is not: the word OR (or its Hindi or Tamil equivalent) sits between two whole, separately numbered sub-items -- (i) ... OR ... (ii) ..., not two lettered options (a)/(b) inside one sub-item. choice_alt only applies when the alternative sits INSIDE a single sub-part (same question_no and sub_part, the first blank and the alternative 'b'); it cannot represent two different sub_part values. When OR instead separates two or more complete numbered/lettered sub-items, treat it exactly like GROUP MARKS above: set attempt_required to 1 (attempt one of them) on every sub-item joined by that OR, and its max_marks to the per-item mark from the group's own printed 'N x M = Total' (here N is 1). The presence of the word OR does not by itself mean choice_alt -- what matters is whether the alternative is a lettered option inside one sub-part, or a whole separate sub-item in its own right. 

Separately, read what the paper's own cover or instructions page declares about itself, if anything is printed there: the maximum marks for the whole paper (e.g. 'Maximum Marks: 80'), how many questions it contains (e.g. 'This question paper contains 38 questions'), and any per-section mark total (e.g. 'Section A: 20 marks', or 'This section comprises 6 questions of 3 marks each' -- multiply those two numbers together for that section's total). Leave any of these blank if the paper does not state it outright -- never calculate it yourself from the questions you extracted; it must be a number the paper itself prints.
```

PREVIOUS_PAGE_NOTE (`backend/app/extraction/paper_vision.py:169-182`):

```text
You are about to see two images: the page that came immediately before the one you are reading, then the page you are actually reading. The first is there ONLY so you can tell whether something on the second page continues from it -- an unlabelled lettered sub-part, a group's required-count instruction and its 'N x M = Total' arithmetic, a section header -- none of which may be restated on the second page even though it still applies there. Use the first image to fill in exactly those carried-over values (the same section, the same question number, the same attempt_required and per-item mark) on rows from the SECOND page when nothing on the second page itself states them and they clearly continue from the first. Do NOT extract any question rows from the first image itself -- it was already read on its own turn; a row belongs in your output only if the text you're transcribing it from is physically printed on the second image.
```

**Merging pages (`read()`, `paper_vision.py:333-437`).** Carries the last section, question number, `attempt_required` and group mark across pages. A row with a sub-part but no number inherits the last number; a row with neither is dropped and named in `problems`. `logical_page` is forced to the page index. Declared values: first non-null wins.

**Text route (`backend/app/extraction/paper.py`).** Regexes: `SECTION` captures only the letter (`:50`); `QUESTION` `^\s*(\d{1,2})\s*\.\s*(.*)$` left of 22% page width (`:52, 563`); roman `SUB_PART` (`:56`); lowercase `LETTERED_PART` (`:64`); `OR_MARKER` OR/अथवा/அல்லது (`:69`); declared total, section totals and question count (`:72-87`). Marks come from `mark_grammar.parse_label` in the margin band (`:430-441, 553-560`). Post-passes (`:631-637`): distribute sum marks, demote unmarked sub-parts, classify lettered parts, demote unpaired choices, resolve bilingual, inherit choice marks, mark context rows, check. Repeated page furniture is dropped (`:379-419`).

**Address format.** `ExtractedQuestion.address` (`paper.py:165-169`) and `Address.key` (`backend/app/extraction/address.py:63-75`) both build `"{section}/{question_no}/{sub_part}/{choice_alt}"` with empty strings for missing parts, e.g. `C/27//b`, `A/15/iii/b`. `sub_part` is a free `String(12)` (`backend/app/models/assessment.py:265`), so a vision value like `10.2` is stored as-is: `A/10/10.2/` (**INFERRED** from the prompt's mention of `19.1, 19.2`). Uniqueness: `uq_scanned_address`, `uq_question_address` (`assessment.py:258, 174`); collisions resolved before insert by `dedupe_addresses` (`paper.py:958-1030`).

**OR alternatives.**
- Convention: the first half of an OR pair has `choice_alt` blank, the alternative `"b"` (vision SYSTEM; text route `paper.py:613-619`). Lettered parts separated by OR may get `"a"`/`"b"` (`paper.py:744-747`).
- Totals count `choice_alt in (None, "a")` (`paper.py:209-211`; `marks.py:_scanned_effective_total`, 677-718).
- `group_choices` (`backend/app/extraction/choice.py:63-134`) buckets only rows with a truthy `choice_alt`, so a `None`/`"b"` pair forms no group (**INFERRED**).
- `choice_group_id` is set **only** by the Q-matrix import (`marks.py:500-506`). Questions created from a scan always have `choice_group_id = NULL`.

**Source/case-based parents.** `context_addresses` (`paper.py:925-945`): a row with no sub-part whose question number also has sub-part rows. Purely structural. Not a column; recomputed wherever needed. In map, context rows are skipped and their text is prepended to each sub-part's stem as `"{passage}\n\nQUESTION ON THE PASSAGE ABOVE:\n{stem}"` (`marks.py:2278-2294`).

**"Any N of M" (e.g. map sub-items "any five").** The vision prompt's GROUP MARKS rule sets `max_marks` to the per-item mark and `attempt_required` to N on every sub-item. Stored in `scanned_question.attempt_required` and copied to `question.attempt_required` (`marks.py:2449`). `group_choices` forms an attempt group with `marks = required * max(per_item)` (`choice.py:104-133`).

**`max_marks`.** Nullable on `scanned_question`, NOT NULL on `question`. Missing values are filled by `_fill_missing_marks` (`marks.py:1599-1668`): equal halves of a choice; else most common sibling mark; else the section's most common mark; else 1.0; each marked `edited_by="auto"`.

**Paper header and section titles.** Only `assessment.declared` (JSON) stores header facts: `{"sections": {letter: marks}, "question_count", "total_marks"}` (`marks.py:846-853`). `scanned_question.section` and `question.section` hold only the letter (`String(8)`). Both routes drop the title: the text route's `SECTION` regex captures only `([A-Z])` and `_declared` discards the title group (`paper.py:50, 447-450`); the vision schema has no title field. **A chapter named in a section header ("Section B — Geography: Minerals and Energy Resources") is not stored and not used anywhere.** The declared values are used only for confirmation totals and verification gates (`marks.py:1815-1839`; `backend/app/extraction/verification.py:85, 106, 150`).

**`blocked_reason`.** Every assignment in `marks.py`:

| Line | Value | Condition |
|---|---|---|
| 1513 | `None` | manual edit changed a field |
| 2332 | `None` | row is a context stem |
| 2336 | "no stem text was extracted, so there is nothing to place" | empty stem |
| 2340 | "no mark label was read; supply the marks before mapping" | `max_marks is None` |
| 2361 | "no chapter in the book matched this question" | retrieval found no chapter and the row is not a case-study sub-part |
| 2367-2370 | "{chapter} is not mapped to a board unit, so its marks have nowhere to count" | no `chapter_board_unit` row |
| 2400-2404 | "no concept family exists for {chapter}. Open the book screen…" | no families and `auto_pipeline` off |
| 2442 | `choice.blocked` | `choose_family` and `resolve_blocked_family` both failed and no auto family was made |
| 2501, 2580 | `None` | promoted |
| 2514 | "no chapter in the book matched this question" | deferred case-study sub-part with no sibling to borrow from |
| 2542-2544 | `choice.blocked` or "no concept family exists for {chapter}." | deferred row, no family |

**Status and tables.** `paper_scan_job` (`documents.py:317-345`): `status` pending → succeeded/failed, `error_status` 409/422/404/500, `progress_done/total`; a job pending more than 15 minutes is failed with 504 on poll (`marks.py:1177, 1194-1202`). `_finish_paper_scan` deletes unpromoted `scanned_question` rows and inserts the new ones; clears `assessment.scan_confirmed_at/by`; writes `route`, `pdf_page_count`, `source_sha256`, `declared`; stores `scan_document` + `scan_page` via `store_document` (`backend/app/api/documents.py:57-108`), replacing any previous document of the same kind. A scan never changes `assessment.status`.

### 2.4 Creating `question` rows

**Where.** `_map_paper` (`marks.py:2116-2583`), reached from `POST /assessments/{id}/map` or the zero-touch chain. The other creator is the Q-matrix import `POST /assessments/{id}/questions` (`marks.py:414-512`, admin only), which resolves codes to node ids, sets `choice_group_id`, writes `question_skill(source="import")`, and does not set `stem_hash`.

**Fields set by map** (`marks.py:2446-2457`):

| Column | Value |
|---|---|
| `chapter_id` | `_chapter_of(verdict.node_id)` — the retrieval winner (`marks.py:2352-2353, 1407-1417`) |
| `board_unit_id` | `units[chapter.id]` from `chapter_board_unit` for the assessment's version (`marks.py:2215-2220, 2365`) |
| `curriculum_section` | topic pick's section if any, else `verdict.section`, else the section in the landed node's code (`marks.py:2379-2382`) |
| `concept_family_id` | `choose_family` → else `resolve_blocked_family` (LLM) → else, zero-touch only, `_ensure_family` → else the row stays blocked (`marks.py:2398-2444`) |
| `concept_variant` | `stem_text[:200]` |
| `variant_hash` | `variant_hash(stem_text[:200])`, sha256 of the normalised stem (`backend/app/taxonomy/variants.py:33-34`) |
| `stem_hash` | `stem_hash(stem_text)` (`backend/app/ingest/book.py:220-221`) |
| `verified_against` | `"retrieval:{lexical|hybrid}"` |
| `choice_group_id` | not set |

`concept_family_id` is NOT NULL (`assessment.py:223`). **There is no placeholder family**: without a family no `question` row is created and the staged row stays blocked. The check constraint `(chapter_id IS NULL) = (curriculum_section IS NULL)` applies (`assessment.py:178-181`).

**Resolving `X.SST` into the four books.**
- The four SST curricula share `group_code="X.SST"` (`backend/app/curriculum/__init__.py:152-223`); `group_subjects` returns all four (`__init__.py:553-569`).
- `_SST_SECTION_SUBJECT = {"A": "X.HIST", "B": "X.GEO", "C": "X.POL", "D": "X.ECO"}` (`marks.py:1435`) is a fixed convention, not read from the paper.
- Map: when the paper is in the SST group, each row with a mapped section letter is retrieved against that subject's own index (`_indexes_for_subject`, `marks.py:2186-2212, 2344-2350`); otherwise against the whole group.
- Place: `own_scope[q.id]` = that subject's chapter labels, passed as `scope_of` (`placement.py:323-343, 412`).

**Why the same paper exists as several assessments.**
- `POST /assessments` (`marks.py:91-162`) always inserts a new row; `assessment` has no unique constraint on subject, title, exam or file.
- `assessment.source_sha256` is written (`marks.py:845`) but never read anywhere in `backend/app`. `scan_document.sha256` is only used for storage; replacement is keyed on (assessment, kind), not on the hash (`documents.py:73-87`).
- Frontend `submitScan` (`frontend/lib/usePaperScan.ts:361-438`):

```ts
if (!id) {
  const created = await api.createAssessment(key, { subject_code: scanSubject, title: scanTitle });
  id = created.assessment_id;
  setAssessmentId(id);
}
```

  Every upload from the standalone panel on the papers list (shown only when no paper is open, `frontend/app/teacher/dashboard/page.tsx:518, 715-790`) creates a **new** assessment. Uploading from inside an open paper reuses it.
- A scan refused after creation (wrong subject, failed vision read) leaves an empty assessment behind; a retry from the list creates another (**INFERRED**).
- The offline-retry path stores the assessment id once created; if `createAssessment` succeeded server-side but its response was lost, the retry creates another (**INFERRED**).
- `_queue_auto_pipeline` (`marks.py:1707-1713`) creates a map/place job pair without checking `running_job`, so repeated scans of one assessment can queue duplicate pairs (**INFERRED**).

So re-uploading from the list screen creates a new assessment each time with no deduplication; re-scanning inside an open assessment replaces its staged rows and document.

### 2.5 The map job and the place job

| | Map (`kind="map"`) | Place (`kind="place"`, the classify step) |
|---|---|---|
| Route | `POST /assessments/{id}/map` (`marks.py:1933-1973`) | `POST /assessments/{id}/place` (`placement.py:761-833`) |
| Runner | `_run_map_job` → `_map_paper` (`marks.py:2043-2096, 2116-2583`) | `_run_placement_job` (`placement.py:159-758`) |
| Precondition | scan confirmed; staged rows; book chunks (`_map_inputs`, 1900-1930) | stems; Anthropic key; book chunks |
| Works on | staged rows with `question_id IS NULL` | every `question` of the assessment |
| Creates questions | yes | no |
| Model calls | none in zero-touch (topic deferred); topic judge on a manual map; `auto_resolve` when blocked | chapter judge, topic judge, `auto_resolve` |
| Writes | `question`, 1 `question_placement`, `question_skill` | 1 `question_placement`, 1 `question_tier`, `question_skill` per question per run |

**Jobs.** `PlacementJob` (`documents.py:348-389`): `kind` default `"place"`, `status` pending/succeeded/failed, `result` JSON, `error_status`, `error_detail`, `finished_at`, progress. Idempotency: `running_job(db, id, kind)` returns the newest pending job younger than the stale window and fails older ones with 500 "the job did not finish; the service restarted while it ran" (`marks.py:1976-2011`). Window: 45 minutes, or 4 hours when `batch_classify` is on (default). The place poll route does not check `kind` (`placement.py:836-860`).

**Zero-touch chain.** `auto_pipeline=True` by default (`config.py:128`). After a scan: `_queue_auto_pipeline` creates both job rows; `_run_auto_pipeline` (`marks.py:1716-1762`) runs `auto_confirm_scan`, then `_run_map_job`, then (if map succeeded) `_run_placement_job`; otherwise the place job is failed 409 with the map's reason. Because the place job is already pending while map runs, `_map_paper` sets `deferred_to_classify = running_job(db, id, "place") is not None` (`marks.py:2258`): no topic judge is built in map, retrieval's section stands, and every pick is replaced by `agreed=True, rationale="provisional: the classify step queued behind this map decides the topic"` (`marks.py:2302-2308`).

Place failure modes, all via `_finish_placement_job` (`placement.py:107-128`): 404 assessment missing; 409 no stems / no key / no book; 502 `place_paper` raised; 502 every question `judge_failed` ("the reading model could not be asked for any question, so nothing was changed"); 502 topic stage raised; 500 write phase raised.

#### 2.5.1 Hybrid retrieval (`backend/app/ingest/probe.py`)

- **Tokens** (33-59): `normalise(text).casefold()`, keep Unicode letter/mark runs, drop English `STOPWORDS` (27-30) and words of ≤2 characters.
- **Lexical** (`LexicalIndex`, 179-207): TF-IDF **dot product**, not BM25 and not cosine:

```python
score = sum(q[w] * tf[w] * math.log(self.n / (1 + self.df[w])) for w in q if w in tf)
if score > 0: Candidate(..., score / norm, section_number, text)
```

  `norm` is the square root of the chunk's token count. IDF ≤ 0 when a word appears in nearly every chunk; non-positive scores are dropped.
- **Semantic** (`SemanticIndex`, 149-176): only chunks with an embedding; the question is embedded with Jina (`retrieval.query`) and every chunk scored by cosine.
- **Fusion** (`locate`, 254-373): each index searched for `depth` (×3 when scoped) results; scope filter applied after search; **reciprocal rank fusion** with `RRF_K = 60` and no weights (`_rrf`, 239-251).
- **Chapter score:** per chunk node, sum of its top `CORROBORATION_DEPTH = 2` fused scores (236, 310-313). `score` = top chapter's score; `margin` = top minus runner-up.
- **`agreed`:** `len(ranked) > 1 and len({lst[0].node_id for lst in ranked}) == 1` — True only when lexical and semantic put the same chapter first. **With lexical only, `agreed` is always False.**
- **`section`:** within the top chapter, sum each section's top 2 fused scores; a dotted descendant with evidence wins over its parent (354-361).
- **`evidence`:** round-robin across the top `evidence_chapters` chapters, best first, up to `evidence_passages` (`_evidence_across`, 436-465). **`runners_up`:** next three chapters with scores.
- **Defaults:** `depth=12`, `evidence_passages=3`, `evidence_chapters=1`. Maximum `score` ≈ 0.065 hybrid (2/61+2/62), ≈ 0.0325 lexical (**INFERRED** arithmetic).
- **Filters:** `content_chunks` (118-131) keeps bucket T only (falls back to all if none) and drops chunks of fewer than 3 tokens. So exercises are excluded, while captions, boxes, activities, sources, glossary entries and map chunks (all bucket T for book-map subjects) are **included**.
- **`full_chapter_evidence`** (376-433): one best passage per section of a chapter, ranked by a fresh within-chapter lexical index; zero-score sections still included.
- **`retrieval_query_text`** (81-103): strips the Assertion–Reason lead-in and options from the retrieval query only; judges read the real stem.

Map calls `locate(retrieval_query_text(stem), row_indexes)` with defaults (`marks.py:2352`). **Map's `question_placement.confidence` is `verdict.score`** (`marks.py:2462`), i.e. this RRF chapter score, never above about 0.065.

#### 2.5.2 Chapter judge (place only)

**Evidence** (`_pass`, `backend/app/classify/pipeline.py:119-309`).
- `locate(query, indexes, depth=8, scope=q_scope, evidence_passages=8, evidence_chapters=E)` where `classifier_evidence_passages=8` and `E = min(3 × books, 9)`: 3 for one book, 9 for SST's four (`placement.py:394-397`).
- `own_evidence = full_chapter_evidence(winner)` (one passage per section of the winning chapter) plus `rival_evidence` (retrieval passages from other chapters).
- Each passage truncated to 1200 characters, or `max(300, 12000 // n)` when there are more than 10 (`_adaptive_passage_chars`).
- A question with no evidence at all gets no slot and no placement or tier row (**INFERRED**).
- Scope: `q_scope = (scope & own_scope or own_scope) if scope else own_scope` (152-155). If scoped retrieval returns nothing, it retries unscoped and sets `out_of_scope=True`; the primary option's confidence becomes 0.0 (162-170, 263-274).

**Call** (`backend/app/classify/anthropic_judge.py:69-99`). `claude-sonnet-5` (`model_classifier`, `config.py:103`), effort `medium` (`config.py:108`) via `output_config` (`backend/app/llm.py:20-52`), `max_tokens=16000`, `output_format=Classification`, **no `cache_control`**, **no retries** in code. Live by default; batched only if `batch_classify` and `batch_chapter_judge` (default False, `config.py:112-121`; `placement.py:315`). When batched, all questions are asked at once from up to 64 threads (`pipeline.py:214-225`).

**Parse failures.** Any exception (API error, validation error including a missing `confidence`) becomes `Classification(chapter=None, ..., reasoning="the reading model's answer for this question was invalid ({exc}) -- needs a person.", confidence=0.0)`, the question is marked `judge_failed`, and its slot is `[Option(None, None, 0.0)]` (`pipeline.py:234-259`). In the write phase a `judge_failed` question keeps its mapped chapter and gets a flagged placement row (`placement.py:501-514`).

**Schema** (`backend/app/classify/judge.py:29-60`): `chapter: str | None` (required); `curriculum_section: str | None = None`; `tier: str | None = None` (one of the three TIERS); `skill_required: str` (≤400); `reasoning: str` (≤600); `evidence: list[str] = []`; `confidence: float` (0–1, **required**); `alternative_chapter: str | None = None`. `TIERS = ("Remembering & Understanding", "Applying", "Analysing, Evaluating & Creating")` (`judge.py:26`).

SYSTEM prompt (`backend/app/classify/judge.py:71-124`):

```text
You place CBSE Class X questions in the NCERT textbook.

You are given a question and passages retrieved from the book. Decide which chapter the
question belongs to, using only the chapters present in the passages -- never a chapter
you were not shown, even if you believe it fits better.

You have three honest answers, not two:

1. The question is ABOUT something in one of the candidate chapters (a theorem, a
   character, a grammar rule, a poem's theme). Pick that chapter.
2. The question is content-anchored -- it is clearly testing something from the book --
   but you cannot tell which of several candidate chapters from the evidence shown. Pick
   the closest one and say so in your reasoning, with confidence below 0.7 and the other
   candidate in alternative_chapter. This is still "the question is about a chapter",
   just an uncertain guess at which one.
3. The question is SKILL-ANCHORED: it has no content tie to any specific chapter because
   it is testing a general writing or language skill against a prompt invented for this
   paper -- a letter to a named recipient, an essay from a given outline, an unseen
   passage or picture composition, a notice or dialogue-writing task, a "rewrite in your
   own words" with no source text from the book. For these, set chapter to null and put
   what the student has to DO in skill_required (e.g. "write a formal letter requesting
   library books", "compose a narrative from a picture prompt"). This is a confident,
   correct answer, not a hedge: do not use a low confidence just because chapter is null,
   and do not force a chapter onto it merely because a passage was retrieved -- retrieval
   often returns the closest-sounding passage even when nothing in the book is what the
   question is actually asking for.

Case 3 is narrow. It is for a task that would be exactly the same question on a different
paper testing a different chapter -- the skill is what is being tested, not the content.
It is NOT an excuse to null out a question you are merely unsure about, or one that draws
on a specific chapter's vocabulary, characters, or grammar point even loosely -- that is
case 2. When in doubt whether a question has a content tie at all, prefer case 2: a
low-confidence guess that names real evidence is more useful to a teacher than an
abstention that turns out to have been avoidable.

Judge what the question ASKS, not which words it shares with a passage. A question about a
theorem is not the theorem. A question that asks which statement is NOT true is testing the
condition being violated. A question mentioning height and a right angle is not necessarily
trigonometry -- a cone's slant height is mensuration.

For the competency tier, use CBSE's own three:
- "Remembering & Understanding" -- recall a fact, state a definition, apply a formula the
  way it was taught
- "Applying" -- use a taught method in a situation that needs setting up first
- "Analysing, Evaluating & Creating" -- compare, justify, prove something not proved in the
  book, or work backwards from a result

Confidence is your own honest estimate that a CBSE teacher would agree with your answer --
the chapter you picked, or, for a null chapter, that the question really is skill-anchored
with no chapter to name. Use below 0.7 whenever a content-anchored question could
reasonably sit in another chapter, and name that chapter in alternative_chapter. A
low-confidence content guess costs a teacher a minute's review; a confident wrong chapter
goes into a report and is acted on -- and forcing a chapter onto a skill-anchored question
is exactly that failure, just dressed up as a guess.
```

User prompt template (`backend/app/classify/judge.py:127-147`):

```python
def build_prompt(
    question: str, evidence: list[Evidence], passage_chars: int = 1200
) -> str:
    """The question, and the book passages retrieval found for it."""
    chapters = sorted({e.chapter for e in evidence})
    lines = [
        "QUESTION",
        question.strip(),
        "",
        f"CANDIDATE CHAPTERS (choose exactly one): {', '.join(chapters)}",
        "",
        "PASSAGES FROM THE BOOK",
    ]
    for i, e in enumerate(evidence, 1):
        section = f" (section {e.section})" if e.section else ""
        # truncated: a whole exercise runs to 8500 characters and the useful signal is at
        # the start, while the tail is later questions that would pull the judge off
        lines.append(
            f"\n[{i}] {e.chapter} -- {e.reference}{section}\n{e.text[:passage_chars]}"
        )
    return "\n".join(lines)
```

**Grounding** (`backend/app/classify/grounding.py:43-113`). A chapter not among those offered is replaced by the alphabetically first offered chapter with confidence 0.0; a tier not exactly one of the three is cleared; a section not in `known_sections[chapter]` is cleared; cited references not shown are removed; **any violation caps confidence at `min(confidence, 0.4)`** (`grounding.py:107-108`). `known_sections` merges subtopic node codes and `book_chunk.section_number` per chapter (`placement.py:280-301`).

**Options and reconcile** (`pipeline.py:276-307`; `backend/app/classify/reconcile.py`). Each question's options: the judge's chapter at its confidence; then up to three retrieval runners-up at `max(0.05, call.confidence * 0.4)` (`pipeline.py:293`); then `alternative_chapter` at `call.confidence * 0.8`. Note these two use `call.confidence`, not the zeroed out-of-scope confidence. With no declared blueprint, `reconcile` takes each question's best option; with a blueprint it does a greedy swap search (≤200 swaps). `overruled` lists moved questions (source `"blueprint"`).

**Scope inference.** If no scope is declared (`syllabus_scope` unset) and `infer_scope_when_undeclared` (default True), `place_paper` infers a chapter set from the first pass (`backend/app/classify/scope.py`: ≥2 questions, ≥10% of marks, vote confidence ≥0.60, paper ≥8 questions, 80% mark coverage) and, if confident, **runs a second full pass** of chapter-judge calls (`pipeline.py:356-380`).

**How the choice is applied.** `PlacedQuestion.chapter`, `board_unit` and `confidence` come from the reconcile assignment; `curriculum_section`, `tier`, `skill_required`, `reasoning` and `evidence` come from the judge (`pipeline.py:353-369`).

#### 2.5.3 Topic judge

**Where it runs.** In place for every question with a chapter (`placement.py:436-478`); in map only when no classify job is queued (manual map). `TopicJudge` in `backend/app/classify/topic.py`, `claude-sonnet-5`, effort `medium`; in place it is batched by default (`batched=settings.batch_classify`, `placement.py:361-365`), fanning out over up to 64 threads so each round becomes one batch.

**What it reads.** Whole-chapter mode when the judge supports it and the chapter document is ≤ `FULL_CHAPTER_MAX_CHARS = 250_000` (`topic.py:206`): `chapter_document()` (238-256) lays out every section as `## SECTION {n}  {heading}` followed by its chunk texts (sorted by reference length, reference, id). Sections with no chunks are skipped; chunks with no `section_number` (introductions, exercises) are not included. Otherwise sampled mode: retrieval passages, term-evidence chunks and one passage per section.

**Retrieval and term votes inside the chapter** (`choose_topic`, `topic.py:536-733`).
- `locate(query, [lexical over the whole section-tagged pool, semantic over the chapter], depth=8, scope={chapter_id}, evidence_chapters=1)` → `retrieval_section`.
- `distinctive_terms` (455-478): multi-word capitalised phrases, mid-sentence capitalised words not in a stock list, quoted strings of 6–80 characters, four-digit years. `term_evidence` (481-508) keeps terms found in 1–2 sections; `term_vote` (511-519) returns a single section when all single-section votes agree; `named` is that section.

**Whole-chapter flow (`_choose_from_whole_chapter`, `topic.py:744-902`).**
1. Read 1, `mode="answer"`; Read 2, `mode="taught"`. Independent calls on the same cached chapter.
2. `anchor()`: the section that contains the quoted sentence(s) (≥12 characters, normalised) overrides the number the model wrote unless the two are parent/child.
3. `section = answer_sec or taught_sec`; if neither, fall back.
4. Claimants: `section`, `taught_sec`, `named`, and `retrieval_section` only when `named` is None, each only if unrelated to the others.
5. If more than one claimant: a confirm read restricted to them (`candidates`).
6. `agreed` = single claimant, or the confirm sided with `section` and `named` does not contradict it.
7. Verification (`_verify`, 909-987): `answerable(section)` must return true with a quote that sits under that section or its sub-sections; else each other claimant is checked; else one relocating read with the failed sections excluded, which must also verify; else "no section of the chapter answers this question from its own text; the section that comes closest was kept" and `agreed=False`.
8. `secondaries`: up to three sections from the answer read's `also`, unrelated to the primary.

**Calls per question (INFERRED by tracing).** Minimum 2; typical 3 (two reads + verify) or 4 (+ confirm); maximum 8 (2 reads + confirm + verify primary + 2 other claimants + relocate + verify relocated). Sampled mode: 1–2. There is no self-consistency voting beyond the two independent reads and the confirm.

**Fallback.** No judge, or both reads abstain: `fallback_section` (place: the chapter judge's grounded section; map: retrieval's section) if it is a real heading, with `agreed` true when retrieval agrees; else retrieval's section with `agreed=False` (`topic.py:611-624`).

**Prompt caching.** The second system block (the chapter text) carries `cache_control: {"type": "ephemeral"}` (`topic.py:291-309`), shared by every read of the same chapter. This is the only `cache_control` in the pipeline.

**Schemas** (`topic.py:84-135`).

```python
class _TopicChoice(BaseModel):
    section: str            # "exactly one section number from the list offered, e.g. '1.2', or the literal 'none' ..."
    rationale: str          # max_length=400
    quote: str = ""
    answer: str = ""        # max_length=600
    quotes: list[str] = []
    also: list[str] = []    # other sections a part of the question is answered in (up to three)

class _Answerability(BaseModel):
    answerable: bool
    quotes: list[str] = []
    reason: str             # max_length=300
```

Whole-chapter SYSTEM prompt `_DOCUMENT_SYSTEM` (`backend/app/classify/topic.py:208-235`):

```text
You place one CBSE Class X exam question under the ONE section of its
NCERT textbook chapter that it tests. The chapter has already been decided; do not question
it. The COMPLETE text of the chapter follows, laid out section by section under numbered
headings. Read it. Then answer with the number of the section whose text contains what the
question tests, and copy that sentence, verbatim, into `quote`.

Rules:
- The section is where the question is ANSWERED, not where its subject is mentioned. A
  question that names a thing (a nuclear plant, a law, a book) but asks what, where, why
  or how belongs where the chapter teaches that answer -- a nuclear plant's location is
  taught where nuclear energy is taught, measures against a problem are taught where the
  remedies are listed, not where the problem is named. Quote the sentence that answers.
- A sub-question of a passage-based (source-based) question is about the passage's
  subject: place it where the chapter discusses what the passage discusses.
- A map-skill or locate-and-label item belongs to the section that teaches the thing
  being located.
- Prefer the most specific section: a sub-section (2.2) beats its parent (2) when the
  sentence you quote is under the sub-section's heading.
- A question with several parts answered in different places (a chronology to arrange,
  columns to match, statements to judge true or false, a source with sub-questions on
  different things) belongs to the section that answers MOST of it. When its parts fall
  under different sub-sections of ONE parent section, answer with that parent. List every
  other section a part is answered in under `also` -- only sections a part is actually
  answered in, never one that merely mentions the subject. A single-part question leaves
  `also` empty.
- Map work, figures, tables and captions are part of a section's text. A place shown
  only on the map for a section is answered by that section.
- Answer 'none' only when no section of the chapter contains what the question tests.
```

Cached system blocks (`backend/app/classify/topic.py:291-309`):

```python
    def _document_system(self, chapter_label: str, headings: dict[str, str], document: str) -> list:
        """The cached prefix every read of one chapter shares: identical bytes for every
        question, every mode and every check, so it is written to the cache once."""
        section_list = "\n".join(
            f"- {n}  {h}" if h and h != n else f"- {n}" for n, h in headings.items()
        )
        return [
            {"type": "text", "text": _DOCUMENT_SYSTEM},
            {
                "type": "text",
                "text": (
                    f"CHAPTER: {chapter_label}\n\nSECTIONS\n{section_list}\n\n"
                    f"FULL TEXT OF THE CHAPTER\n\n{document}"
                ),
                # the chapter is identical for every question on it: written to the
                # cache once, read back at a fraction of the price for the rest
                "cache_control": {"type": "ephemeral"},
            },
        ]
```

Whole-chapter reads, including every `ask` string (`backend/app/classify/topic.py:311-368`):

```python
    def pick_from_document(
        self, stem: str, chapter_label: str, headings: dict[str, str], document: str,
        candidates: dict[str, str] | None = None, mode: str = "answer",
        exclude: dict[str, str] | None = None,
    ) -> _TopicChoice:
        """Read the whole chapter (a cached prefix shared by every question on it) and
        name the section whose text holds what the question tests.

        ``mode`` "answer": write the model answer first, from the chapter only, and quote
        the sentences it is drawn from -- the section is where the question is answered.
        ``mode`` "taught": the plainer reading, where is this taught. The two are asked
        independently and compared. ``candidates`` narrows the answer to a few sections
        for a confirm pass; ``exclude`` names sections already checked and found NOT to
        answer the question, for a relocating read. The document is the same in every
        case, so the cache still hits."""
        extra = {"output_config": self.output_config} if self.output_config else {}
        if mode == "answer":
            ask = (
                "First write, in `answer`, the answer a student would give to this "
                "question using only the chapter above (one to three sentences). Then copy "
                "into `quotes`, verbatim, the sentence or sentences of the chapter your "
                "answer is drawn from (up to three). `section` is the section those "
                "sentences are in. If a part of the question is answered in a different "
                "section, list that section in `also`."
            )
        else:
            ask = (
                "Which section number does this question belong to? Copy the sentence that "
                "contains what it tests into `quote`, verbatim from the chapter above."
            )
        if candidates:
            ask = (
                "Earlier readings disagreed. Decide between ONLY these sections: "
                + ", ".join(f"{n} ({h})" for n, h in candidates.items())
                + ". Which one's text ANSWERS the question, not merely mentions its "
                "subject? Write the answer in `answer`, and copy the sentence(s) it is "
                "drawn from into `quotes`, verbatim from the chapter above."
            )
        if exclude:
            ask = (
                "The text of "
                + ", ".join(f"section {n} ({h})" for n, h in exclude.items())
                + " was checked and does NOT answer this question. Which OTHER section's "
                "text does -- including its map work, figures, tables and captions? Write "
                "the answer in `answer`, copy the sentence(s) it is drawn from into "
                "`quotes`, verbatim from the chapter above, and answer 'none' if no other "
                "section answers it."
            )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=self._document_system(chapter_label, headings, document),
            messages=[{"role": "user", "content": f"QUESTION\n{stem.strip()[:3000]}\n\n{ask}"}],
            output_format=_TopicChoice,
            **extra,
        )
        self._count(response)
        return response.parsed_output
```

Answerability check (`backend/app/classify/topic.py:370-398`):

```python
    def answerable(
        self, stem: str, chapter_label: str, headings: dict[str, str], document: str,
        section: str, sub_sections: list[str] | None = None,
    ) -> _Answerability:
        """Can ``section``'s text, read alone, answer the question? The verification that
        catches a section which names the question's subject without answering it --
        the same cached chapter, one short answer."""
        extra = {"output_config": self.output_config} if self.output_config else {}
        heading = headings.get(section, "")
        where = f"SECTION {section}" + (f" ({heading})" if heading and heading != section else "")
        if sub_sections:
            where += " together with its sub-sections " + ", ".join(sub_sections)
        ask = (
            f"Read ONLY the text under {where} in the chapter above -- its body, boxes, "
            "map work, figures, tables and captions. Could a student answer this question "
            "fully from that text alone? Set `answerable` true only if that text itself "
            "states what the question asks for; naming the same subject is not enough. If "
            "true, copy the sentence(s) that answer it into `quotes`, verbatim."
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=2000,
            system=self._document_system(chapter_label, headings, document),
            messages=[{"role": "user", "content": f"QUESTION\n{stem.strip()[:3000]}\n\n{ask}"}],
            output_format=_Answerability,
            **extra,
        )
        self._count(response)
        return response.parsed_output
```

Sampled-mode SYSTEM prompt `_SYSTEM` (`backend/app/classify/topic.py:138-162`):

```text
You place one CBSE Class X exam question under the ONE section of its NCERT
textbook chapter that it tests. The chapter has already been decided; do not question it.

You are given every section of that chapter, numbered, with the book's own heading for
each, and passages from the book. Answer with exactly one section number copied from the
list. Judge what the question ASKS, not which words it shares with a passage: a question
about the functions of political parties belongs under the section whose heading names
functions, even if a later section on reform mentions functions in passing.

Rules:
- The section is where the FACT the question tests is written, not the heading that
  sounds most like the question. A question about the Index of Prohibited Books belongs
  to the section whose text mentions the Index, even if another section's heading is
  "the Fear of Print". Copy that sentence into `quote`, verbatim, from the passage shown.
- Prefer the most specific section that is genuinely about the question. A sub-section
  (2.2) beats its parent (2) when the question is about that sub-section's subject; the
  parent is right only when the question spans its children or is about the parent's
  own introductory text.
- A sub-question of a passage-based (source-based) question is about the passage's
  subject: place it where the book discusses what the passage discusses.
- A map-skill or one-line locate-and-label item belongs to the section that teaches the
  thing being located (a coal mine goes under the coal section, not the chapter intro).
- Answer 'none' only when the question fits no listed section at all. A confident wrong
  section is filed as fact and misleads every report grouped by topic, but so is a
  needless 'none': it hands the choice back to word-overlap search.
```

Sampled-mode user prompt (`backend/app/classify/topic.py:165-184`):

```python
def _prompt(
    stem: str, chapter_label: str, headings: dict[str, str],
    passages: list[Candidate], passage_chars: int,
) -> str:
    lines = [
        f"CHAPTER: {chapter_label}",
        "",
        "QUESTION",
        stem.strip()[:3000],
        "",
        "SECTIONS OF THIS CHAPTER (answer with exactly one number)",
    ]
    for number, heading in headings.items():
        lines.append(f"- {number}  {heading}" if heading and heading != number else f"- {number}")
    lines.append("")
    lines.append("PASSAGES FROM THE BOOK")
    for i, c in enumerate(passages, 1):
        where = f" (section {c.section})" if c.section else ""
        lines.append(f"\n[{i}] {c.reference}{where}\n{c.text[:passage_chars]}")
    return "\n".join(lines)
```

Sampled-mode call (`backend/app/classify/topic.py:400-417`):

```python
    def pick(
        self, stem: str, chapter_label: str, headings: dict[str, str],
        passages: list[Candidate],
    ) -> _TopicChoice:
        extra = {"output_config": self.output_config} if self.output_config else {}
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=8000,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": _prompt(stem, chapter_label, headings, passages, self.passage_chars),
            }],
            output_format=_TopicChoice,
            **extra,
        )
        self._count(response)
        return response.parsed_output
```

**Where a confidence of 0.4 comes from.** It cannot come from the model omitting confidence: `confidence` is required with bounds, so an omission fails validation and the question becomes `judge_failed` with 0.0. Map rows never carry 0.4 (their confidence is the RRF score). On a place row, 0.4 arises from:
1. **Grounding cap** (`grounding.py:107-108`): the judge returned ≥0.4 and any violation occurred — most often a `curriculum_section` not in `known_sections`, or a cited reference that was not shown. These appear in the place job's `grounding_violations`.
2. **Runner-up option** (`pipeline.py:293`): a runner-up chosen when the judge's confidence was 1.0 gives `max(0.05, 1.0 × 0.4) = 0.4`. That happens when a blueprint overrules (source `"blueprint"`) or when an out-of-scope primary was zeroed and a runner-up outranked it (source `"model"`).
The value is also written to `question_skill.confidence` and `question_tier.confidence` (`placement.py:595, 657-664`).

#### 2.5.4 Family resolution

`choose_family` (`backend/app/mapping/family.py:51-115`), verbatim logic:

```python
if not candidates:
    return Choice(None, blocked=(
        f"no concept family exists for {chapter_label}. Open the book screen for "
        f"this subject and create the families it proposes."))
claimants = [f for f in candidates if section and section in sections_of.get(f.code, set())]
if len(claimants) == 1:
    return Choice(claimants[0])
if claimants and prefer_label:
    named = [f for f in claimants if alike(f.label, prefer_label)]
    if len(named) == 1:
        return Choice(named[0])
    if named:
        claimants = named
if claimants:
    return Choice(
        min(claimants, key=lambda f: (len(sections_of.get(f.code, ())), f.code)),
        unsettled=(
            f"{len(claimants)} families of {chapter_label} draw on section {section}; "
            f"the narrowest was taken and a person should settle it"))
if len(candidates) == 1:
    return Choice(candidates[0])
return Choice(None, blocked=(
    f"{len(candidates)} families exist for {chapter_label} and none claims "
    + (f"section {section}, which is where the book puts this question" if section
       else "a section, and the passages that matched name no section either")
    + ". Settle it in review, or re-create the families from the book so each "
    "one records the section it covers."))
```

`alike()` (`family.py:43-48`) lowercases, strips a leading number, keeps `[a-z]+` words, and is true when either word string contains the other. `prefer_label` is the topic pick's heading.

**`resolve_blocked_family`** (`backend/app/mapping/auto_resolve.py:194-238`; any exception → None):
- Stage 0, no model call (`semantic_family_choice`, 253-344): needs a Jina key; scores each family by its best chunk cosine within the sections it alone claims; returns the winner if it leads by ≥ `SEMANTIC_FAMILY_MARGIN = 0.08`.
- Stage 1: chunks whose `section_number` equals the question's section, filtered by subject codes but **not by chapter** (432-437), joined and sent to `_ask`. A failed quote check or `"none"` returns None without trying stage 2.
- Stage 2: lexical top 3 plus semantic top 3 over the chapter's chunks, formatted `"[ref] text"`, sent to `_ask`; `book_section` is the section of the passage containing the quote.
- `_ask` (176-191): `messages.parse(model=settings.model_classifier, max_tokens=4000, system=_SYSTEM, output_format=_FamilyChoice, effort via output_config)`. Live, never batched, no caching. The quote must be a real substring of the passages after whitespace/lowercase normalisation, else None.
- Schema `_FamilyChoice` (80-89): `family_code` (an offered code or `'none'`), `rationale`, `quote`.
- The winner's section is recorded via `record_family_section(source=f"auto_resolve_{grounded_in}")`.

SYSTEM prompt (`backend/app/mapping/auto_resolve.py:92-103`):

```text
You are placing one exam question under the concept family it tests. You are given the question itself, one or more real passages from the textbook chapter it belongs to, and a list of candidate families already proposed for this chapter. Pick the family whose label the passages show this question is actually about. Quote the exact words of the PASSAGES (not the question) that justify your choice; do not paraphrase or invent wording, and do not reason from anything you recall about this textbook beyond what is shown below. If more than one family could fit, or none clearly does, or the passages do not actually settle it, say so honestly by answering 'none' -- a wrong placement is filed as fact and silently misleads every future report grouped by this family.
```

User prompt (`backend/app/mapping/auto_resolve.py:115-121` and `124-140`):

```python
def _candidate_lines(candidates: list[TaxonomyNode], sections_of: dict[str, list[str]]) -> list[str]:
    lines = []
    for c in candidates:
        covers = sections_of.get(c.code) or []
        covers_note = f" (already covers section(s) {', '.join(covers)})" if covers else ""
        lines.append(f"- {c.code}: {c.label}{covers_note}")
    return lines

def _prompt(chapter_label: str, stem_text: str, passages: str,
            candidates: list[TaxonomyNode], sections_of: dict[str, list[str]]) -> str:
    return "\n".join([
        f"Chapter: {chapter_label}",
        "",
        "Question:",
        stem_text[:2000],
        "",
        "Passages from the book:",
        passages[:6000],
        "",
        "Candidate families:",
        *_candidate_lines(candidates, sections_of),
        "",
        "Which family code does this question belong to? Quote the exact words of the "
        "PASSAGES that justify it. Answer 'none' if they don't clearly settle it.",
    ])
```

**`_ensure_family`** (map only, zero-touch only): see 2.2.4. Place has no such fallback; a family it cannot resolve leaves the question untouched and counts as `family_refused`.

#### 2.5.5 Writing results

`QuestionPlacement` (`backend/app/models/assessment.py:319-353`, append-only): `question_id`, `chapter_id`, `board_unit_id`, `curriculum_section` (String 32), `tier` (String 48), `skill_required` (String 400), `confidence`, `source` ('model' | 'blueprint' | 'scope' | 'human'), `needs_review`, `reviewed_by`, `reasoning` (**String 1000**), `evidence` (JSON), `candidates` (JSON), `created_at`.

**Rows per question.**
- Map: **one** row at creation (`marks.py:2460-2490`): `confidence=verdict.score`, `source="model"`, reasoning `"{mode} retrieval, margin {m:.3f}. Topic {s} ({h}): {rationale}. {ambiguous}. Auto-resolved: …"`, `evidence` = up to 6 retrieval references, `candidates` = up to 4 runner-up chapter labels, no tier. Deferred case-study rows: one row with confidence 0.0, `needs_review=True` (`marks.py:2562-2572`).
- Place: **one** row per question per run (`placement.py:624-653`): chapter, section (topic pick's section when present), tier text, skill, `confidence=placed.confidence`, `source="blueprint" if overruled else "model"`, reasoning = judge reasoning + "Topic {s} ({h}): {rationale}" + family messages + auto-resolve text, `evidence` = grounded references, `candidates=[chapter]`.
- Human settle: one row, confidence 1.0, `source="human"`, `needs_review=False` (`placement.py:1054-1067`).

So a question typically has two rows after zero-touch (map + place), three or more after a re-run or a review. **The newest row (by `created_at`) is the one the screen reads** for the review flag and explanation (see 2.7).

**When the `question` row changes.**

| When | `chapter_id` | `curriculum_section` | `concept_family_id` | Source of the value |
|---|---|---|---|---|
| Map, at creation | retrieval winner | topic pick, else retrieval | `choose_family` / auto | map's own computation (equals the map placement row) |
| Place, judge failed | unchanged | unchanged | unchanged | — (placement row flagged) |
| Place, skill-anchored (`chapter is None`) | set NULL | set NULL | unchanged | judge |
| Place, settle with family and section | reconcile chapter | topic pick, else judge | chosen family | the place placement row's values |
| Place, family found but no section | unchanged | unchanged | **changed** | — (**INFERRED** mismatch possible) |
| Place, no family | unchanged | unchanged | unchanged | — (`family_refused`) |
| Human confirm | body chapter | body or existing | body family if given | the human placement row |

(`placement.py:483-611, 990-1132`.)

**Topic rows (`question_skill`).** Map inserts `QuestionSkill(source="retrieval")` at weight 1.0 directly, plus secondaries at `SECONDARY_WEIGHT = 0.5` (`marks.py:2494-2498, 2099-2113`). Place and review call `set_question_topic` (`backend/app/mapping/topic_node.py:140-183`): primary weight 1.0, secondaries 0.5; earlier machine rows (`retrieval`, `model`, `classify`) are replaced; if a non-machine row exists and the caller is not human, nothing changes.

#### 2.5.6 Review flag

Map (`marks.py:2469-2474`):

```python
needs_review=(
    not verdict.agreed
    or (pick.section is not None and not pick.agreed)
    or ambiguous is not None
    or (auto_resolved is not None and not pick.agreed)
),
```

With lexical-only retrieval `verdict.agreed` is always False, so **every map row is flagged when chunks have no embeddings**. Deferred case-study rows: always True.

Place (`placement.py:633-641`):

```python
needs_review=(
    placed.needs_review
    or (pick is not None and pick.section is not None and not pick.agreed)
    or choice.unsettled is not None
    or choice.blocked is not None
    or (auto_resolved is not None and not (pick is not None and pick.agreed))
),
```

`placed.needs_review` comes from `needs_a_human` (`reconcile.py:204-232`): chosen option confidence < 0.70, or overruled by the blueprint, or option margin < `CHAPTER_OPTION_MARGIN = 0.12`; an infeasible blueprint flags every question. The `judge_failed` branch forces True. Human: False.

#### 2.5.7 Chapter scope

**The chapter named in a paper's section header is not used.** Only the section letter is stored (2.3), and nothing reads a chapter name from a header. What limits scope today:
1. `assessment.syllabus_scope` (JSON chapter codes; `assessment.py:125-133`), set at creation (`marks.py:135-158`) or via `PUT /assessments/{id}/scope` (`placement.py:76-104`). **Only place uses it** (`placement.py:319-321`); map's `locate` call takes no scope.
2. The SST section letter → subject mapping (map: per-subject index; place: `own_scope`).
3. Subject/group restriction of chunks and chapters (`group_subjects`, `placement.py:253, 863-886`).
4. Scope inference in place when nothing is declared.
5. The topic judge is always confined to the decided chapter (`scope={chapter_id}`).

The natural places a header-derived chapter scope would plug in, without describing a fix: the per-row `row_indexes` selection in map (`marks.py:2344-2350`) and the per-question `own_scope` in place (`placement.py:323-343`), both of which already narrow by section letter.

#### 2.5.8 Caching and batching

- Prompt caching: only the topic judge's chapter block (`topic.py:298-308`). Chapter judge, sampled topic reads, `auto_resolve` and the vision reader are uncached.
- Batching: topic judge in place, on by default; chapter judge only with `batch_chapter_judge`; topic judge in map, `auto_resolve` and vision never. Wrapper: `backend/app/llm_batch.py` (`BatchedClient`), which converts `output_format` to `output_config.format`, gathers calls arriving within `batch_linger_seconds=3.0`, polls every `batch_poll_seconds=15.0`, cancels after `batch_max_wait_seconds=10800`; errored or expired items raise in their own caller.
- No call ever puts several questions in one prompt; batching groups separate requests.

### 2.6 Tiers

`QuestionTier` (`assessment.py:301-316`, append-only per its docstring): `question_id`, `tier` (String 8 short code; NULL = abstained), `action_class`, `familiarity`, `familiarity_bucket`, `signals` (JSON), `conformal_set` (JSON), `confidence`, `source` (default "ensemble"), `model_version`, `rationale` (2000), timestamps.

- **What decides the tier.** Only the chapter judge's `Classification.tier`, using the CBSE three-tier text in its SYSTEM prompt. `tier_code()` (`assessment.py:43-53`) maps the wording to `R&U` / `AP` / `AEC`; grounding clears anything else. No familiarity or other signal feeds it: the `familiarity`, `action_class` and `signals` columns are never written in this flow. `backend/app/taxonomy/tier.py:classify_tier` is referenced only by tests. The judge's tier survives a blueprint overrule even though the chapter changed.
- **Where written.** Place, one row per placed question per run, even when the tier is None (`placement.py:657-664`; `marks.py:1290-1293` comment). Human confirm with a tier adds one (`placement.py:1113-1116`). Map writes none. The scope-inference second pass does not add a row.
- **Why 110 rows for 55 questions.** Two place runs for the same assessment (for example the zero-touch classify followed by a manual Classify, or a re-run) each append 55 rows. Nothing deletes or supersedes earlier rows.

### 2.7 Display and export

**Endpoint.** `GET /assessments/{id}/scan` → `read_scan` (`backend/app/api/marks.py:1251-1404`), called by `api.readScan` (`frontend/lib/api.ts:2356-2357`) from `refresh()` in `frontend/lib/usePaperScan.ts:307-359`. Rows are staged `scanned_question` rows ordered by section, numeric question number, sub-part, choice (`marks.py:1258-1271`). Each row's `mapped_to` is built by the nested `mapped(row)` serializer (`marks.py:1317-1341`) from the `question` linked via `scanned_question.question_id`.

| Column | Table.column read | When several rows exist | Serializer | Frontend cell |
|---|---|---|---|---|
| **Chapter** | `question.chapter_id` → `taxonomy_node.label` (not `question_placement`) | one question per staged row | `marks.py:1321, 1325` | `frontend/app/teacher/dashboard/page.tsx:1040`: `q.mapped_to?.chapter ?? <tag>{blocked_reason ?? "Not placed"}</tag>` |
| **Topic** | `question_skill.node_id` → `taxonomy_node.label` | sorted by weight descending, first label shown; ties fall to DB order | `marks.py:1277-1288, 1328` | `page.tsx:1050`: `q.mapped_to?.topic ?? "—"` |
| **Tier** | `question_tier.tier` → `TIER_ALIASES` label | **no `ORDER BY`**; each non-null row overwrites the previous, so the last non-null row the DB returns wins | `marks.py:1289-1300, 1334-1335` | `page.tsx:1052` |
| **Needs review** | `question_placement.needs_review` | newest by `created_at` (ascending loop, last write wins) | `marks.py:1305-1315, 1339` | `page.tsx:1054-1063` |
| **Explanation** | `question_placement.reasoning` of that same newest row | as above | `marks.py:1340` | `page.tsx:1056` (gold tag); under it one of two hard-coded sentences chosen by `review_reason.includes("Auto-resolved")` (`page.tsx:1013, 1057-1061`) |

Topic code path:

```python
for link in sorted(db.scalars(select(QuestionSkill).where(...)),
                   key=lambda link: -(link.weight if link.weight is not None else 1.0)):
    ...skills.setdefault(link.question_id, []).append(node.label)
...
"topic": (skills.get(question.id) or [None])[0],
```

So the Topic column reads **neither** `question.curriculum_section` **nor** any `question_placement` row. It reads the label of the heaviest `question_skill` node. For book-map subjects that label is `"{number} {title}"` from the chunk reference; for other subjects it is the subtopic node label. Because `topic_node` relabels nodes by code (2.2.2), the label shown can come from a different numbering than the section stored on the question.

Tier code path:

```python
for row_tier in db.scalars(select(QuestionTier).where(QuestionTier.question_id.in_(...))):
    classified_question_ids.add(row_tier.question_id)
    if row_tier.tier:
        tiers[row_tier.question_id] = row_tier.tier
```

Needs-review and explanation code path:

```python
for row_placement in db.scalars(select(QuestionPlacement)...order_by(QuestionPlacement.created_at)):
    review[row_placement.question_id] = (row_placement.needs_review, row_placement.reasoning or None)
```

**Source-passage rows** show a roll-up of their sub-parts' distinct chapters and topics joined with " / " (`page.tsx:209-217, 1027-1050`).

**Settle modal.** Reads `GET /assessments/{id}/review` (`placement.py:910-987`): latest placement per question where `needs_review` is true, sorted by confidence ascending; shows its `reasoning` (`page.tsx:1146-1148`).

**Display inconsistencies (from the code).**
- A skill-anchored question (classify set `chapter_id = NULL`) has `mapped_to` but no chapter and no blocked reason, so it renders the red "Not placed" tag and still counts in the "mapped" tab (`placement.py:515-527`; `page.tsx:1040`).
- The "Needs review" count right after a map run comes from the map job's result, which counts every flagged `question_placement` row ever written for the paper (`marks.py:2624-2629`), while a reopened paper counts only latest rows (`usePaperScan.ts:342`).
- When the judge failed or a family was refused, the latest placement row and the Chapter column can name different chapters (`placement.py:501-514, 605-609`).

**Exports.** There is no export or download of the scan/review table. Question-level data reaches files only through:
- `backend/app/api/academics.py` xlsx/pdf/csv routes (`/overview.xlsx`, `/{section}/students.xlsx`, `/students/{id}.xlsx`, `/students/{id}/subjects/{code}.xlsx|.pdf`, `/tests.xlsx|.pdf`, `/tests/{id}.xlsx|.pdf`), all built on `resolved_rows` (`academics.py:108-179`): chapter from `question.chapter_id` (code), tier from an unordered dict over `question_tier` in which a NULL (abstain) row **can** overwrite a real tier (`academics.py:141-144`); no topic.
- `backend/app/api/reports.py:_rows` (98-161): all `question_skill` codes (unordered), tier skipping NULL (unordered), chapter from `question.chapter_id` falling back to the latest placement (`_latest_placements`, 84-95). PDFs via `backend/app/analysis/boardx_report.py` and `backend/app/analysis/report_pdf.py`.

So the screen, the reports and the academics exports can show different tiers for the same question.

**Duplicates and several runs.** The papers list returns every assessment of the school ordered `created_at DESC` (`backend/app/api/admin.py:756-774`; `marks.py:283-287`). When a subject is pre-selected, the dashboard auto-opens the first match, i.e. the **newest** assessment for that subject (`usePaperScan.ts:153-161`); otherwise whichever card is clicked. Within one assessment the screen shows one row per staged row, with the newest placement, the heaviest topic, and the DB-order-last non-null tier.

---

## 3. Data snapshot

**Not run against production.** The only database reachable here is a local SQLite development file (`YAADHUM_DATABASE_URL` [REDACTED], scheme `sqlite+pysqlite`). A read-only check found that neither `959e36d4-5028-42e6-922e-c69228c5c325` nor `32ebf883-0a1f-4b10-ace9-6eecc7ffd946` exists in it, it holds six `X.SST` assessments created by local development, and its `book_chunk` table is empty. Its contents are not representative, so no tables are reproduced. No production connection is configured in this environment.

The following SELECT-only queries (Postgres syntax) produce the requested snapshot when run against the production database by someone with read access.

```sql
-- 3.1 X.SST assessments with question counts and job history
SELECT a.id, a.created_at, a.exam_id, a.title,
       (SELECT count(*) FROM question q WHERE q.assessment_id = a.id) AS questions,
       (SELECT string_agg(j.kind || ':' || j.status || ':' ||
                coalesce(extract(epoch FROM (j.finished_at - j.created_at))::int::text, '-'),
                ', ' ORDER BY j.created_at)
          FROM placement_job j WHERE j.assessment_id = a.id) AS jobs_kind_status_seconds
FROM assessment a
WHERE a.subject_code = 'X.SST'
ORDER BY a.created_at;

-- 3.2 Per-question state and every placement row, for the two assessments
SELECT q.address, q.curriculum_section, cf.label AS concept_family,
       p.created_at, p.source, p.curriculum_section AS placed_section,
       p.confidence, p.needs_review, left(p.reasoning, 150) AS reasoning_150
FROM question q
JOIN taxonomy_node cf ON cf.id = q.concept_family_id
LEFT JOIN question_placement p ON p.question_id = q.id
WHERE q.assessment_id IN ('959e36d4-5028-42e6-922e-c69228c5c325',
                          '32ebf883-0a1f-4b10-ace9-6eecc7ffd946')
ORDER BY q.assessment_id, q.section, q.question_no, q.sub_part, p.created_at;

-- 3.2b What the Topic and Tier columns would show for the same questions
SELECT q.address, n.code, n.label, s.weight, s.source, s.confidence
FROM question q JOIN question_skill s ON s.question_id = q.id
JOIN taxonomy_node n ON n.id = s.node_id
WHERE q.assessment_id IN ('959e36d4-5028-42e6-922e-c69228c5c325',
                          '32ebf883-0a1f-4b10-ace9-6eecc7ffd946')
ORDER BY q.address, s.weight DESC;

SELECT q.address, t.created_at, t.tier, t.source, t.confidence
FROM question q JOIN question_tier t ON t.question_id = q.id
WHERE q.assessment_id IN ('959e36d4-5028-42e6-922e-c69228c5c325',
                          '32ebf883-0a1f-4b10-ace9-6eecc7ffd946')
ORDER BY q.address, t.created_at;

-- 3.3 Subtopics and concept families of the four chapters
SELECT ch.label AS chapter, n.kind, n.code, n.label, n.created_at
FROM taxonomy_node n JOIN taxonomy_node ch ON ch.id = n.parent_id
WHERE ch.kind = 'chapter'
  AND ch.label IN ('Print Culture and the Modern World', 'Minerals and Energy Resources',
                   'Political Parties', 'Globalisation and the Indian Economy')
  AND n.kind IN ('subtopic', 'concept_family')
ORDER BY ch.label, n.kind, n.code;

-- 3.3b Section claims behind those families
SELECT p.code, p.source, p.run_id, p.from_sections, p.applied_at, p.created_at
FROM concept_family_proposal p
WHERE p.subject_code IN ('X.HIST', 'X.GEO', 'X.POL', 'X.ECO')
ORDER BY p.code, p.created_at;

-- 3.4 Book chunks by reference type and section presence
SELECT subject_code,
       CASE WHEN reference LIKE '%(caption)%' THEN 'caption'
            WHEN reference LIKE '%(box%'      THEN 'box'
            WHEN reference LIKE '%(activity)%' THEN 'activity'
            WHEN reference LIKE '%(glossary%' THEN 'glossary'
            WHEN reference LIKE '%(source%'   THEN 'source'
            WHEN reference LIKE '%(map)%'     THEN 'map'
            WHEN reference LIKE 'Exercise Q%' THEN 'exercise'
            ELSE 'body' END AS ref_type,
       section_number IS NULL AS no_section,
       embedding IS NULL AS no_embedding,
       count(*)
FROM book_chunk
WHERE subject_code IN ('X.HIST', 'X.GEO', 'X.POL', 'X.ECO', 'X.SCI')
GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4;

-- 3.5 Confidence distribution of judge (place) rows
SELECT source, round(confidence::numeric, 2) AS confidence, count(*)
FROM question_placement
WHERE source IN ('model', 'blueprint') AND reasoning NOT LIKE '%retrieval, margin%'
GROUP BY 1, 2 ORDER BY 1, 2;
```

---

## 4. Cost and volume

**Per-stage model parameters.**

| Stage | Model (setting) | Effort | max_tokens | Batched | Cached |
|---|---|---|---|---|---|
| Vision page read | `claude-opus-5` (`model_high_stakes`) | not sent | 16000 | no | no |
| Chapter judge | `claude-sonnet-5` (`model_classifier`) | `medium` (`model_effort`) | 16000 | only if `batch_chapter_judge` (off) | no |
| Topic judge reads | `claude-sonnet-5` | `medium` | 8000 | in place: yes (`batch_classify`, on) | chapter block, ephemeral |
| Topic answerability | `claude-sonnet-5` | `medium` | 2000 | as above | as above |
| Family auto-resolve | `claude-sonnet-5` | `medium` | 4000 | no | no |
| LLM family proposals (not in pipeline) | `claude-haiku-4-5` (`model_high_volume`) | not sent | 16000 | no | no |
| Hindi page OCR (ingest only) | `gemini-3.6-flash` | temperature 0 | — | no | no |
| Embeddings | `jina-embeddings-v4`, 512 dims | — | — | ≤32 per request | — |

**Worked count for a 55-question, 4-chapter Social Science paper, zero-touch path.** Assumptions: 55 = gradable rows after context rows are excluded; one chapter per SST subject; vision route with P pages; embeddings present; the answer read and the verification succeed on most rows.

| Step | Calls | Arithmetic |
|---|---|---|
| Vision scan | P | 1 per page (e.g. 7 pages → 7). Text route: 0 |
| Subject check | 0 | lexical only |
| Map | 0–55 LLM, 55 Jina | topic deferred; `auto_resolve` 0–1 per question only when `choose_family` blocks (book-map families claim each section, so usually 0); 1 Jina query embedding per question |
| Place: chapter judge | 55, or 110 | 1 per question; ×2 when scope inference triggers a second pass (no `syllabus_scope`, paper ≥ 8 questions, confident vote) |
| Place: topic judge | 110 to 440; typically 165–220 | 2 to 8 per question; typical 3 (two reads + verify) to 4 (+ confirm): 55 × 3 = 165, 55 × 4 = 220 |
| Place: Jina | 110–165 | chapter retrieval 1 per question per pass + topic retrieval 1 per question |
| Place: auto-resolve | 0–55 | when a family is blocked |
| **Total LLM, typical** | **P + 220 to P + 330** | P + 55 (or 110) chapter + 165–220 topic + ~0 auto-resolve |

Prompt cache: the topic judge's chapter block is written once per chapter (4 writes) and read on every later read of that chapter within the cache lifetime; how batch requests share the cache is not visible in the code (**UNKNOWN**).

**Usage tracking in code.**
- `AnthropicJudge` counts `calls`, `input_tokens`, `output_tokens`, `cache_read_tokens` (`backend/app/classify/anthropic_judge.py:87-91`); `TopicJudge._count` the same (`backend/app/classify/topic.py:283-289`).
- Place job result `spend`: model, effort, calls, input, output, cache-read tokens, passages shown, chapters shown, batched flag, and `estimated_usd` with each judge priced at its own rate (`placement.py:695-730`). Map job result `spend` covers the topic judge only (`marks.py:2610-2622`).
- Price table `PRICES_PER_MTOK` and `estimate_usd` (`backend/app/llm.py:57-83`): input, output and cache-read prices per model; batched calls halved; unknown models priced as `claude-sonnet-5`. **Cache-creation tokens are not counted or priced** (no `cache_creation` in the code).
- **Not counted anywhere:** the vision reader, the grid-sheet reader, `auto_resolve`, the LLM family proposer, Gemini, Sarvam and Jina.
- Surfaced: `assessment_summaries` sums `spend` from the latest succeeded map and place jobs (`marks.py:209-227, 257-261`); the dashboard shows "N model calls · ≈ $X" (`frontend/app/teacher/dashboard/page.tsx:463-465`).

---

## 5. Open questions and inconsistencies

**Topic and section numbering.**
1. Two subtopic numbering schemes coexist for book-map subjects (reading order from PDF ingest; printed numbers from the book map), keyed by the same code format. `topic_node` relabels whatever node has the computed code, so ingest nodes are overwritten with book-map labels (2.2.2).
2. `marks.py:2221-2229` and `2390-2391` can still write a stale ingest subtopic as the topic when no book-map label is found.
3. `sections_of` is a last-wins dict over unordered proposal rows in map and place, but a union in `auto_resolve`; `record_family_section` seeds from the first matching row only.
4. `_ensure_family` codes (`{chapter}.CF.AUTO_*`) are not under the `{subject}.CF.` prefix the book-screen routes filter on.
5. `auto_resolve` stage 1 selects chunks by section number across the whole subject group, not by chapter, so another book's identically numbered section can be mixed in (`auto_resolve.py:432-437`).

**Confidence and review.**
6. Map placement confidence is an RRF score (≤ ~0.065) while place confidence is the judge's 0–1 estimate; the two share one column.
7. With no embeddings, `verdict.agreed` is always False and every map row is flagged.
8. Out-of-scope options: runner-up and alternative options use the unzeroed `call.confidence`, so an out-of-scope primary at 0.0 can lose to a runner-up without a blueprint (`pipeline.py:276-303`).
9. `question_placement.reasoning` is `String(1000)`; place concatenates up to 600 characters of judge reasoning, the topic rationale, family messages and auto-resolve text, which can exceed 1000 (**INFERRED**: on Postgres the write phase would fail with 500).

**Tiers and display.**
10. `QuestionTier`'s docstring promises precedence; no precedence logic exists. All three readers (`marks.py:1295-1300`, `reports.py:118-121`, `academics.py:141-144`) read without `ORDER BY`, and they treat NULL tiers differently.
11. Topic ties between equal weights fall to DB order.
12. Skill-anchored rows render as "Not placed"; the post-map "Needs review" count includes historical rows.

**Scope and duplicates.**
13. The chapter named in a section header is discarded by both extractors.
14. `syllabus_scope` is honoured by place but ignored by map.
15. `source_sha256` is written and never read; the standalone upload path always creates a new assessment; `_queue_auto_pipeline` does not check for running jobs.
16. The place poll route does not check `kind`.
17. `choice_group_id` is never set for scanned questions; a `None`/`"b"` OR pair forms no group in `group_choices`.

**Ingestion.**
18. `import_book_map --apply` drops all embeddings for each subject it imports; no step re-embeds.
19. "Exercise Qn" uses the list index, not the printed number. Intro and summary units have no section, so they are absent from the topic judge's chapter document.
20. On the PDF path, text before the first heading is not chunked.

**Flags and markers.**
- No `TODO`, `FIXME`, `XXX` or `HACK` markers in `backend/app`.
- Pipeline flags (`backend/app/config.py`): `auto_pipeline`, `batch_classify`, `batch_chapter_judge`, `batch_linger_seconds`, `batch_poll_seconds`, `batch_max_wait_seconds`, `model_high_stakes`, `model_high_volume`, `model_classifier`, `model_effort`, `vision_page_concurrency`, `classifier_evidence_passages`, `classifier_evidence_chapters`, `classifier_passage_chars`, `embedding_model`, `embedding_dimensions`, `gemini_model`, `sarvam_language`, `auto_accept_threshold`, `conformal_alpha`, `evidence_floor_marks`, `evidence_floor_questions`.
- Dead or unused: `backend/app/taxonomy/tier.py:classify_tier` (tests only); Redis in local compose; `backend/app/mapping/solver.py` is the marks constraint solver, not part of chapter placement.

**Differences between subjects.**

| Aspect | Social Science (X.SST) | Science (X.SCI) | Maths (X.MATH) | Languages (X.ENG, X.HIN, X.TAM) |
|---|---|---|---|---|
| Book text source | book-map import | book-map import | PDF ingest | PDF ingest (single section), Hindi OCR, Tamil OCR fallback |
| Section numbers | printed (book map) | printed (book map) | printed via regex | one section per chapter |
| Topic label source | chunk reference `"{n} {title}"` (`BOOK_MAP_SUBJECTS`) | same | subtopic node label | subtopic node label |
| Per-question subject narrowing | section letter → book (`_SST_SECTION_SUBJECT`) | none | none | none |
| Evidence chapters in chapter judge | up to 9 (4 books) | 3 | 3 | up to 9 for multi-book groups |
| Concept families | book-map catalog codes | book-map catalog codes | curated + proposed | proposed |
| Skill-anchored (no chapter) answers | rare | rare | rare | expected for writing tasks (judge case 3) |

---

## 6. File index

**Backend: API and jobs**
- `backend/app/api/marks.py` — assessment create, Q-matrix import, scan routes and jobs, confirm, zero-touch chain, map job and `_map_paper`, `_ensure_family`, `read_scan` display serializer, paper summaries and spend.
- `backend/app/api/placement.py` — scope route, place job (judges, topic, writes, spend), review queue and human confirm.
- `backend/app/api/books.py` — curriculum setup, contents/chapter ingest, `_load`, expected sections, family proposals and application, embedding backfill.
- `backend/app/api/documents.py` — `store_document` for scan documents and pages.
- `backend/app/api/admin.py` — teacher papers list ordering, subjects and chapter listing.
- `backend/app/api/reports.py` — report rows, latest placements, PDF routes.
- `backend/app/api/academics.py` — `resolved_rows` and xlsx/pdf/csv exports.
- `backend/app/main.py` — app setup and routers.
- `backend/app/config.py` — settings and env var names.

**Backend: extraction, retrieval, judges**
- `backend/app/extraction/paper.py` — text-route paper extractor, regexes, addresses, context rows, dedupe.
- `backend/app/extraction/paper_vision.py` — vision paper reader, prompts, schema, rasteriser.
- `backend/app/extraction/address.py` — address key format.
- `backend/app/extraction/choice.py` — OR and attempt-N grouping.
- `backend/app/extraction/verification.py` — declared-value gates.
- `backend/app/ingest/probe.py` — tokeniser, lexical and semantic indexes, `locate` fusion, content filters.
- `backend/app/ingest/book.py` — PDF text, TOC parsing, section detection, chunking.
- `backend/app/ingest/jina.py`, `embed.py` — embeddings client and cosine.
- `backend/app/ingest/gemini_ocr.py`, `sarvam_ocr.py`, `hindi_text.py`, `hindi_ocr.py`, `tamil_text.py`, `tamil_ocr.py` — OCR backends.
- `backend/app/classify/judge.py` — chapter judge prompt and schema.
- `backend/app/classify/anthropic_judge.py` — chapter judge client.
- `backend/app/classify/grounding.py` — grounding checks and the 0.4 cap.
- `backend/app/classify/pipeline.py` — `_pass`, options, scope inference, `place_paper`.
- `backend/app/classify/reconcile.py` — blueprint reconcile and `needs_a_human`.
- `backend/app/classify/scope.py` — scope inference thresholds.
- `backend/app/classify/topic.py` — topic judge prompts, schemas, `choose_topic`, verification, caching.
- `backend/app/llm.py` — effort options and price table.
- `backend/app/llm_batch.py` — Message Batches wrapper.

**Backend: mapping and taxonomy**
- `backend/app/mapping/family.py` — `choose_family`, `alike`.
- `backend/app/mapping/auto_resolve.py` — blocked-family resolution, prompt, `record_family_section`.
- `backend/app/mapping/topic_node.py` — `section_headings`, `topic_node`, `set_question_topic`, `BOOK_MAP_SUBJECTS`.
- `backend/app/mapping/solver.py` — marks constraint solver (not chapter placement).
- `backend/app/curriculum/__init__.py` — `CURRICULA`, subject groups, chapter titles.
- `backend/app/curriculum/apply.py` — subject, unit, chapter and curated family creation.
- `backend/app/curriculum/families.py` — heading-based family proposals.
- `backend/app/curriculum/llm_families.py` — LLM family proposer.
- `backend/app/taxonomy/variants.py` — variant hash.
- `backend/app/taxonomy/tier.py` — unused tier ensemble.

**Backend: models and migrations**
- `backend/app/models/assessment.py` — Assessment, Question, ScannedQuestion, QuestionPlacement, QuestionSkill, QuestionTier, tier codes.
- `backend/app/models/taxonomy.py` — TaxonomyNode, BookChunk, BookSource, ConceptFamilyProposal, IngestJob.
- `backend/app/models/documents.py` — ScanDocument, ScanPage, PaperScanJob, PlacementJob.
- `backend/app/models/base.py` — timestamp mixin.
- `backend/migrations/versions/5a1ebe98e396_*.py` — `book_chunk` DDL, JSON embedding.
- `backend/migrations/versions/a1c4f7e920b3_book_chunk_section.py` — `section_number` column and back-fill.

**Backend: scripts and reference data**
- `backend/scripts/import_book_map.py` — book-map import for SST and Science.
- `backend/scripts/embed_kb.py` — embedding backfill.
- `backend/scripts/load_expected_sections.py` — hand-typed section oracle.
- `backend/scripts/apply_concept_families.py` — family dedupe and apply client.
- `backend/scripts/diagnose_duplicate_subtopics.py` — duplicate-label subtopic diagnostic.
- `backend/scripts/seed.py`, `backend/scripts/ingest_book.py` — seed and CLI ingest.
- `backend/reference/book_map/*/*_units.json`, `*.md`, `README.md` — Social Science book map.
- `backend/reference/book_map_science/*` — Science book map and its docs.

**Frontend**
- `frontend/app/teacher/dashboard/page.tsx` — papers list, upload panels, scan table, settle modal, spend label.
- `frontend/lib/usePaperScan.ts` — upload, assessment creation, refresh, auto-open, job following.
- `frontend/lib/api.ts` — API client and types.
- `frontend/lib/download.ts` — download helper.

**Infrastructure**
- `infra/docker-compose.yml`, `infra/Caddyfile`, `infra/README.md`, `infra/s3-lifecycle.json`, `infra/backup-postgres.sh` — production topology.
- `backend/Dockerfile`, `frontend/Dockerfile`, `render.yaml`, root `docker-compose.yml`, `.github/workflows/ci.yml` — build, alternative hosting, local dev, CI.
- `backend/pyproject.toml`, `frontend/package.json` — dependencies.
