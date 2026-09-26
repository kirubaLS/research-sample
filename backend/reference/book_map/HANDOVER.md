# Handover: loading the book map into AVAI

For Claude Code. Read CLAUDE.md first. This file describes the data in `reference/book_map/` and how it maps onto the book tables. Plain PostgreSQL, migrations for every schema change, no Supabase-specific features.

## What is here

| File | Content |
|---|---|
| `<subject>/<n>_<chapter>.md` | Human-readable chapter map, one per chapter (22 total) |
| `<subject>/<subject>_units.json` | Same content, machine-readable; this is what gets loaded |
| `gold_cycle_test_1.json` | Verified correct units for all 55 Cycle Test I questions |
| `AUDIT.md` | Audit results and the placement rules they imply |
| `outside_textbook.json` | Board-paper questions that the textbook text cannot answer, with their label and nearest topic |
| `README.md` | Division rules, validation, open review items |

## JSON shape (`<subject>_units.json`)

```
chapter:  code, title, pages[first,last], units[], exercise{id, pages[], text[]}
unit:     id, kind, number, title, parent, pages[], catalog,
          body[]        {page, text}              -- evidence
          terms[]       {term, definition}        -- evidence (glossary)
          key_terms[]   string                    -- words printed in bold
          boxes[]       {label, title, page, text[], catalog?}   -- evidence
          sources[]     {label, title, page, text[]}             -- evidence ("Unlabelled" = margin note)
          activities[]  {label, page, text[]}     -- supporting evidence
          captions[]    {page, text}              -- supporting evidence
```

`kind` is `intro`, `section`, `subsection`, `summary` or `box`. Skip `intro` units with no body and no boxes. `parent` is the id of the enclosing unit. `catalog` is the concept-family code; every unit has one.

## Loading into the tables

1. **Edition:** one `curriculum_edition` row per subject for the 2026-27 reprint, with the source PDF hash. Leave `frozen_at` empty until the review items are settled.
2. **Nodes:** one `curriculum_node` per chapter, unit and box, following `parent`. Store `number` as the display number and the unit `id` as a stable external key.
3. **Chunks:** one `book_chunk` per body paragraph, glossary term, box and source, with its content type. Activities and captions may be stored with their own content types but must be excluded from placement search. Exercises get a separate node of kind `exercise`, also excluded.
4. **Topics:** one `topic` per distinct `catalog` code, and a `topic_node_link` from each topic to its unit node for this edition.
5. **Map items (Geography):** store the catalog's `map_places` against the topics so map-only places can be matched.

Do not re-parse the PDFs for this step; the parser in BOOK_MAPPING_SPEC.md is for future editions.

## Placement rules learned from the audit

1. Split multi-part questions into their parts and place each part; a question may have several primary units.
2. Introduction and Summing Up units are fallbacks only.
3. When the best candidates are a parent and its child, choose the child that contains the quoted evidence.
4. Keyword or vector search only shortlists; the model chooses a unit and quotes the evidence sentence, which is then checked against the chunk text. Prefer a primary-evidence quote; use an activity or caption quote only when the question is drawn from it.
6. Treat US and British spellings as the same word ("globalization"/"globalisation", "organized"/"organised"); board papers use both.
7. If no unit contains the answer, label the question `beyond_text` or `not_in_books` instead of forcing a topic.
5. Geography map-only places are matched through the map list.

## Questions outside the textbook

Placement must be able to say a question is not answerable from the book instead of forcing a topic. Use two labels:

- `beyond_text`: the question comes from a textbook topic but its answer goes beyond the book (for example "Suggest ways to promote women's entrepreneurship"). Map it to the nearest topic and store the label with the placement.
- `not_in_books`: no textbook topic covers it (for example the "Floods: basic safety precautions" case study). Store no topic, only the label.

`outside_textbook.json` lists every such question found in the 2026 board papers, with paper references and the nearest topic. Load it as part of the test data; placement should reproduce these labels.

## Checks before calling this done

- Node, chunk and topic counts per subject match the JSON (History 95 units, Politics 42, Economics 55, Geography 120).
- No exercise chunk is reachable by placement search; activity and caption chunks are searchable and marked as supporting evidence.
- Gold set in `tests/gold/`: every primary unit exists and every evidence sentence is found inside that unit's evidence chunks (100% before placement work starts). Placement accuracy is then scored against it at unit and chapter level.
- Add the 367 textbook exercise questions as a second, unlabelled test set to watch placement behaviour across all chapters.

## Open review items

Listed in README.md. None block loading; keep `frozen_at` empty until someone confirms them.
