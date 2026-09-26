# Audit of the book division

Goal: confirm the division can hold any question from these chapters, not only the Cycle Test I paper.

## 1. Structural audit (all 312 units)

| Check | Result |
|---|---|
| Units with no text of their own and no sub-units | 1: Geography "District Roads", a single sentence in the book |
| Oversized units (over 1,800 words) | 0; the largest is about 1,000 words |
| Sections starting mid-sentence | 0 |
| Sentences split across two units | 0 |
| The same paragraph in two units | 0 |
| Leftover heading junk in the text | 0 |
| Units out of page order | 0 |

Defects found and fixed during this audit:
- **Economics:** on odd-numbered pages the text columns sit further left, so columns were read out of order and five sections began with the end of the previous section's sentence.
- **Geography:** boxes printed inside the running text (Atal Bhujal Yojana, Sardar Sarovar Dam, Rat-Hole Mining, Digital India) were absorbing the section text printed after them.
- **Geography:** where a heading is also the subject of its sentence ("Rubber is an important…"), the heading word had been cut from the sentence.
- **Geography:** topics are now nested under the book's group headings (Conventional / Non-Conventional Sources of Energy, Food / Non-Food Crops, Ferrous / Non-Ferrous Minerals, Roadways, Mineral-based Industries and others).

## 2. Stress test with every end-of-chapter exercise question

All 367 exercise questions from the 22 chapters were placed against the division with a simple keyword scorer:

| Result | Questions | Share |
|---|---|---|
| One unit clearly best | 175 | 47% |
| Top two are parent and child, or in the same group | 33 | 9% |
| Top two unrelated units score close | 122 | 33% |
| Too generic for keywords ("Find the odd one out") | 37 | 10% |

The close cases were inspected by hand (60 in detail). None was caused by the division: in every case the answer sits inside one unit, or inside several because the question has several parts. Roughly 40% were multi-part questions, a third were placed correctly with a close runner-up, 15% had the right unit ranked second by the crude scorer, and 10% were parsing artefacts where a question was fused with the next exercise item.

## 3. What this means for placement

The division holds. The weak points are in placement:
1. Split multi-part questions and place each part.
2. Introduction and Summing Up units are fallbacks only; they repeat section content.
3. Prefer the most specific unit containing the evidence sentence.
4. Keyword matching was clearly right for only about half the questions, so it can only shortlist; the model must choose and quote evidence.
5. Geography map-only places are matched through the catalog map list.

## 4. Test against the CBSE 2026 board papers

All 15 sets (32/1/1 to 32/5/3), 727 question items, 364 unique questions, checked against the book map without changes.

| Outcome | Unique questions |
|---|---|
| Exact topic in the map, answer in its text | 346 |
| Exact topic in the map, answer only in an activity or caption | 2 |
| Topic in the map, answer beyond the book's text | 8 |
| General knowledge, not in the book | 1 |
| Not in any textbook (flood-safety case study) | 4 |
| Could not verify (unreadable scanned pictures, or an OCR fragment that isn't a question) | 3 |

Changes made after this test, with approval:
1. Activities and captions changed from "never evidence" to supporting evidence, so the 2 activity or caption questions can be located.
2. An "outside the textbook" labelling added (`beyond_text`, `not_in_books`), with the 13 affected questions listed in `outside_textbook.json`.

The division itself was not changed.
