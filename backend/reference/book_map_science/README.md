# NCERT Class X Science: book map

*Science*, Class X, NCERT reprint 2026-27: 13 chapters divided into 178 units that any exam question can be mapped to. One Markdown file per chapter, plus `science_units.json` with the same content in machine-readable form. Same format and rules as the Social Science book map.

## How the book is divided

- **Every printed numbered heading is a unit**, keeping the book's number (`5.2`, `5.2.1` …). Sections are `##`, sub-sections `###`. Chapter openings are an `Introduction` unit; *What you have learnt* is a summary unit.
- **Activities** (Activity 1.1 …) are attached to the unit where they are printed, as supporting evidence. Board questions are often drawn from them.
- **"Do You Know?" and "More to Know!" boxes** are attached to their unit.
- **In-text question boxes** (the "Questions" printed after sections) are kept separate, labelled `intext_question`, and are never used as evidence, like exercises.
- **Figure and table captions** are attached as supporting evidence. Diagrams themselves are not in the map; only their captions are.
- **Exercises** are one separate unit per chapter.
- Unit ids use the chapter codes already in the AVAI database (`X.SCI.CHEMRXN`, `X.SCI.LIFEPROC` …). The `catalog:` field reuses the existing database family code wherever the family label matches the printed heading (88 units); the other 90 get new codes from their heading.

## Validation

| Check | Result |
|---|---|
| Text on every page accounted for | complete (about 439,000 characters; only two stray diagram letters left out) |
| Printed numbered headings found | all; 4.2.3 does not exist in this reprint |
| Structural audit | no empty, oversized, duplicated or out-of-order units; no text split across units |
| CBSE 2026 Science board papers (15 sets, 31/1/1 to 31/5/3) | 700 question items, 380 unique: every one has an exact unit in the map |

## Review items

- **Headings printed with shadow lettering:** they were rebuilt letter by letter and checked against the page.
- **"Reproductive Health":** printed as sub-part (d) of 7.3.3; kept as its own unit (`X.SCI.REPRO.7.3.3.d`) because it has its own heading and board questions target it.
- **"Family of Salts" (2.4.1):** its content is entirely an activity, so it has no body text of its own.
- **The old Science family list in the database:** of 261 families, 88 match printed headings and were reused. The other 173 are AI-written concept labels, several of them near-duplicates. They are not needed for mapping and should be retired the same way as the old Social Science codes.
