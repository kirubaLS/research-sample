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

---

## Phase 1 follow-up: resolver variants and teacher-scope warnings

- `backend/app/classify/question_scope.py`: `ScopeDecision.warning` and `PaperScope.warnings()`. A section title that resolves only to chapters outside the teacher's scope is ignored for that question, the teacher's scope stands, and one warning line is recorded.
- The warnings reach the job result as `scope_warnings`, in the map job (`backend/app/api/marks.py:2748`) and the place job (`backend/app/api/placement.py:857`), only with `sst_unified_scope` on.
- Tests in `backend/tests/test_resolve.py`:
  - eight spelling variants, each to exactly one chapter
  - "Resources and Development", "Global World" and "Globalisation" never cross-match
  - the gold paper's four exact header strings
  - "Energy Resources" alone resolves to `X.GEO.MINERALSENERGY` with score 1.0 through its alias; without the alias the title scores 0.667, below the 0.8 threshold, and nothing is returned
- Tests in `backend/tests/test_question_scope.py`: the warning, its appearance in both job results, and no key with the flag off.

---

## Phase 2: one clean, two-level topic list per chapter

### Settings (all off by default)

| Setting | File | What it switches on |
|---|---|---|
| `topic_depth_cap` | `backend/app/config.py:156` | `collapse_section` everywhere a section is decided or stored, for subjects in the map below |
| `topic_max_depth` (2) | `backend/app/config.py:158` | the depth a listed subject gets when its own entry gives none |
| `topic_max_depth_by_subject` | `backend/app/config.py:159` | `{"X.HIST":2,"X.GEO":2,"X.POL":2,"X.ECO":2}`. A subject not listed keeps today's behaviour. JSON in `YAADHUM_TOPIC_MAX_DEPTH_BY_SUBJECT`. |
| `topic_major_only_document` | `backend/app/config.py:165` | the topic judge is offered major topics only, with deeper text as subheadings and "0 Introduction" |
| `book_map_only_subtopics` | `backend/app/config.py:169` | book-map subtopics matched by printed number only, never relabelled, never an ingest-node fallback; family sections are a union |

No migration in Phase 2. `question_placement.curriculum_section_fine` came with Phase 1's migration.

### Where the book map's structure comes from

New `backend/app/curriculum/book_map.py` reads unit structure (number, title, kind, parent, family code) from the audited reference JSON in `backend/reference/book_map/`. It keeps no body text.

The chunk table cannot say that "2.1 Rat-Hole Mining" is a box, or that "4.1 Conventional Sources of Energy" exists with no text of its own. This module can. It adds no dependency on `book_chunk`.

- `major_headings` (`:90`) lists every numbered unit at depth ≤ the cap that is not a box, plus "0 Introduction" when the chapter has an unnumbered introduction or conclusion.
- `major_of` (`:112`) maps any section to its major topic: itself, a box's parent, or the nearest listed ancestor.
- `family_topic` (`:137`) gives the major topic a book-map family *is*, or none.

### 2A: the cap

- **`collapse_section(subject_code, section, *, chapter_code=None)`** (`backend/app/curriculum/depth.py:46`):
  - truncates "4.1.1" to "4.1" for capped subjects
  - lifts a box to its parent when the chapter is known
  - leaves `None` and "none" unchanged
- **Applied at each point:**
  - **Retrieval evidence** for the chapter judge: one passage per major topic, labelled with it. `full_chapter_evidence(..., section_key=)` (`backend/app/ingest/probe.py:388-423`), with `PassOptions.section_cap` and `shown_section` (`backend/app/classify/pipeline.py:147`, `:213-246`).
  - **Chapter-judge grounding:** `known_sections` is collapsed (`backend/app/api/placement.py:313-319`). The judge's own answer is cut before it is grounded (`section_mapper`, `backend/app/classify/anthropic_judge.py:41`, `:109-112`), so a correct "4.1.2" is not counted as a violation.
  - **Every topic-judge result** (answer, taught, confirm, relocate and `also`): `capped()` (`backend/app/classify/topic.py:92`) cuts the section, retrieval's section and the secondaries. It drops secondaries that collapse onto the primary, removes duplicates, and keeps the original as `fine_section`. Applied in map (`backend/app/api/marks.py:2474-2480`, `:2639-2641`) and place (`backend/app/api/placement.py:541-547`).
  - **`fallback_section`:** the judge's section is already cut by `section_mapper`, and the write phase cuts it again (`backend/app/api/placement.py:648-657`).
  - **`choose_family` and `auto_resolve`:** see 2D. In `auto_resolve`, under the cap, a section's text is the chapter's own chunks of that major topic and its sub-sections, never another book's identically numbered section. Every recorded section is cut (`backend/app/mapping/auto_resolve.py:160-163`, `:372-411`).
  - **Human confirm:** cut, with the fine value kept (`backend/app/api/placement.py:1235-1243`).
  - **Last guard:** `topic_node()` cuts before creating or matching a node (`backend/app/mapping/topic_node.py:150`, `:185`). No caller can write a deeper subtopic for a capped subject.
  - **Reports:** an older deep skill code groups with its major topic on read, and the proof's section is cut (`backend/app/api/reports.py:98-121`, `:142`, `:217`).
  - **Eval:** Phase 6.
- **Test that nothing deeper is written:** `backend/tests/test_question_scope.py::test_no_path_writes_a_three_level_section_for_a_capped_subject`.
  - It runs map, then place, then a human confirm, with judges that always answer 4.1.2.
  - It asserts that no `question`, `question_placement` or `question_skill` row is deeper than two levels, and that 4.1.2 is kept in `curriculum_section_fine`.
  - With the cap switched off the same test fails, which shows it catches the problem.

### 2B: the topic judge sees major topics only

- **`topic_headings()`** (`backend/app/mapping/topic_node.py:130`) returns the major headings when `major_view()` applies. That includes headings with no text of its own, such as 4.1, excludes boxes, and adds "0 Introduction". Used by map (`backend/app/api/marks.py:2374`), place (`backend/app/api/placement.py:390`) and confirm (`:1269`).
- **`major_chunks()` and `_MajorChunk`** (`backend/app/classify/topic.py:362-421`) show every chunk through its major topic. A chunk of 4.1.2 counts as 4.1, and introduction or conclusion text counts as "0". Retrieval, term votes, the chapter document, quote anchoring and answerability therefore all work at major-topic level. `choose_topic(..., major=(chapter_code, depth))` (`:723`) switches it on.
- **`chapter_document(..., render_empty=True)`** (`backend/app/classify/topic.py:320`) renders deeper units and boxes as `### Title` or `### Box: Title` subheadings inside their major topic, in book order, with no deeper number shown. It keeps a major heading that has no text of its own.
- **Prompts:** `_DOCUMENT_SYSTEM_MAJOR` and `_SYSTEM_MAJOR` (`backend/app/classify/topic.py:294-318`).
  - The specificity rule reads "the most specific of the listed sections".
  - Sub-headings are never answers.
  - Section 0 means chapter level.
  - The rule that a question spanning sub-sections of one parent goes to the parent is kept.
  - Used only when `TopicJudge(major_only=True)` (`:430`).
- **Answerability** reads the whole major topic. Its text in the document includes every subheading, and the quote check accepts a sentence from any of its sub-sections.
- **Gold-paper examples removed** from both topic-judge prompts in both paths (unflagged, as agreed). The replacements come from Federalism (language policy) and Water Resources (Bhakra Nangal, a dam), chapters outside the gold set (`backend/app/classify/topic.py:197`, `:202`, `:212`, `:270-271`). A test checks that no prompt contains "Index of Prohibited Books", "Fear of Print", "political parties", "nuclear" or "coal mine".

### 2C: clean subtopic nodes

- **`topic_node()`** never relabels an existing node of a book-map subject under `book_map_only_subtopics` (`backend/app/mapping/topic_node.py:167`, `:195`).
- **Map** no longer falls back to the ingest-created nodes for book-map subjects (`backend/app/api/marks.py:2498`, `:2648`). A major topic with no chunk of its own takes the book map's heading (`:2487-2496`).
- **`sections_of`** is a union over proposal rows in both map and place, via `backend/app/mapping/family_sections.py:38`.
- **Script `backend/scripts/clean_book_map_subtopics.py`**, dry run by default:
  - sorts every subtopic node into KEEP, RELABEL, ORPHAN or DEEP
  - lists the `question_skill` and `question` rows on each ORPHAN and DEEP node, with each row's target
  - with `--apply`: relabels; repoints references (deleting a duplicate instead); moves a question's section with its primary topic; deletes an ORPHAN once nothing references it, unless its code is a major topic's, in which case the node is relabelled and kept; keeps DEEP nodes
  - writes an undo file
  - a reference with no target is listed as UNRESOLVED and left in place

### 2D: families follow the cap

- **`family_sections.build()`** (`backend/app/mapping/family_sections.py`):
  - cuts each family's sections to major topics
  - lets a book-map family claim the topic it is, "0" for an introduction's family
  - marks as **deep** every family whose own unit is deeper than the cap or is a box
- **`candidates()`** drops deep families from new placements in map (`backend/app/api/marks.py:2511`, `:2652`) and place (`backend/app/api/placement.py:689`).
- **`choose_family(..., exact_sections_of=)`** (`backend/app/mapping/family.py:57`, `:84-89`) prefers the family whose own claim is exactly the section, so Coal, Petroleum, Natural Gas and Electricity never compete with Conventional Sources of Energy for 4.1.
- **Script `backend/scripts/propose_major_topic_families.py`**, dry run by default:
  - REUSE an existing family that is the major topic
  - CREATE `{subject}.CF.{slug(heading)}` only where none exists
  - REPOINT school-paper questions on deep families: each question goes to the family of its own `curriculum_section` collapsed to its major topic when that topic has a family, and to the deep family's own major topic only when it has none. The reason is printed on each REPOINT line ("by question section" or "by deep family's topic").
  - list board-paper questions as untouched
  - with `--apply`: create the families, each with one `concept_family_proposal` row claiming exactly its section; repoint; write an undo file
- **Consumers to know about:** remediation rows, reports, the insight rules and board-paper family frequencies are all keyed by family. Repointing school-paper questions changes past reports for those questions. Board papers are never repointed.

### 2E: storage

- `question.curriculum_section`, the primary `question_skill` node and `question_placement.curriculum_section` hold the collapsed section.
- The judge's fine-grained answer goes to `question_placement.curriculum_section_fine`, written by map (`backend/app/api/marks.py:2577`), place (`backend/app/api/placement.py:797`) and confirm (`:1241`).
- I chose a column over the evidence JSON because place already stores a list of references there, and changing its shape would break its readers.

### Gold fixture

`backend/tests/fixtures/sst_gold/unit_test_2026_09.json`: 55 questions, with B16 as corrected (exact 2.2 or 2.3, partial 2), and the new baseline (54 exact, 0 partial, 1 wrong) and targets. A test asserts that every exact and partial section in the key is one the topic judge is actually offered for its chapter.

### Tests added in Phase 2 (33, all passing)

| File | What it covers |
|---|---|
| `backend/tests/test_major_topics.py` | `collapse_section` per subject, boxes, flag off, the per-subject map. `capped()` and dropped secondaries. Judge answer cut before grounding. One evidence passage per major topic. 4.1 selectable with no text of its own. 2.1 never selectable. "0 Introduction". The document renders Coal, Petroleum, Natural Gas and Electricity under `## SECTION 4.1  4.1 Conventional Sources of Energy`, and Rat-Hole Mining as a box under 2. A deeper quote lands on its major topic. A box or deeper number is not an answer. Answerability over the whole major topic. Major prompts. No gold-chapter examples. Live judge prompt switch. The gold fixture fits the headings. All built from the real Minerals and Energy Resources book map. |
| `backend/tests/test_major_topic_data.py` | A short label inside a longer heading is not that heading (the Water Resources case). Union versus last-wins. Deep and box families marked. A new placement never picks a deep family. Candidates never empty. No relabel under the flag. Both scripts: dry run writes nothing, apply refuses without a backup, apply repoints and writes an undo file, board papers untouched. |
| `backend/tests/test_question_scope.py` | No three-level section from map, place or confirm. |

Full suite after Phase 2: 1181 passed, 19 skipped, and only the 12 baseline failures.

### Dry runs

Both scripts were run against a scratch SQLite database (`docs/investigation/phase2-dryruns/seed_scratch_db.py`) holding:

- the four Social Science curricula, plus Science, which `import_book_map` requires
- `scripts/import_book_map --apply`, the real book maps
- the reading-order subtopic nodes the PDF ingest makes, from the repo's own oracle `scripts/load_expected_sections.py`
- the depth-3 nodes the old mapping path created
- three **synthetic** questions so the reference listing has rows to show: C/23 on `X.POL.PARTIES.S4 "Functions"`, B/19.3 on `4.1.2 Petroleum`, and B/16 on the `2.1` box

A byte comparison confirmed that neither dry run changed the database. Full outputs are in `docs/investigation/phase2-dryruns/`.

| Script | Summary line |
|---|---|
| `clean_book_map_subtopics` | KEEP 0, RELABEL 100, ORPHAN 246, DEEP 44 |
| `propose_major_topic_families` | REUSE 260, CREATE 3 (introductions of Making of a Global World, Sectors of the Indian Economy, Money and Credit, which the book map gives no family), deep families 49, REPOINT 2, board questions left alone 0 |

An `--apply` of the cleanup script on a copy of the scratch database moved the synthetic questions to `1.2 Functions`, `4.1 Conventional Sources of Energy` and `2 Mode of Occurrence of Minerals`. Re-planning afterwards gave KEEP 177, RELABEL 0, ORPHAN 0, DEEP 44, so a second run changes nothing.

### Commands for you (staging copy only)

```bash
cd backend
python -m scripts.clean_book_map_subtopics            > clean-plan.txt   # read it
python -m scripts.propose_major_topic_families        > families-plan.txt
# after a backup:
python -m scripts.clean_book_map_subtopics --apply --i-have-a-backup
python -m scripts.propose_major_topic_families --apply --i-have-a-backup
# then, per environment:
#   YAADHUM_TOPIC_DEPTH_CAP=true YAADHUM_TOPIC_MAJOR_ONLY_DOCUMENT=true
#   YAADHUM_BOOK_MAP_ONLY_SUBTOPICS=true
```

Run the subtopic cleanup before switching on `book_map_only_subtopics`. With the flag on and the cleanup not yet applied, a node whose code collides, such as `S3 "Meaning"` for section 3 "National parties", keeps its wrong label until the script relabels it.

## Book-map fixes from the audit (approved)

Reference data, with the matching Markdown for each change:

| Unit | Before | After | Why |
|---|---|---|---|
| `X.GEO.WATER.4` Bamboo Drip Irrigation System | section `4` | box `3.1` under 3 Rainwater Harvesting | A picture-only feature printed after Rainwater Harvesting on p45, not a section. |
| `X.GEO.LIFELINES.1.7` Digital India | box `1.7` under 1 Transport | box `2.1` under 2 Communication | Its text is on p97; Communication starts on p95. |
| `X.ECO.SECTORS.6`, `X.ECO.MONEYCREDIT.8`, `X.ECO.GLOBALISATION.9` SUMMING UP | numbered 6, 8, 9 | unnumbered | These are summaries, not sections. |
| `X.HIST.GLOBALWORLD.2.4b` Indentured Labour Migration from India | `2.4` (the book prints 2.4 twice) | `2.4b` | Each 2.4 heading keeps its own topic. |

The Minerals nesting (Ferrous and Non-Ferrous under "Mode of Occurrence") matches the book's own heading levels and is unchanged.

Code needed for these changes:

- **`2.4b` is a valid section number.**
  - `clean_sections` and the subtopic-code parser (`SECTION_CODE`) accept one trailing lowercase letter, so the topic code is `X.HIST.GLOBALWORLD.S2_4b`.
  - `book_map.section_key` sorts sections in book order (2.4 < 2.4b < 2.5 < 2.10). The topic list, the chapter document, the cleanup script and `major_headings` all use it.
  - `depth("2.4b")` is 2, so the section is not cut down.
  - The label-to-words helpers strip "2.4b " as the number, not as the word "b".
- **Section 0 belongs to the introduction.**
  - `family_topic` returns "0" only for the introduction's family.
  - A summary or conclusion family is now deep: it is kept for questions already filed on it but never chosen for a new placement. This affects Nationalism in India and Industrialisation (Conclusion) and Sectors, Money and Credit and Globalisation (Summing Up).
  - Their text is still chapter-level evidence under "0".

Tests: 8 new tests in `tests/test_major_topics.py`. The full suite gives 1190 passed, 19 skipped and the same 12 known failures. Ruff finds no new errors.

## Dry runs on the backup (Part B) and the fixes from them

Both scripts were dry-run on a restored copy of the backup in a throwaway local Postgres. The database and the dump were deleted afterwards, and nothing was applied anywhere.

- **Cleanup script totals:** KEEP 30, RELABEL 86, ORPHAN 237, DEEP 10.
- **Families script totals:** REUSE 257, CREATE 3, deep families 55, REPOINT 61.
- **Questions touched:** all are in Minerals and Energy Resources. DEEP lines touch 62 questions and REPOINT lines touch 61.
- **Unresolved references:** none.

Fixes made after that run:

- **`clean_book_map_subtopics`:** a DEEP node's topic links now follow the question's own collapsed section first. This is the same rule the family repoint uses. The node's own major topic is used only when the question's section is no topic. The backup's case was a link on 4.1.4 Electricity whose question sits in 4.2.1; it now goes to 4.2, not 4.1.
- **Deep conclusion and Summing Up families:**
  - They print "chapter level" instead of "major topic ?".
  - When the repoint has to fall back on the family, these families fall back to "0", because their text is chapter level.
- **The old `S2_4-2` subtopic** (Indentured Labour) is an ORPHAN pointing at 2.4b. Approved as is.

## Introductions titled for their content (approved)

Nine introductions carry examinable content. Their unit title in the book map (JSON and Markdown) now names it, and the number stays 0:

- Nationalism in Europe: "Introduction: Sorrieu's Vision and the Nation-State"
- Nationalism in India: "Introduction: Nationalism and the Anti-Colonial Movement"
- Industrialisation: "Introduction: Images of Industrial Progress"
- Resources and Development: "Introduction: Types and Classification of Resources"
- Forest and Wildlife: "Introduction: Biodiversity and the Role of Forests"
- Water Resources: "Introduction: Freshwater and the Hydrological Cycle"
- Minerals and Energy: "Introduction: Importance of Minerals"
- Manufacturing: "Introduction: What Is Manufacturing"
- Lifelines: "Introduction: Need for Transport, Communication and Trade"

Where the new title shows up:

- **Topic list:** `book_map.intro_label` makes section 0 show the title when it starts with "Introduction:". Every other introduction, including Politics' printed "Overview", shows as "0 Introduction".
- **Family labels:** these take the unit title when the book map is next imported. That import has not been run anywhere.
- **Old "0 Introduction" subtopic nodes:** the cleanup script relabels them to the titled form.

An introduction titled this way also stops matching the "not a learning area" rule ("Introduction"). That is intended: these introductions carry content a student can be weak at.

## Phase 3: the Topic column always shows the final decision

The Topic column shows a question's primary `question_skill` node. Reports read `question.curriculum_section`. Phase 3 makes the two always agree, and makes each reader's choice deterministic. There are no new settings and no migration.

### 3.1 One writer for topics
- **Map step.** It no longer inserts `question_skill` rows directly. It writes through `set_question_topic`, the same writer the place run and the review settle use:
  - the primary topic at weight 1.0;
  - the judge's collapsed `also` sections at 0.5;
  - every earlier machine row (`retrieval`, `model`, `classify`) replaced.
- **Case-study sub-part (map step).** A sub-part that borrows a sibling's chapter no longer keeps the sibling's topic once the topic judge gives it a different section of its own.
- **Skill-anchored question (place).** When the judge says a question has no chapter, its machine topic rows are removed together with its section. Before, the map step's topic stayed in the column.
- **A person's settle is final.** If a person chose the question's topic (a review settle, or an imported Q-matrix), a later place run changes nothing on the question: not the chapter, section, family or topic.
  - The run still appends its placement row, prefixed "Not applied: a person settled this question." and not flagged for review.
  - Before, the place run rewrote the question's chapter and section while the person's topic stayed. That is exactly the disagreement 3.2 forbids.
  - `set_question_topic` now checks for a person's row before it touches any node, so a refused machine call no longer relabels nodes either.

### 3.2 Section and topic agree
- **Write-phase guard.** `topic_mismatches` / `assert_topic_matches_section` (in `app/mapping/topic_node.py`) run before each write phase commits: the map step, the place run and the review settle.
  - Every question whose topic the phase wrote must show its stored section as its primary subtopic.
  - A mismatch raises `TopicSectionMismatch`. The job then fails without committing anything (the review settle returns 500).
  - Only questions written in that phase are checked, so older rows can't fail a new run.
- **Read-only listing.** `scripts/list_topic_mismatches.py` lists existing mismatches (`--assessment`, `--subject`).
  - It has no `--apply`: a mismatch is fixed by re-running place or by settling the question in review.
  - On the scratch database it finds the synthetic B/19/19.7 row (section 4.2.1, topic 4.1.4).

### 3.3 Deterministic Topic tie-break
`primary_order` sorts topic rows by weight, heaviest first, then by id. The scan screen and the reports both use it. `question_skill` has no creation time, so the id is the stable tie-break; adding a `created_at` would need a migration.

### 3.4 Tiers: the newest named tier wins
- `app/classify/current_tier.current_tiers` reads `question_tier` ordered by `created_at` then id. The newest row that names a tier wins, so an abstain (tier None) never erases a tier.
- All three readers use it: `marks.read_scan`, `reports._rows` and `academics.resolved_rows`.
- Before, none of them ordered the rows, and `academics` let a later abstain blank the tier.

### On the real data (your check of the backup)
- **Mismatches.** Only assessment `32ebf883` has topic/section mismatches: 21 of its 55 questions, all retrieval-sourced topic rows left from an older run. Every other paper has 0.
  - `python -m scripts.list_topic_mismatches` should report exactly **21** on staging, all on that paper.
  - Re-running place on that paper resolves them, and so does retiring it as a duplicate (Phase 5). No fix script is needed.
- **Settled questions.** No `question_skill` or `question_placement` row in production is person- or import-sourced today, so the "a person's settle is final" rule (3.1) changes nothing on existing data.

### Tests (11 new, `tests/test_topic_column.py`)
- Machine rows replaced, with primary 1.0 and secondaries 0.5.
- A secondary that collapses onto the primary keeps 1.0.
- A machine call never overrules or relabels a person's topic.
- A place run leaves no stale retrieval row.
- A place run after a person's settle changes nothing on the question.
- A skill-anchored question keeps no topic.
- The guard refuses a mismatch.
- The listing script is read-only.
- The tie-break is deterministic.
- The newest named tier wins.
- All three readers use the one tier rule.

## Phase 4: review flags that mean something

### Settings (both off by default)
- `cite_passages_by_number` (`YAADHUM_CITE_PASSAGES_BY_NUMBER`)
- `review_flag_rule` (`YAADHUM_REVIEW_FLAG_RULE`)

With both off, the judge's request and every flag are exactly as before. The reasoning truncation (4.3) is unflagged, as agreed.

### 4.1 Citations by passage number
- **The judge cites numbers.** With the flag on, the chapter judge answers with `NumberedClassification` (or `NumberedScopedClassification` when scoped), whose `evidence` is `list[int]`: the `[n]` printed before each passage. The system prompt gains `CITE_NOTE` (`app/classify/judge.py`).
- **The numbers are checked.** `grounding.resolve_citations` checks each number against the passages actually shown (1..n) and turns it into the passage's reference, so everything downstream still reads references.
- **String matching is only a tolerant fallback.** A string citation is still read if it is one of:
  - a bare number or `[n]`;
  - the printed passage line `"{chapter} -- {reference} (section n)"`, with or without its `[n]` and section;
  - a bare reference;
  - a quote of at least 12 characters found in exactly one shown passage.
- **A citation problem is a warning only.** It goes into `Grounded.warnings`, never into `violations`, and never caps confidence at 0.4.
  - The judge keeps them as `citation_warnings`, and the place job result reports them under `citation_warnings`.
  - A scoped answer keeps its `no_in_scope_chapter` signal through grounding.
  - The other checks (chapter, section, tier) are unchanged.

### 4.2 Seven reasons, stored on the row
`app/classify/review_rule.py` holds the rule. A row is flagged only for the following (`blueprint_overruled` was added after review; a thin margin between the judge's top two chapters stays dropped):

| Code | Condition |
|---|---|
| `judge_failed` | the chapter judge could not be asked |
| `cross_scope` | the placement left the declared scope |
| `blueprint_overruled` | the paper's declared blueprint (marks per chapter) moved the question to a chapter other than the chapter judge's |
| `family` | the family is unsettled (several claim the section) or blocked; this includes a family refused because the question moved to a chapter whose families cannot place it |
| `low_confidence` | the chapter judge's **own** confidence is below 0.7, and it chose among **more than one** chapter |
| `topic_differs` | the topic judge's section differs from in-chapter retrieval's (a parent and its own sub-section do not differ), and answerability did not verify it |
| `topic_unverified` | answerability found that no section of the chapter can answer the question, or the topic judge gave no answer and retrieval decided |

- **Stored reason.** `question_placement.review_reason` holds every applicable code, comma-joined in that order (whole codes only, at most 64 characters). It is set on every flagged row and null on every unflagged one.
- **Place.** The pipeline now records the chapter judge's own confidence and how many chapters it chose among (`PlacedQuestion.judge_confidence`, `chapters_shown`). A skipped or failed judge has none, so `low_confidence` cannot fire for it. The thin-margin check no longer flags on its own.
  - The job's `needs_review` is the number of rows flagged.
  - A new `flagged_by_reason` breaks them down.
  - A question a person settled is never flagged (Phase 3).
- **Map.** The map step uses the same rule with the inputs it has: the family, and the topic pick unless the classify job queued behind the map decides the topic (a provisional topic is no doubt). There is no chapter judge at map time.

### 4.3 Reasoning fits its column (unflagged)
A validator on `QuestionPlacement.reasoning` (`app/models/assessment.py`) cuts it to 1000 characters before insert. It covers map, place and review alike, so an over-long reasoning can no longer fail a Postgres write phase.

### The gold paper under the new rule (959e36d4)
**From your analysis of the backup** (the replay was not re-run here):
- **Flagged today:** 39 of 55 rows.
  - The 38 low-confidence rows are all at exactly 0.4.
  - The place job's `grounding_violations` show all 38 were citation-only problems; the 0.4 cap applied to them is gone under `cite_passages_by_number`.
  - No row carries a family, topic-differs, topic-unverified or judge-failed reason.
- **Expected under the new rule: about 1–2 flags.** That assumes the citation cap is gone and single-chapter scopes skip the chapter judge (`skip_single_chapter_judge`), so `low_confidence` cannot fire for them. **This is an estimate; Phase 6 measures it.**

**The replay script.** `python -m scripts.replay_review_flags --assessment <id>` applies the rule offline to a paper's stored placements. It is read-only, and it reports a condition as **unknown** where its input was not stored:

| Condition | Stored? |
|---|---|
| `judge_failed`, `cross_scope`, `blueprint_overruled`, `family`, `topic_unverified` | yes, from the reasoning texts, the `cross_scope` column, or `source = "blueprint"` |
| `low_confidence` | partly: 0.7 or above is a known no; below 0.7, or a blueprint row, is unknown, because the number of chapters the judge saw is not stored |
| `topic_differs` | partly: a disagreement note without answerability's verdict is unknown; no note is read as no (inferred) |

### Tests (42 new, `tests/test_review_flags.py`)
- **Citations:**
  - every citation form resolves;
  - every invalid citation is a problem;
  - a problem is a warning with the confidence unchanged;
  - the scoped signal survives grounding;
  - with the flag off, the old cap still applies;
  - the live judge asks for numbers and returns references;
  - with the flag off, the live judge is unchanged.
- **Review rule:**
  - each of the six reasons, and the cases that must not flag;
  - stored-code width and order;
  - the map step's rule, including a provisional topic;
  - the pipeline records the judge's own confidence, and none for a skipped judge;
  - every flagged row of a place run carries a reason.
- **Truncation:** reasoning is cut to 1000 characters on insert.
- **Replay:** every stored condition is read; unknown is reported where an input wasn't stored; map rows and settled rows are handled; the script is read-only.

## Phase 5: stop duplicate papers

**On real data, a hash check alone catches none of the copies.** The five uploads of the gold paper have five different `source_sha256` values (0b8baeb0b534, 657f581b3272, 72cb39ad63da, 5b3d5893337a, 76b08d3d1ec6) and two titles ("Bharath Social", "Cycle Test I"). The merged PDF's bytes change between uploads even when the pages are the same. So the hash check is kept because it is cheap, but the content check is the one that finds them.

### Settings (both off by default)
- `duplicate_upload_check` (`YAADHUM_DUPLICATE_UPLOAD_CHECK`): 5.1
- `auto_pipeline_dedupe` (`YAADHUM_AUTO_PIPELINE_DEDUPE`): 5.2

### Migration `f3a9c6d2b8e1` (additive, three nullable columns on `assessment`)
| Column | Holds |
|---|---|
| `source_file_hashes` (JSON) | sha256 of each original uploaded file, before the pages are merged |
| `class_section_id` (FK `section.id`, indexed) | the class section a paper is for, as approved earlier |
| `duplicate_check` (JSON) | the matches found, and the teacher's decision |

`downgrade()` removes all three. Tested on SQLite and on Postgres 16: upgrade, downgrade, upgrade. **Run `alembic upgrade head` on staging before the scripts below**; a database without these columns cannot be read by the new model.

### 5.1 The hash check and the content check (`app/extraction/duplicates.py`)
- **Hash check.** The scan route hashes each original file before `pages_to_pdf` merges them, and stores the hashes on the paper. The vision path stores them in the request, before the job runs.
- **Content check, after extraction and before mapping.** `_finish_paper_scan`, used by both the text and vision routes, compares this paper's normalised question stems with every other paper of the same school and subject.
  - It uses the same `stem_hash` the question rows store.
  - For a paper that was never mapped, it uses the staged scanned questions instead.
  - A paper matches if it shares an original file's hash, or if **at least 70% of this upload's stems** are on it. Matches are listed most similar first.
  - Two papers that both know their class section, and differ, are never matched. If either side's section is unknown, the match is shown and the teacher decides.
- **Nothing is reused automatically.** A match is returned in the scan result (`duplicates`: id, title, exam, created, overlap, how it matched, question count), stored in `duplicate_check`, and shown in the paper list (`duplicates_pending`).
  - **No model call is spent while it waits:** the automatic map and classify are not queued.
  - The teacher answers at `POST /assessments/{id}/duplicates/decision`:
    - `open_existing` (with one of the matched ids) records the choice and names the paper to open. The new upload is left as it is; nothing is deleted.
    - `keep_new` records the choice and starts the automatic pipeline it held back.
  - A teacher who presses Map by hand is not stopped.
- **Frontend.** `submitScan` (`frontend/lib/usePaperScan.ts`) asks with a confirm dialog: "This looks like a paper you already have: … N% of its questions match". OK opens the existing paper; Cancel keeps the upload as new and follows its pipeline. `api.decideDuplicate` and the new types are in `frontend/lib/api.ts`.
  - **Limit:** a scan resumed after a lost connection (`resumeScanJob`) does not ask. The match stays pending, so nothing is mapped, and the list shows it as `duplicates_pending`.
- **Paper creation.** `POST /assessments` takes `class_section_id`, checked to be one of the school's sections. The frontend does not send it yet.

### 5.2 One map/classify pair at a time
With `auto_pipeline_dedupe` on, `_queue_auto_pipeline` returns the pending jobs, marked `already_queued`, while a map or classify job is already pending for the paper, and the caller starts nothing. This applies to both scan routes and to `keep_new`. The manual Map route already refused a second run.

### 5.3 `scripts/list_duplicate_assessments.py` (read-only, no `--apply`)
- **How papers are grouped.** Two papers of the same school and subject are linked by a shared file hash, the same merged-PDF hash, or a stem overlap of at least 70% from either side. Linked papers form groups (union-find), and papers with known, different class sections are never linked.
- **What it prints.** Each group lists every paper with its id, title, created time, exam (the one linked to the exam is marked `<- linked to the exam`), stem and question counts, overlap with the group's first paper, what linked it, its sha256 prefix, and its job counts.
- **On the backup it should report one group of 5:** 32ebf883, 2654797a, 6253a5c9, 03c447fd and 959e36d4, with 959e36d4 marked as linked to the exam. `tests/test_duplicate_papers.py::test_the_listing_finds_the_backups_five_copies_as_one_group` reproduces that shape: five papers, five different hashes, two titles, one with a misread stem, one with a short read, one linked to an exam. Alongside them are a different paper of the same subject and the same stems under another subject; neither is grouped.

```bash
cd backend
alembic upgrade head            # staging copy only
python -m scripts.list_duplicate_assessments --subject X.SST
```

### Tests (14 new, `tests/test_duplicate_papers.py`)
- **Content check:**
  - a first upload matches nothing;
  - the same file matches by hash and stems;
  - a re-made file with another title matches by stems alone;
  - 33% is not a match;
  - original files are hashed before merging;
  - a known, different class section is never a match, while an unknown one is still shown;
  - an unknown section id is refused;
  - with the setting off, nothing changes.
- **Teacher's choice:**
  - a match holds the automatic pipeline until the teacher chooses, and the list shows it pending;
  - `keep_new` starts the pipeline;
  - `open_existing` names the paper and deletes nothing;
  - a decision with no match waiting is refused.
- **Job dedupe and listing:**
  - no second map/classify pair while one is pending;
  - the backup's five copies form one group;
  - the listing writes nothing.

## Phase 6: evaluation, and the staging runbook

### Held papers in the papers list (added at the start of Phase 6)
- **The label.** A paper the duplicate check is holding shows, in both paper lists on the teacher dashboard (inside a test, and standalone): **"Possible duplicate of <title> (<overlap>%) — not mapped"**, with **Open existing** and **Keep as new** buttons. These make the same decision as the scan's dialog, so a resumed scan that showed no dialog can still be released.
  - The component is `frontend/components/DuplicateHold.tsx`; the action is `releaseDuplicate` in `frontend/lib/usePaperScan.ts`.
  - **Keep as new** starts the held-back pipeline and follows it. **Open existing** opens the matched paper.
- **When it shows.** Only while the pipeline is held. The server (`app.extraction.duplicates.held_by`, read by `assessment_summaries`) stops listing the match once the teacher has chosen, or once the paper has been mapped, for example by pressing Map by hand. That retires the "resumed scan does not ask" follow-up from Phase 5.

### `scripts/eval_mapping.py` (read-only)
- **Input.** `--assessment <id>` reads the stored paper; on Postgres the session is `READ ONLY`. `--fixture <file>` re-scores predictions saved earlier with `--export`.
- **Collapsing.** Every predicted section is collapsed to the key's two levels with `collapse_section(..., max_depth=2)`, a new optional argument, whatever the settings say. The book map decides where a box or a deeper unit belongs.
- **Scoring.** Each question is scored against `tests/fixtures/sst_gold/unit_test_2026_09.json`: chapter correct, and topic exact / partial / wrong. A wrong chapter counts as wrong on both.
- **What it reports:**
  - totals, and the same per paper section;
  - flag precision and recall, both as you specified (wrong only) and counting a partial as a miss;
  - `review_reason` counts;
  - sections stored deeper than two levels;
  - model calls, tokens and estimated cost per question, from the map and place jobs' own `spend`;
  - every miss, one line each;
  - PASS or FAIL against the key's targets.
- **`--export <file>`** writes the predictions and the scores as JSON, so a run can be re-scored after the database is gone.
- **Gold fixture.** The baseline now records the 39 flags you measured (38 citation-only, at 0.4), and the targets gain `flagged_expected: "about 1-2 (estimate)"`.
- **What a report looks like.** This is from a hand-made fixture with one partial and one flag, **not a real run**:

```
READ-ONLY -- nothing will be written
gold: Unit Test, Class X Social Science (X.SST)   run: 959e36d4-5028-42e6-922e-c69228c5c325 (illustration, not a real run)

CHAPTER  55/55
TOPIC    exact 54, partial 1, wrong 0
FLAGS    1 flagged; precision 0.0, recall None (wrong only); counting partial as a miss: precision 1.0, recall 1.0
REASONS  topic_differs 1
DEPTH    0 section(s) deeper than 2 levels
SPEND    192 calls, 76800 in / 230400 out / 1920000 cache-read tokens, ~$1.42 (place); per question 3.5 calls, 1396 in / 4189 out, ~$0.0258

BY SECTION
  sec   qs  chapter  exact  partial  wrong  flagged
  A     14       14     14        0      0        0
  B     16       16     15        1      0        1
  C     14       14     14        0      0        0
  D     11       11     11        0      0        0

MISSES (1)
  B/16//       partial  section 2 -> 2; key exact ['2.2', '2.3'] partial ['2']; flagged [topic_differs]

TARGETS
  PASS  chapter: 55/55 (target 55)
  PASS  topic exact: 54 (target >= 54)
  PASS  flags: 1 (target <= 8; expected about 1-2 (estimate; Phase 6 measures it))
  FAIL  flag precision: 0.0 (target >= 0.5)
  PASS  no 3-level section: 0 deeper than 2
```

### Format robustness F1–F4
These were complete from Phase 1. All tests use mocked models.
- `tests/test_question_scope.py`:
  - F1: a section title naming a chapter, and a subject-only title;
  - F2 and F4: type-only titles ("SECTION A — MCQs") and no titles never narrow by letter;
  - bilingual type titles and bilingual subject titles;
  - F3: syllabus lines;
  - teacher scope precedence;
  - the old `declared` shape;
  - map and place end to end with the flags on and off;
  - a board Section A is never forced into History.
- `tests/test_resolve.py`: spelling variants, short names through aliases, Hindi subject words, chapter numbers, close names that must not cross-match, and low-scoring or unclear text resolving to nothing.

### `scripts/apply_undo.py` (new, for rollback)
- **What it does.** It reverses an applied run from the undo file it wrote, newest entry first: an inserted row is deleted, an updated row gets its old values back, a deleted row is re-inserted with its old id.
- **Conflicts.** It first checks each row is still as the run left it; a row changed since is a CONFLICT, and nothing is written without `--force`.
- **Safety.** It is a dry run by default, `--apply` needs `--i-have-a-backup`, and it writes its own undo file.
- **Test.** An applied subtopic cleanup reversed by its undo file returns the database to exactly where it was (`tests/test_major_topic_data.py`).

### Tests (Phase 6)
- `tests/test_eval_mapping.py`: 12 tests.
  - a perfect run is 55/55 and passes every target;
  - each kind of miss is scored and listed;
  - predictions are collapsed with the book map (Coal 4.1.1 → 4.1; the Rat-Hole Mining box 2.1 → 2);
  - a three-level section is reported;
  - flag precision and recall, both ways, and the reason counts;
  - spend per question;
  - export then offline re-score gives the same scores;
  - a stored paper is read and scored without writing;
  - argument checks, and the depth override.
- `tests/test_duplicate_papers.py`: 7 more, covering the held label and the `held_by` rule.
- `tests/test_major_topic_data.py`: the undo round trip.

## Staging runbook (staging copy only, never production)

Follow it in order. Each step says what it should print. `$STAGING` is the staging connection string, which you set yourself; nothing here prints it. Every script is run from `backend/`, with `YAADHUM_DATABASE_URL` and `YAADHUM_MIGRATION_DATABASE_URL` pointing at the staging copy. `$API` is the staging API, `$KEY` a school admin key for the gold paper's school, and `GOLD=959e36d4-5028-42e6-922e-c69228c5c325`.

**0. Before you start.**
- Set `YAADHUM_AUTO_PIPELINE=false` on the staging backend for the whole run, so nothing maps or classifies by itself; step 8 starts place explicitly.
- The staging backend needs `YAADHUM_ANTHROPIC_API_KEY` for step 8. Paid calls happen only in step 8, and in 7b's vision read if the PDF has no text layer.
- Keep every undo file the scripts write.

**1. Restore a fresh backup.**
```bash
createdb yaadhum_staging            # or drop and recreate the staging database
gunzip -c yaadhum_backup.sql.gz | psql "$STAGING" -q -v ON_ERROR_STOP=0 2>restore_errors.log
grep -c ERROR restore_errors.log
```
*Expect:* only ownership noise. On the reduced backup that was 51 × `role "yaadhum" does not exist` and 1 × `unrecognized configuration parameter "transaction_timeout"`. Any other ERROR line is a real failure; stop.

**2. Migrate.**
```bash
alembic upgrade head
```
*Expect* exactly these two upgrades (the backup is at `c4e8a1f7b2d9`):
`Running upgrade c4e8a1f7b2d9 -> e2b7c4a9d1f3` (placement columns) and `Running upgrade e2b7c4a9d1f3 -> f3a9c6d2b8e1` (duplicate-check columns).

**3. Re-import the book map.** This carries 2.4b, the box fixes, the unnumbered Summing Up and the titled introductions into the database.
```bash
python -m scripts.import_book_map             # dry run: read it
python -m scripts.import_book_map --apply
```
- *Expect (dry run):* `Chapters matched` 5 / 7 / 5 / 5 for X.HIST / X.GEO / X.POL / X.ECO, and `Concept families in the new map` 95 / 120 / 42 / 55.
- Any old family that still has questions is listed and left alone. Then `Dry run only -- nothing was changed`; after `--apply`, `Applied.`
- Existing families keep their ids, and their labels are refreshed: the nine introductions get their new titles.
- **Embeddings:** the re-imported chunks have none. Retrieval then runs on its lexical index, which the pipeline already supports; the topic judge reads each chapter's whole text either way. To restore semantic retrieval, run `python -m scripts.embed_kb --subject X.HIST --dry-run` (then without `--dry-run`) for each of the four subjects. **That calls Jina, a paid API**, so it is your call. The baseline run's embedding state is not recorded, so do the same thing for before and after if you compare.

**4. Aliases and the two topic scripts.** Dry run, check, then apply, in this order.
```bash
python -m scripts.list_topic_mismatches                         # before anything is applied
python -m scripts.seed_sst_aliases
python -m scripts.seed_sst_aliases --apply --i-have-a-backup
python -m scripts.clean_book_map_subtopics                      > clean-plan.txt
python -m scripts.clean_book_map_subtopics --apply --i-have-a-backup
python -m scripts.clean_book_map_subtopics                      > clean-after.txt
python -m scripts.propose_major_topic_families                  > families-plan.txt
python -m scripts.propose_major_topic_families --apply --i-have-a-backup
```
*Expect:*
- **`list_topic_mismatches`:** `TOTAL 21 question(s) on 1 paper(s)`, all on `32ebf883`. Run it here, before the cleanup moves topic links.
- **`seed_sst_aliases`:** about 19 alias rows to insert and 2 skipped (that was the scratch database), then the same count applied.
- **`clean-plan.txt`:** `TOTAL KEEP 30, RELABEL 86, ORPHAN 237, DEEP 10`, as in Part B. The B/19/19.7 link on 4.1.4 Electricity now goes to **4.2** (the question's own section). No UNRESOLVED lines touch real questions.
- **`clean-after.txt`:** no RELABEL, ORPHAN 0, DEEP 10 (deep nodes stay).
- **`families-plan.txt`:** `TOTAL REUSE 257, deep families 55, REPOINT 61, board questions left alone 0, CREATE 3`. The three CREATEs are the introductions of Global World, Sectors and Money and Credit. Conclusion and Summing Up families print `-> chapter level (kept, unused)`.

**5. The two listings.**
```bash
python -m scripts.list_topic_mismatches
python -m scripts.list_duplicate_assessments --subject X.SST
```
*Expect:*
- **`list_topic_mismatches`:** at most 21, all on `32ebf883`. It reported exactly 21 before step 4; the cleanup can only make some of them agree, by moving a deep link to the question's own section. Re-running place on that paper, or retiring it as a duplicate, resolves the rest.
- **`list_duplicate_assessments`:** one group of 5 (`32ebf883`, `2654797a`, `6253a5c9`, `03c447fd`, `959e36d4`), linked by `stems`, never `hash`, with `959e36d4` marked `<- linked to the exam`. The Maths paper is in no group.

**6. Turn the flags on, in this order** (environment variables on the staging backend, then restart it):
1. `YAADHUM_TOPIC_DEPTH_CAP=true`, `YAADHUM_TOPIC_MAJOR_ONLY_DOCUMENT=true`, `YAADHUM_BOOK_MAP_ONLY_SUBTOPICS=true` (Phase 2; the cleanup is already applied)
2. `YAADHUM_SST_UNIFIED_SCOPE=true`, `YAADHUM_SKIP_SINGLE_CHAPTER_JUDGE=true`, `YAADHUM_BALANCED_GROUP_CANDIDATES=true`, `YAADHUM_CROSS_SCOPE_FALLBACK=true` (Phase 1 scope)
3. `YAADHUM_CITE_PASSAGES_BY_NUMBER=true`, `YAADHUM_REVIEW_FLAG_RULE=true` (Phase 4)
4. `YAADHUM_PAPER_CAPTURE_STRUCTURE=true` (Phase 1.1; needed for step 7b)
5. `YAADHUM_DUPLICATE_UPLOAD_CHECK=true`, `YAADHUM_AUTO_PIPELINE_DEDUPE=true` (Phase 5). These only act on uploads and the automatic pipeline, which is off for this run.

*Expect:* the backend starts normally, and the gold paper's Topic column is unchanged until step 8.

**7. Give the gold paper its scope.** Pick one; **7b is recommended**, and it is what the expected results in step 8 assume.
- **7a (scope only).** `curl -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" $API/assessments/$GOLD/scope -d '{"chapters":["X.HIST.PRINTCULTURE","X.GEO.MINERALSENERGY","X.POL.PARTIES","X.ECO.GLOBALISATION"]}'`. Every question is then scoped to all four chapters, so **the chapter judge is asked for all 55**. Its confidence below 0.7 with four chapters to choose from is a `low_confidence` flag, and the cost is about $1 more (see the estimate below).
- **7b (re-scan once; tests header capture).** Download the stored paper and send it back:
  ```bash
  curl -H "X-API-Key: $KEY" $API/assessments/$GOLD/documents             # note the question_paper document id
  curl -H "X-API-Key: $KEY" $API/documents/<doc-id>/pages/0 -o gold.pdf
  curl -H "X-API-Key: $KEY" -F files=@gold.pdf $API/assessments/$GOLD/scan
  ```
  - *Expect:* the scan response lists `duplicates` (the four other copies) and no `auto`, because the pipeline is off and held. Already-mapped questions are kept (`already_promoted`). The re-scan clears the scan's confirmation, which place does not need.
  - `GET $API/assessments/$GOLD/scan` → `declared.section_titles` should hold A–D with each section's printed title, e.g. "Geography : Minerals and Energy Resources". Each question then resolves to one chapter, and the chapter judge is skipped.
  - Answer the duplicate question with **Keep as new** (`POST $API/assessments/$GOLD/duplicates/decision -d '{"choice":"keep_new"}'`). It records the choice; with the automatic pipeline off, nothing runs.
  - A text-layer PDF re-scans without a model call; a scanned PDF goes through the vision reader, which is one paid call per page.

**8. Re-run place on the gold paper, then score it.**
```bash
curl -X POST -H "X-API-Key: $KEY" $API/assessments/$GOLD/place      # -> {"job_id": ...}
curl -H "X-API-Key: $KEY" $API/assessments/$GOLD/place/jobs/<job_id> # poll until "succeeded"
python -m scripts.eval_mapping --assessment $GOLD --export gold-after.json
```
- The topic judge goes through the Batches API (`batch_classify`, on by default), so the job can take from a few minutes to about an hour.
- *Expected results:*
  - **chapter 55/55**;
  - **topic ≥ 54 exact**;
  - **flags ≈ 1–2** (an estimate, from your analysis of the backup; this run measures it);
  - **no 3-level section** (`DEPTH 0`);
  - every TARGETS line PASS, except possibly `flag precision`, which is noisy at one or two flags. Read it with the partial-as-a-miss figure beside it.
- The SPEND line gives the measured cost; compare it with the estimate below.
- Keep `gold-after.json`: it re-scores offline with `--fixture`.

**9. Roll back.**
1. **Flags off.** Unset the variables from step 6, newest group first, and restart. Every path is then as before. Nothing the flags wrote needs undoing to run with them off; the new columns are nullable and unread.
2. **Undo the data scripts**, newest run first: `propose_major_topic_families`, then `clean_book_map_subtopics`, then `seed_sst_aliases`.
   ```bash
   python -m scripts.apply_undo undo-propose_major_topic_families-<time>.json      # dry run: 0 conflict(s)
   python -m scripts.apply_undo undo-propose_major_topic_families-<time>.json --apply --i-have-a-backup
   ```
   Repeat for the other two files.
3. **The book-map re-import** (step 3) has no undo file; it replaces chunks and proposals wholesale. Restore the backup if it must be reverted.
4. **The migration:** `alembic downgrade e2b7c4a9d1f3` removes the Phase 5 columns, and `alembic downgrade c4e8a1f7b2d9` removes the Phase 1 ones. Both were tested on Postgres 16.
5. **Last resort:** restore the step 1 backup.

## Cost of step 8 (estimate, current price table)
- **Model and price.** The model is `claude-sonnet-5` at medium effort. `PRICES_PER_MTOK` in `app/llm.py` gives $2 per million input tokens, $10 per million output and $0.20 per million cache reads; the Batches API halves all three.
- **The four chapters' text.** Measured from the book map: Print Culture ≈ 12.7k tokens, Minerals ≈ 6.7k, Parties ≈ 7.3k, Globalisation ≈ 7.1k. Weighted by questions, that averages 8.5k per question, read from the prompt cache.
- **Topic judge per question:** the answer and taught reads, about 1.2 answerability checks and about 0.3 confirm/relocate reads, so about 3.5 calls. Each reads about 10k cached tokens and 0.4k fresh input, and writes 0.7–2.5k output tokens including thinking.
- **Chapter judge** (7a only): one live call per question, about 3.8k input (8 passages × 1200 characters, plus the prompt) and about 1k output.

| | low | mid | high |
|---|---|---|---|
| Topic judge (batched, the default) | $0.81 | $1.42 | $3.82 |
| Chapter judge, 7a only (55 live calls) | +$0.80 | +$0.97 | +$1.52 |
| **Step 8 with 7b** | **≈ $0.8** | **≈ $1.4** | **≈ $3.8** |
| **Step 8 with 7a** | ≈ $1.6 | ≈ $2.4 | ≈ $5.3 |

- **Uncertainty.** Output tokens, mostly thinking, are the largest and least certain term, which is why the range is wide. The midpoint is about 2.6 cents per question with 7b.
- **Not counted:** cache writes (about 4 × 10k tokens, roughly $0.10; the price table does not count them, see the investigation report), and the vision reader if 7b re-scans a scanned PDF.
- **Measurement.** The place job's `spend`, printed by `eval_mapping.py` as SPEND, is the measured figure.

## Text reader gated (before the production rollout)
The text route's title and syllabus scan (`_structure` in `app/extraction/paper.py`) now runs only when `paper_capture_structure` is on. Before, it always ran and its result was dropped when the setting was off.

With the setting off, question-paper reading is now the same code path as production's `4e97dfa`:
- the vision reader sends the same prompt and output format;
- the text reader does no extra work;
- nothing new is stored or returned.

The test `test_with_the_flag_off_the_text_route_never_scans_for_titles` proves the scan is never called with the setting off, and called once per read with it on.

## Fixes from the pre-deploy code review
A code review of the whole branch against production (`4e97dfa`) found three things worth fixing before the rollout. Each is fixed and tested.

- **`apply_undo.py` and rows changed twice.** A run that changed one row twice (several duplicate links merged into one twin) left the row holding only the last value, so the undo reported the earlier change as "changed since the run", refused to apply, and under `--force` left an intermediate value. `plan()` now checks each step against the row as it will be once the later steps are reversed, tracked in memory with nothing written. A real later edit is still a conflict.
- **"Keep as new" is idempotent.** A second call (double-click, a second tab, a retry) returns the earlier decision with `already_decided` and starts nothing, so it can no longer queue a second map-and-classify pair even with `auto_pipeline_dedupe` off.
- **No dialog on a duplicate match.** Dismissing the old confirm dialog counted as "keep as new" and started the paid pipeline. The dialog is gone: a matched scan stays held, and the "Possible duplicate … — not mapped" banner with Open existing and Keep as new buttons shows on the paper screen as well as in the papers list. `DuplicateHold` now takes the matches and one callback.

**Reviewed and left as is** (listed in the review, none touches the production plan):
- A borrowed case-study sub-part is not flagged under `review_flag_rule`, because it is not one of the seven reasons. This is a decision for you.
- The topic judge's base prompts changed for every subject. This is the approved removal of the gold paper's examples.
- Findings in code behind settings that stay off in production (`cross_scope_fallback`, `paper_capture_structure`, `balanced_group_candidates`):
  - a chapter-judge "no fit" answer whose second look fails goes unflagged;
  - the syllabus pattern can match question text;
  - an out-of-scope retry gets a different result in balanced mode;
  - the job's settled and blueprint figures are not recomputed after a cross-scope move.

## Follow-ups (not done)

- **The paper-creation screen should send `class_section_id`** when it knows the section, so two classes' copies of one test are never offered as duplicates.
- ~~A scan resumed after a lost connection should ask the duplicate question too~~: done in Phase 6. The papers list shows the held label with both actions.

- **Twelve order-dependent baseline test failures.** They pass alone and fail in the full run, through shared test-client state (for example, a stubbed judge that is not the one the run uses). Until this is fixed, a new end-to-end test can't be fully trusted in the full suite. Phase 3 had to drop the second half of one test for this reason.

- **Show GEO, POL and ECO topic labels in the teacher UI without the number prefix.** Their numbers are reading order, not printed in the books. Keep the numbers in stored codes, and keep them for History, where they are printed. This is not a one-line change: the label reaches the teacher through several API fields and the xlsx and PDF exports, so it needs one display helper used at each of those places.

## Section cards and the one-call topic read (default OFF: `YAADHUM_TOPIC_CARD_MODE`)

* `backend/reference/book_map/section_cards.json`: one card per major topic of all 22 Social
  Science chapters (heading, opening, ~18 key terms: glossary terms, box titles, names, years,
  rare words). 27.7k tokens in all against 172k of full text. Rebuild with
  `python -m scripts.build_section_cards`; `--check` fails when stale or a topic has no card.
* `app/classify/section_cards.py`: chunk-level BM25 (a section scores its best chunk plus 0.3 x
  its next two). On the gold paper: right section first 43/54, in the top three 51/54 (whole
  section TF-IDF 33 / 43; cards only 31 / 41).
* With the setting on (and `topic_major_only_document`), `choose_topic` makes ONE call that
  reads the chapter's cards and the full text of the two top-ranked sections. It is taken only
  when the quoted sentences are found verbatim in the book under the section named and the
  book's own terms / BM25 / retrieval agree; anything else reads the whole chapter as before.
  `judge.card_hits` / `judge.card_escalations` count both.
* **Adaptive excerpt.** BM25's margin ((top1 - top2) / top1) sets how much full text goes
  with the cards: one section at >= 0.5 (gold: 22/22 first sections right), two at >= 0.25
  (12/17), three below (9/15 right first, 11/15 in the top two).
* **Fuzzy quote check.** A quote counts when it is verbatim in a shown section, or when >= 85%
  of its words (six or more) sit in one stretch of it; never alone: the section it sits in must
  be the one named.
* **Counted signals** (`card_signals`): section shown, quote found, quote verbatim, quote in the
  named section, BM25 agrees, retrieval agrees, book terms agree (7; a signal with nothing to
  say agrees). Accepted at >= 6 with the quote in the named section and no book term pointing
  elsewhere; anything else reads the whole chapter. Outcomes are tallied (`accept`, `review`,
  `fallback`, `no_quote`, `terms_disagree`, ...) and written to the place job result as
  `card_tiers`.
* Measured offline on the gold paper and NOT adopted: fusing an exact-term/entity signal into
  BM25 (no gain, hurt at larger weights); richer cards (term coverage grows only in step with
  tokens); a reranker (BM25 already has the right section in the top three for 50-51 of 54).
  Dense fusion was not testable offline (no embeddings in the test container).
* Not yet measured on a paid run: accuracy and spend with card mode on. Compare with the
  card-mode-off numbers from the same paper.

## Any teacher, any subject (default OFF: `YAADHUM_TEACHER_ANY_SUBJECT_UPLOADS`)

Question papers were already open to every teacher key. With the setting on, answer sheets,
mark grids, single scripts and per-student marks are too: `teacher_can_enter_marks` accepts any
teacher key for any section of the key's OWN school, and `/admin/me` reports `enter_marks`. A
section of another school, or one that does not exist, is still a 404. Reading class marks,
cohort reports and the Insights/My-class subject filter (`teacher_can_read`,
`teacher_subject_codes`) are unchanged. Off, the subject-assignment rule applies as before.

## Mapping logic is kept per subject (`YAADHUM_MAPPING_V2_SUBJECTS`)

Every flag that changes how a paper is mapped is also gated by the paper's subject. The list
is `mapping_v2_subjects`, default `["X.SST","X.HIST","X.GEO","X.POL","X.ECO"]`. For a paper of
any other subject (Mathematics, Science, English, ...) every flag in
`app.mapping.subject_scope.SUBJECT_FLAGS` reads False, whatever the environment says, and the
pipeline runs the path it ran before the rework:

* placement and map take their settings through `for_subject(settings, paper.subject_code)`;
* the topic depth cap, the major-topic view, book-map-only subtopics and the text-route
  structure capture check the chapter's or paper's subject themselves;
* the vision reader's structure capture and the stored `declared` structure follow the subject;
* the topic judge reads `app/classify/legacy_prompts.py` (the two prompts exactly as they were,
  verbatim from git, pinned by a test) for a subject outside the list;
* section cards exist only for the four Social Science subjects.

To bring Science onto the new logic when its own mapping is ready, add `"X.SCI"` to the list;
Mathematics and Social Science are unaffected. `tests/test_subject_isolation.py` pins all of
this. Not gated, deliberately: the duplicate-upload hold (it compares papers of one subject
with each other and changes no mapping), the teacher screens, and anything not in SUBJECT_FLAGS.

## Science: section discipline and instruction-only rows (default OFF, Science only)

Two rules in `app/classify/science_scope.py`, each behind its own flag and each acting for a
paper of subject `X.SCI` and nothing else (`science_on` is False for any other subject, flag or
no flag; the flags are deliberately NOT in the shared `SUBJECT_FLAGS` list, so turning one on
changes Science only and no other subject's flags):

* `YAADHUM_SCIENCE_SECTION_SCOPE` -- the place step holds a section to one discipline when the
  paper says it is one: its printed title names Biology / Chemistry / Physics, or at least 4
  questions and 75% of them first landed in that discipline's chapters. Such a section's
  questions may only be placed in that discipline's chapters. A mixed section (a board paper's
  section A) is left alone. A teacher's paper scope is respected inside it. The place job
  result gains `science_sections` (letter -> discipline).
* `YAADHUM_SCIENCE_INSTRUCTION_ROWS` -- in the map step, a row that is only an instruction (an
  assertion-reason preamble with no assertion or reason, "Attempt either option (a) or (b)",
  "Read the following passage ..." with no passage) is not placed by its boilerplate: with rows
  after it (the options) it is skipped like a case-study stem; alone it is blocked with the
  reason, so a teacher sees it instead of a wrong chapter.

Found on a real Science paper's map output (72 gradable rows: chapter 86% right, topic 71%):
four instruction-only rows were placed by boilerplate, three questions crossed disciplines, and
topic mix-ups inside Metals and Light made up most of the rest. Not done here: capping Science
topics at two levels, tidying its book map, a Science gold key.
