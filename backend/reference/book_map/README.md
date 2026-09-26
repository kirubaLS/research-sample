# NCERT Class X Social Science: book map

All four 2026-27 reprint textbooks, divided into units that any exam question from these chapters can be mapped to. One Markdown file per chapter, plus one `<subject>_units.json` per book with the same content in machine-readable form.

| Folder | Book | Chapters | Units |
|---|---|---|---|
| `history/` | India and the Contemporary World – II | 5 | 95 |
| `politics/` | Democratic Politics – II | 5 | 42 |
| `economics/` | Understanding Economic Development | 5 | 55 |
| `geography/` | Contemporary India – II | 7 | 120 (nested, e.g. Energy Resources > Conventional Sources of Energy > Coal) |

Also here: `AUDIT.md` (audit and board-paper test results), `HANDOVER.md` (instructions for Claude Code), `gold_cycle_test_1.json` (verified answers for the example paper), `outside_textbook.json` (board questions the book cannot answer).

## How each book is divided

- **Every printed heading is a unit.** History keeps the book's printed numbers; the other books number units in reading order (`3`, `3.2`, `3.2.1` …).
- **Chapter openings** without a heading are an `Introduction` unit; *Summing Up* and *Conclusion* are their own units.
- **Boxes** are listed under the unit where their text sits.
- **Glossary terms** (History "New words", Politics margin definitions) are attached to their unit; words printed in bold are listed as key terms.
- **Sources, activities, "Let's work these out", cartoon bubbles, figure and table captions** are attached to their unit. Body, box, term and source text is primary evidence; activities and captions are supporting evidence, searched when locating a topic because board questions are sometimes drawn from them.
- **Exercises** are one separate unit per chapter, never attached to the last section.
- Nothing is merged across a printed heading, and every piece of text appears exactly once.

Every unit header looks like:
`unit: X.GEO.MINERALSENERGY.4.1.1 | kind: subsection | parent: … | pages: 67–69 | catalog: X.GEO.CF.COAL`

The `catalog:` field links the unit to the concept-family catalog (Social_family_complete); all 312 units carry one. Geography units also list the CBSE map items linked to them, marking places that appear only on maps.

## Validation

| Check | History | Politics | Economics | Geography |
|---|---|---|---|---|
| Text blocks on every page accounted for | complete | complete | complete | complete (4 garbled heading lines replaced by clean catalog titles) |
| Catalog headings found | 95 / 95 | all | all | 169 / 170 |
| Structural audit defects (see AUDIT.md) | 0 | 0 | 0 | 0 |
| Example paper: answer text in the expected unit | 20 / 20 | 18 / 18 | 11 / 11 | 20 / 20, plus map-only items via the map list |
| Textbook exercise questions placed (see AUDIT.md) | 40 | 50 | 163 | 114 |

## Review items

- **History:** Garibaldi box moved to 4.2 Italy Unified (printed after 4.3 only because of layout). "To the altar of this revolution…" box kept in Nationalism in India 3.1; confirm. Section number 2.4 is printed twice in The Making of a Global World; the second is `2.4b`.
- **Politics:** "Partisan" is printed beside the Meaning/Functions boundary; kept under Meaning, while the catalog puts it under Functions.
- **Economics:** Headings printed in capitals are kept as printed. Untitled italic passages are kept as untitled boxes.
- **Geography:** Headings were located using the catalog's printed heading list and checked against each page. Nesting follows the book's heading groups; please confirm. The "Krishna-Godavari dispute" box is printed inside the running text of Water Resources. Talcher, Kalpakkam and Namrup appear only on maps and are linked through the catalog map list.

## Handing this to Claude Code

Put this folder in the project as `reference/book_map/` and give Claude Code `HANDOVER.md`.
