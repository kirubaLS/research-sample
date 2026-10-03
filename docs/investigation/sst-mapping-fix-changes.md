# Social Science mapping fix: changes

Branch `sst-mapping-fix`. One commit per phase. Every behaviour change sits behind a setting in `backend/app/config.py`, and every setting defaults to **off**. With every setting off, the pipeline behaves as before. The only unflagged changes are the two you approved: truncating the placement reasoning, and removing gold-paper examples from prompts. Both are in later phases.

Line numbers refer to the files as they stand at the end of the phase that changed them.

## Test baseline

In a clean virtualenv (`pip install -e ".[dev]"`), the unchanged code gives 12 failures. Eleven pass when their own file runs alone, so they depend on test order. The other one needs OCR, which is not installed in this container. Any failure outside this list is a blocker.

```text
tests/test_gridsheet.py::test_a_single_scripts_student_missed_off_the_roster_is_flagged_not_invented
tests/test_placement_api.py::test_classify_auto_resolves_instead_of_overwriting_a_good_placement_with_blocked_text
tests/test_placement_api.py::test_a_classifier_outage_fails_the_job_and_leaves_every_mapped_chapter_alone
tests/test_placement_group_scoping.py::test_identical_chapter_labels_in_different_subjects_do_not_collide
tests/test_placement_group_scoping.py::test_place_retrieves_book_chunks_across_the_whole_group
tests/test_placement_group_scoping.py::test_place_scores_a_group_paper_against_the_second_books_chapter_too
tests/test_reading.py::test_a_page_with_nothing_readable_on_it_says_so
tests/test_scan_and_map.py::test_mapping_blocks_a_question_rather_than_inventing_a_chapter
tests/test_scan_and_map.py::test_mapping_refuses_until_someone_has_confirmed_the_extraction
tests/test_scan_and_map.py::test_map_lets_the_topic_judge_choose_the_section_within_the_retrieved_chapter
tests/test_scan_and_map.py::test_the_judge_settles_the_chapter_topic_and_sub_topic_on_the_question
tests/test_topic_judge.py::test_classify_writes_the_judged_topic_and_review_overwrites_it
```

The system Python in this container fails about 450 tests. Its Debian `cryptography` package panics when the PDF routes import it, and that kills the shared test client. That is an environment fault, not a code fault. All results here come from the clean virtualenv.

Lint: `ruff check app tests` already reports errors on the base commit. The files changed here add none beyond what the base commit already had.

---

## Phase 1: read the paper's structure

### Settings

| Setting (env var `YAADHUM_<NAME>`) | Default | File | What it switches on |
|---|---|---|---|
| `paper_capture_structure` | off | `backend/app/config.py:135` | The vision reader also copies section titles and syllabus lines. Both routes store them in `assessment.declared`. |
| `sst_unified_scope` | off | `backend/app/config.py:140` | One scope rule for map and place. A bare section letter carries no subject meaning. |
| `balanced_group_candidates` | off | `backend/app/config.py:143` | The chapter judge sees each book's best chapter when a question's scope spans several books. |
| `cross_scope_fallback` | off | `backend/app/config.py:147` | A question that no in-scope chapter can answer may be placed outside its scope. It is marked `cross_scope` and flagged. |
| `skip_single_chapter_judge` | off | `backend/app/config.py:150` | A question whose scope is one chapter skips the chapter judge. The topic judge's answer read names the tier. |

### Migration

`backend/migrations/versions/e2b7c4a9d1f3_placement_review_reason_cross_scope.py`. It revises `c4e8a1f7b2d9`, the previous head.

- `upgrade()` adds three nullable columns to `question_placement`: `curriculum_section_fine` (String 32), `review_reason` (String 64) and `cross_scope` (Boolean). There is no default and no backfill.
- `downgrade()` drops the same three columns.
- Checked with `alembic upgrade head` then `alembic downgrade base` on a scratch SQLite database. `tests/test_migration_parity.py` passes.
- Model: `backend/app/models/assessment.py:357-363`.
- `curriculum_section_fine` is unused until Phase 2. `review_reason` is written only as `cross_scope` until Phase 4.

### Changes

**1.1 Section titles and syllabus lines**

- `backend/app/extraction/paper_vision.py`
  - `:44-50` adds `section_titles` and `syllabus_lines` to the reading.
  - `:84-99` adds the output schemas `_DeclaredStructureOut` and `_PaperStructureOut`. Every new field has a default, so an older-style reply still parses.
  - `:191` adds `STRUCTURE_RULES`. It is appended to `SYSTEM` only when the flag is on, and says: copy verbatim, leave blank if not printed, never infer, never translate.
  - `:250` adds a `capture_structure` argument to the reader, and `:538` to `read_paper_vision`.
  - With the flag off, the system prompt and output format are byte-for-byte the old ones. A test asserts this.
  - When pages merge, the first non-blank title per letter wins, and syllabus lines are de-duplicated.
- `backend/app/extraction/paper.py`
  - `:91-107` adds `SECTION_TITLED`, `SYLLABUS` and `SYLLABUS_ENTRY`. The existing `SECTION` regex is unchanged.
  - `:200-204` adds the new fields to `PaperExtract`.
  - `:497-548` adds `_structure()`. It reads the title after the letter, or on the line below in brackets, and skips instruction sentences such as "Section A comprises 20 questions…". It collects syllabus lines, plus up to six entry lines under a bare "Syllabus:" label.
  - `:579` calls `_structure()`.
- `backend/app/api/marks.py`
  - `:854-860` adds `section_titles` and `syllabus_lines` keys to `assessment.declared`, only when the flag is on. The existing `sections`, `question_count` and `total_marks` keys are unchanged, so every existing reader still works.
  - `:988-1009` passes `capture_structure` only when the flag is on, so existing stubs of `read_paper_vision` keep their signature.

**1.2 Resolver** (new file `backend/app/curriculum/resolve.py`, no model calls)

- `resolve_text(text, subject_codes, aliases, default_subject=None)` returns subject codes and chapter codes with scores.
- It reads three kinds of evidence:
  - subject words in English and Hindi
  - chapter numbers (Ch 3, Chapter 1-2, Ch. 1, 3, Unit 2, Lesson IV, roman numerals), counted only under a subject word in the same stretch of text, or for a one-book paper
  - chapter titles and `taxonomy_alias` rows, matched on normalised tokens with near-spelling tolerance inside a short window, at a threshold of 0.8
- A subject word restricts title matches to its own book. A title wholly contained in another matched title is dropped, so "Development" inside "Resources and Development" is not counted.
- Below the threshold, it returns nothing.
- `load_chapter_aliases(db, subject_codes)` reads the alias rows.

**1.3-1.4 One scope rule** (new file `backend/app/classify/question_scope.py`)

- `PaperScope.for_section(letter)` applies the precedence teacher, section title, syllabus, inferred, group.
- A lower source only narrows a higher one. If they don't overlap, the higher one stands. The one exception: a section title outranks a syllabus line that does not list its chapter.
- A title that resolves to a subject but no chapter scopes to every chapter of that subject.
- `backend/app/api/marks.py:2225-2257` builds one retrieval index per distinct scope, lazily. `:2389-2401` uses the scope when the flag is on and keeps the `_SST_SECTION_SUBJECT` path when it is off. With the flag on, map now honours the teacher's `syllabus_scope`, which it ignored before.
- `backend/app/api/placement.py:335-353`: with the flag on, the paper-level `scope` is the teacher scope or the syllabus scope, so inference runs only when neither exists. `scope_of` is the per-question decision. The `_SST_SECTION_SUBJECT` path is kept for flag off.

**1.5 Balanced candidates**

- `backend/app/ingest/probe.py:254` adds `search_all()`. `:268` lets `locate()` accept already-fetched results, so one search, and one Jina embedding, serves the scoped verdict and every per-book verdict.
- `backend/app/classify/pipeline.py:238-272` adds `retrieve()`. When a question's scope spans more than one book, each book's best chapter adds up to two passages to the judge's evidence.

**1.6 Cross-scope**

- `backend/app/classify/judge.py:63-82` adds `ScopedClassification` (`Classification` plus `no_in_scope_chapter`) and `SCOPE_NOTE`.
- `backend/app/classify/anthropic_judge.py:77-95`: `classify(..., scoped=True)` sends that schema and note. With `scoped=False`, the request is unchanged.
- `backend/app/classify/pipeline.py:318-413`:
  - A question whose scope was declared (its own title, or a teacher or syllabus scope) is asked the scoped question.
  - If the judge says nothing in scope fits, one more read runs over the paper's own subject group. For Social Science that is History, Geography, Political Science and Economics, nothing else.
  - A chapter outside the scope sets `cross_scope`.
  - The existing "nothing in scope was retrieved" retry also counts as cross-scope when the scope was declared.
  - An inferred scope never produces a cross-scope placement.
- `backend/app/api/placement.py:720-737` writes `cross_scope=True` and `review_reason='cross_scope'`, and forces `needs_review`.

**1.7 Skipping the chapter judge**

- `backend/app/classify/pipeline.py:283-307`: a question whose declared scope is one chapter gets that chapter at confidence 1.0, with no retrieval and no judge call. An inferred single-chapter scope never skips.
- `backend/app/classify/topic.py`:
  - `:127-140` adds `_TopicChoiceWithTier` and `grounded_tier()`. A tier must be one of CBSE's three, worded exactly, or it is dropped, the same rule as the chapter judge's grounding.
  - `:332-392` adds `with_tier`, which applies only to the **answer read** (read 1). The tier wording comes from `TIER_GUIDE` (`backend/app/classify/judge.py:86`) in the user message. The cached chapter prefix is unchanged, and a test asserts this.
  - `:574`, `:772` and `:825-862` add `want_tier`, which threads through `choose_topic`. The tier survives a section fallback.
- `backend/app/api/placement.py`:
  - `:487` asks for the tier only for skipped questions.
  - The tier is written to `question_placement.tier` and, as before, one `question_tier` row per run.
  - The placement `source` is `scope`.
  - `:527-570`: if the topic judge then verifies no section of that one chapter (`verified is False`), `reclassify_without_scope()` (`backend/app/classify/pipeline.py:580`) reads it once over the whole subject group. A different chapter becomes a cross-scope placement, and its topic is decided afresh.

### Tests added (83, all passing)

| File | What it covers |
|---|---|
| `backend/tests/test_paper_structure.py` | Vision prompt and format unchanged with the flag off. Titles and syllabus lines read, kept verbatim, first title wins. An old-style reply parses. Text-route titles: same line, bracketed next line, instruction lines skipped. A bare "Syllabus:" block. No titles. Storage in `declared` with the flag on and off. |
| `backend/tests/test_resolve.py` | Titled sections, short names only through aliases, Hindi subject words, chapter-number lists and ranges, roman numerals. Unclear text returns nothing, including type titles, a bare "Ch 3" in a group paper, one-word partial titles, ambiguous "Resources" and out-of-range numbers. The low-confidence rejection. The subject word restricting titles. The seed script: dry run writes nothing, apply refuses without a backup, apply writes an undo file, a second run is idempotent. |
| `backend/tests/test_question_scope.py` | Formats F1 to F4: subject-only titles, chapter titles, type-only titles, a bilingual type title, a bilingual subject title, no titles, syllabus lines. Teacher precedence and title-versus-syllabus precedence. The old `declared` shape. Map with the flag on, including a board Section A of MCQs never forced into History, and with the flag off. Place scope passed to the pipeline, on and off. Place-job runs for the skip and tier, for the cross-scope move, and for flags off writing no new columns. |
| `backend/tests/test_judge_options.py` | Balanced candidates show the crowded-out book and stay inside scope. Cross-scope: placed outside and marked; in-scope fits never re-asked; back in scope is not cross-scope; flag off sends the old call; an undeclared scope is never asked. Skip: per-question and paper-wide single scope, multi-chapter not skipped, flag off. Tier: grounding of five values, only the answer read asked, schema sent only when tiered. Chapter judge sends the scoped schema only when scoped. |

Full suite: 1129 passed, 19 skipped, and the 12 baseline failures above.

### Script: `backend/scripts/seed_sst_aliases.py`

It only inserts `taxonomy_alias` rows. Dry run is the default. `--apply` requires `--i-have-a-backup` and writes a JSON undo file listing every inserted row's id and values.

The shared guard rails are in `backend/scripts/_row_safety.py`: the dry-run default, the backup refusal that prints a `pg_dump` command naming the environment variable rather than its value, and the undo file.

Dry-run output, against a scratch SQLite database with the four Social Science curricula applied:

```text
DRY RUN -- nothing will be written
  insert                           X.HIST.NATIONALISM_EUROPE    Nationalism in Europe
  insert                           X.HIST.NATIONALISM_EUROPE    Rise of Nationalism in Europe
  skip: equals the chapter label   X.HIST.NATIONALISM_INDIA     Nationalism in India
  insert                           X.HIST.GLOBALWORLD           Making of a Global World
  insert                           X.HIST.GLOBALWORLD           Global World
  insert                           X.HIST.INDUSTRIALISATION     Age of Industrialisation
  insert                           X.HIST.INDUSTRIALISATION     Industrialisation
  insert                           X.HIST.PRINTCULTURE          Print Culture
  insert                           X.GEO.FORESTWILDLIFE         Forest and Wildlife
  insert                           X.GEO.FORESTWILDLIFE         Forests and Wildlife
  insert                           X.GEO.MINERALSENERGY         Minerals
  insert                           X.GEO.MINERALSENERGY         Minerals and Energy
  insert                           X.GEO.MINERALSENERGY         Energy Resources
  insert                           X.GEO.MANUFACTURING          Manufacturing
  insert                           X.GEO.LIFELINES              Lifelines
  insert                           X.GEO.LIFELINES              Lifelines of the National Economy
  skip: equals the chapter label   X.POL.PARTIES                Political Parties
  insert                           X.ECO.SECTORS                Sectors of Economy
  insert                           X.ECO.SECTORS                Sectors of the Economy
  insert                           X.ECO.GLOBALISATION          Globalisation
  insert                           X.ECO.GLOBALISATION          Globalization
19 alias row(s) to insert, 2 skipped
```

Against the local development database `backend/yaadhum.db`, every row is skipped with "chapter not in database", because that copy has no Social Science curriculum.

`--apply` without `--i-have-a-backup` exits with status 2:

```text
Refusing to --apply without a backup. Take one first, for example:

    pg_dump "$YAADHUM_MIGRATION_DATABASE_URL" --format=custom --file "yaadhum-backup-$(date +%Y%m%d-%H%M%S).dump"

then re-run with --apply --i-have-a-backup.
```

### Commands for you (staging copy only, never production)

```bash
cd backend
alembic upgrade head                                     # adds the three nullable columns
python -m scripts.seed_sst_aliases                       # dry run: read the plan
python -m scripts.seed_sst_aliases --apply --i-have-a-backup   # after taking the backup it prints
# then switch on, per environment:
#   YAADHUM_PAPER_CAPTURE_STRUCTURE=true YAADHUM_SST_UNIFIED_SCOPE=true
#   YAADHUM_BALANCED_GROUP_CANDIDATES=true YAADHUM_CROSS_SCOPE_FALLBACK=true
#   YAADHUM_SKIP_SINGLE_CHAPTER_JUDGE=true
```

Section titles reach `declared` only for papers scanned after `paper_capture_structure` is on. A paper scanned earlier must be re-scanned to gain them, and a vision re-scan is a paid call.

### Notes on Phase 1 decisions

- **Teacher scope versus section titles.** The teacher scope is never overruled, but a section title may narrow inside it. Without this, a teacher scope listing all four chapters of a unit test would give every question all four chapters, and the header would be ignored.
- **Inferred scope.** Inference still runs in place only when nothing paper-wide is declared. It still intersects with a question's own title scope. An inferred scope never skips the chapter judge and never makes a placement cross-scope.
- **Cost.**
  - A skipped question saves one chapter-judge call and its retrieval, including the Jina embedding.
  - Balanced candidates add passages but no calls, and no extra embedding because one search is reused.
  - Cross-scope adds one chapter-judge call, only for a question it triggers on. A skipped question that the topic judge cannot verify adds one chapter-judge call plus a new topic decision.
