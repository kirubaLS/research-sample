# Prompt mapper

An experiment in the admin console (**Ops console → Prompt mapper**, `/admin/prompt-lab`): map questions to
chapter and topic with **one cheap model call per batch of 20** (Haiku, `YAADHUM_MODEL_HIGH_VOLUME`), choosing
from the books' complete topic list written into the prompt. It sits beside the real mapping pipeline and
changes nothing in it; nothing it does is saved.

## Why the topic list is generated

A hand-typed list drifts from the books: topics go missing (each crop, the soil types, the consumer-court
sections, language policy) and topics the books lack get added. `app/mapping/prompt_taxonomy.py` builds the list
from the same audited book-map files the rest of the system reads, so all 22 chapters and every section and
sub-section (282 topics) are choices, and a new edition is a data change. Each topic carries hints (names, dates,
terms from its section card and the titles of boxes under it) so the model can tell neighbours apart.

IDs are `H5` for a chapter and `H5.3.2` for its section 3.2; every answer is checked against the list and
translated back to the real chapter code and printed section number, plus the **two-level topic** the reports use.

## Using it

- Type questions (separate them with a line containing `---`), optionally with a section hint
  (A History, B Geography, C Political Science, D Economics), or load a stored paper.
- A stored paper is mapped in full and **compared with its saved mapping**: chapter agreement, topic agreement,
  and a "differs from saved" filter. That comparison is the experiment: does a closed topic list cover topics
  better than retrieval does?
- The summary shows how many mapped, how many are in the syllabus, how many need review, and the cost.

## What it does and does not do

- Read only: own session, never committed. Behind the operator key. 40 runs an hour, 80 questions a run.
- A wrong or invented ID is reported and the row flagged, never trusted. Low confidence and anything not
  clearly in the syllabus is flagged for review.
- Prompt caching: the topic list is a cached block (about 7,100 tokens), so batches after the first read it at
  a tenth of the price.
- Social Science only. A case-based passage must be pasted with its sub-question.
- Not built: OCR upload (type or load stored questions), and the parent-row union for case-based questions.
