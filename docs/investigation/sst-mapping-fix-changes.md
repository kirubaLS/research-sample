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

### 4.2 Six reasons, stored on the row
`app/classify/review_rule.py` holds the rule. A row is flagged only for:

| Code | Condition |
|---|---|
| `judge_failed` | the chapter judge could not be asked |
| `cross_scope` | the placement left the declared scope |
| `family` | the family is unsettled (several claim the section) or blocked; this includes a family refused because the question moved to a chapter whose families cannot place it |
| `low_confidence` | the chapter judge's **own** confidence is below 0.7, and it chose among **more than one** chapter |
| `topic_differs` | the topic judge's section differs from in-chapter retrieval's (a parent and its own sub-section do not differ), and answerability did not verify it |
| `topic_unverified` | answerability found that no section of the chapter can answer the question, or the topic judge gave no answer and retrieval decided |

- **Stored reason.** `question_placement.review_reason` holds every applicable code, comma-joined in that order (whole codes only, at most 64 characters). It is set on every flagged row and null on every unflagged one.
- **Place.** The pipeline now records the chapter judge's own confidence and how many chapters it chose among (`PlacedQuestion.judge_confidence`, `chapters_shown`). A skipped or failed judge has none, so `low_confidence` cannot fire for it. The blueprint's overrule and the thin-margin check no longer flag on their own.
  - The job's `needs_review` is the number of rows flagged.
  - A new `flagged_by_reason` breaks them down.
  - A question a person settled is never flagged (Phase 3).
- **Map.** The map step uses the same rule with the inputs it has: the family, and the topic pick unless the classify job queued behind the map decides the topic (a provisional topic is no doubt). There is no chapter judge at map time.

### 4.3 Reasoning fits its column (unflagged)
A validator on `QuestionPlacement.reasoning` (`app/models/assessment.py`) cuts it to 1000 characters before insert. It covers map, place and review alike, so an over-long reasoning can no longer fail a Postgres write phase.

### The gold paper under the new rule (959e36d4)
**Not run here.** The backup was deleted after Part B, as instructed, and no copy of its placements was kept. Run this against the staging copy:

```bash
cd backend
python -m scripts.replay_review_flags --assessment 959e36d4-5028-42e6-922e-c69228c5c325
```

**What the script does.** It is read-only. For each question's latest placement row it reports each of the six conditions as yes, no or unknown, a verdict (flagged / not flagged / unknown), and today's stored flag. It ends with `TODAY flagged N; NEW RULE flagged a, not flagged b, unknown c`.

**What a stored row can and cannot tell:**

| Condition | Stored? |
|---|---|
| `judge_failed` | yes: the failed-judge reasoning text |
| `cross_scope` | yes: the column, or the cross-scope reasoning text |
| `family` | yes: the unsettled/blocked family message in the reasoning |
| `topic_unverified` | yes: the "no section of the chapter answers" note is written exactly when answerability verified nothing, and the topic judge's fallback text when it gave no answer |
| `low_confidence` | **partly**. The row stores the reconciled confidence: the judge's own, unless the blueprint moved the question. It does not store how many chapters the judge saw (`candidates` holds only the chosen one). So 0.7 or above is a known no; below 0.7, or a blueprint row, is **unknown**. |
| `topic_differs` | **partly**. Retrieval's section is written only when it disagreed and was not settled ("Retrieval within the chapter pointed at section N"). Answerability's verdict is written only when it failed or switched sections. A disagreement note without a verdict is **unknown**. No note is read as **no**: that is wrong only if the answerability call itself failed for a question whose confirming re-read agreed, which no stored text records. |

From here on each new row stores the rule's outcome in `review_reason`, so a run made with `review_flag_rule` on needs no replay. The raw inputs (the judge's own confidence, the chapters shown, answerability's verdict) are still not stored; storing them would need a new column.

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

## Follow-ups (not done)

- **Twelve order-dependent baseline test failures.** They pass alone and fail in the full run, through shared test-client state (for example, a stubbed judge that is not the one the run uses). Until this is fixed, a new end-to-end test can't be fully trusted in the full suite. Phase 3 had to drop the second half of one test for this reason.

- **Show GEO, POL and ECO topic labels in the teacher UI without the number prefix.** Their numbers are reading order, not printed in the books. Keep the numbers in stored codes, and keep them for History, where they are printed. This is not a one-line change: the label reaches the teacher through several API fields and the xlsx and PDF exports, so it needs one display helper used at each of those places.
