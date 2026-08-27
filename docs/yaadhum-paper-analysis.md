# Analysis of Five Real CBSE 2026 Papers — and the Solving Logic

I ran all five papers through extraction and measured what is actually in them. Everything below is
a measured fact from your files, not an assumption. Several findings change the design.

---

## 1. What the five papers actually are

| Paper | Code | PDF pages | Text layer | Questions | Structure |
|---|---|---|---|---|---|
| English (Lang. & Lit.) | 2/7/3 | 19 | **Yes, clean** | 11 | 3 sections: Reading (20) / Grammar & Creative Writing / Literature |
| Science (for V.I.) | 31(B) | 27 | Yes, English only | 39 | 3 sections: Biology (30) / Chemistry (25) / Physics (25) |
| Social Science | 32/7/1 | 27 | Partial, 22 images/page | 38 | 4 sections × 20 marks: History / Geography / Pol. Sci. / Economics |
| Hindi Course B | 4/8/3 | 16 | **None — zero text on all 16 pages** | — | Devanagari, image-only |
| Mathematics (Standard) | 30/7/1 | 7 | **None — zero text, 85 images/page** | — | **4-up imposed: 7 PDF pages = 27 logical pages** |

### Finding 1 — two of five papers have no extractable text at all

Hindi and Maths are pure image PDFs. Any design that parses PDF text as the primary path fails on
40% of your subjects on day one. **This validates the vision-first architecture and downgrades text
parsing to an optimisation**, used only when a text layer happens to exist.

### Finding 2 — the Maths paper is 4-up imposed

Seven PDF pages carry twenty-seven logical A4 pages, tiled two-by-two, each tile with its own
footer (`30/7/1  Page 13 of 27`), its own QR code, and dashed cut lines between them. A page-by-page
extractor would produce four interleaved question streams and quadruple every question.

**Fix:** detect the imposition from the repeated footer pattern `Page N of M` appearing more than
once per PDF page, split on the cut lines, and re-order by the printed logical page number before
anything else runs.

### Finding 3 — bilingual interleaving doubles everything

Science, Social Science, Maths and Hindi print every question twice — English and Hindi — usually on
facing logical pages. Measured naive sums of every right-margin mark label:

| Paper | Naive mark sum | Stated maximum | Excess |
|---|---|---|---|
| English | 90 | 80 | +12% (internal choice only) |
| Science | 172 | 80 | +115% (choice + bilingual) |
| Social Science | 349 | 80 | +336% (choice + bilingual + instruction numerals) |

Without de-duplication and choice-grouping, the reconciliation gate would reject every real paper.

### Finding 4 — marks are right-aligned at a fixed position

Across all three text-layer papers, the right edge of every bare mark label sits at
**x ≈ 0.88 × page width** — the 10th, 50th and 90th percentiles are all 0.88. This is a typesetting
rule, not a tendency.

**Consequence:** a mark-label candidate must be a bare integer, alone on its line, right-aligned in
that band. This removes almost all false positives before a model reads anything, and it is the same
geometric prior we apply to the answer script.

### Finding 5 — the papers hand us four free verification equations

Every paper prints, in its General Instructions:

- **Question count** — "This question paper contains 38 questions."
- **Section marks** — "Each section carries 20 marks." / "Section A : Biology (30 marks)"
- **Section arithmetic** — the Maths paper prints the multiplication outright:
  "This section has 5 Very Short Answer (VSA) type questions carrying 2 marks each.  **5×2=10**"
- **Paper total** — "Maximum Marks : 80"

These are exact, machine-checkable constraints. They are the question-paper equivalent of the cover
total on an answer script, and they make extraction verifiable rather than merely probable.

### Finding 6 — CBSE instructs the student to write the anchor for us

Every one of the five papers carries:

> "Please write down the **Serial Number of the question** in the answer-book at the given place
> before attempting it."

and, for Science and Social Science:

> "**Divide your answer sheet into sections** as per the question paper... It is compulsory to answer
> each question in its respective section. Do not mix answers of one section into the other section."

The anchor our localisation layer depends on is not something we hope to find — it is a field the
board requires the student to fill in, in their own black or blue ink, in a designated place. And the
section headers give us page-range priors for free.

### Finding 7 — internal choice is everywhere, and it is not just a counting problem

Measured `OR` blocks: 6 in English, 9 in Science, 6 in Social Science. Two forms appear:

- whole-question choice — "16. (a) ... **OR** (b) ..."
- sub-part choice — "15. (iii)(a) ... **OR** (iii)(b) ..."

Both alternatives carry identical marks and contribute to the paper total **once**.

---

## 2. The consequence that changes the data model

### The atomic unit is the address, not the question number

Marks are written per **sub-part**, not per question. English Q1 carries 10 marks spread across
(i)–(x). Science Q15 carries 4 marks across (i), (ii) and (iii)(a)/(iii)(b).

So the Q-matrix key is:

```
SECTION / QUESTION_NO / SUB_PART / CHOICE_ALTERNATIVE
     A  /     15      /  (iii)   /       b
     B  /      4      /   (a)    /       -
```

Everything downstream — the solver, the mapping, the report — keys on this address. Keying on the
bare question number does not survive contact with any of these five papers.

### Choice creates missing-not-at-random data, and this is the important one

A student who attempts 16(b) has written nothing for 16(a). The naive system records **16(a) = 0**.

That is wrong, and it is wrong in the direction that harms a child: it would systematically mark
every student weak in whichever topic they *chose to avoid*, which is the opposite of the truth. The
student produced **no evidence** about those skills, and no evidence is not weakness.

`16(a)` must be recorded as **NOT OFFERED**, excluded from the denominator, and reported as a
coverage gap rather than a loss. This single rule is the difference between a diagnostic system and
a misleading one.

---

![Figure A](FIGA)

*Figure A — the five normalisations that turn a real CBSE PDF into a frozen Q-matrix.*

## 3. The solving pipeline, end to end

**Stage A — Normalise the paper (once per paper)**

1. **De-impose** — detect repeated `Page N of M` footers per PDF page; split tiles; order by printed
   logical page. *(Maths needs this; the others pass through.)*
2. **De-duplicate language** — detect script per block (Latin vs Devanagari); keep the English
   stream as canonical, attach the Hindi text as a translation of the same address. Never create two
   Q-matrix rows.
3. **Segment sections** — from the section headers and the General Instructions block, which state
   the section names and their marks.
4. **Extract addresses** — question number, sub-part, choice alternative, with marks taken from the
   right-aligned 0.88 band.
5. **Group choices** — an `OR` line between two alternatives at the same address level creates a
   `choice_group_id`; the group contributes its marks once.
6. **Verify** — question count, per-section marks, section arithmetic, paper total. Any failure
   blocks the paper and shows the teacher exactly which equation broke.

**Stage B — Classify (once per paper, teacher-confirmed)**

Each address gets: **question type**, **skill tags**, **cognitive tier**.

Question type is *extracted, not guessed* — the instructions state the marks and word limits for
each type. All eight of these appear in your papers:

MCQ · Assertion–Reason · Match-the-columns · VSA (2 marks, 40 words) · SA (3 marks, 60 words) ·
LA (5 marks, 120 words) · Case-based CBQ (4 marks, 3 sub-parts) · Map work (2 + 3 marks)

**Stage C — Map the answer sheet (per student)**

1. Colour separation: teacher's red mark layer, student's black/blue layer.
2. Anchors from the **student** layer — the serial numbers CBSE required them to write.
3. Normalise the written address (strip punctuation, map Devanagari numerals, fold script variants).
4. **Closed vocabulary** — the parsed address must exist in the frozen Q-matrix. `16(c)` does not
   exist on this paper, so it is rejected rather than invented.
5. Section prior — a page inside the Geography block resolves an ambiguous "4" to `B/4`, not `A/4`.
6. Marks from the **teacher** layer; Hungarian association; convention refit; constraint solve
   against section and paper totals.
7. Choice resolution — for each choice group, the attempted alternative takes the mark; the other is
   recorded **NOT OFFERED**.

---

![Figure B](FIGB)

*Figure B — mapping an answer sheet onto the Q-matrix, including the choice problem.*

## 4. What "chapter" means is different in every subject

This is the finding that most affects the taxonomy work, and it is why the subject pack has to be
data rather than code.

| Subject | First level | Second level | Notes |
|---|---|---|---|
| **Mathematics** | Chapter (Polynomials, Circles, Trigonometry, Statistics…) | Sub-topic | The straightforward case; the original design applies unchanged. |
| **Science** | **The section *is* the discipline** — Biology (30), Chemistry (25), Physics (25) | Chapter → sub-topic | Section gives the first level for free, with no classification needed. |
| **Social Science** | **Four sub-subjects**, 20 marks each — History, Geography, Political Science, Economics | Chapter → sub-topic | Plus map work as a distinct question type, not a topic. |
| **English / Hindi** | **Skills, not chapters** — Reading, Grammar & Creative Writing, Literature | Sub-skill | Long answers are rubric-scored: **each rubric criterion becomes a skill, each band a partial credit.** The Q-matrix formalism absorbs this unchanged. |

For English and Hindi, "which chapter is the student weak in" is not a meaningful question. The
meaningful one is "is the gap in inference from a passage, in grammar accuracy, or in structuring a
formal letter" — and that is exactly what a skill-based Q-matrix gives you.

---

## 5. Difficulty ranking — where to start

| Rank | Subject | Why |
|---|---|---|
| 1 — easiest | **English** | Clean text layer, single language, only 11 questions, sections carry explicit marks. Best first target for the pipeline. |
| 2 | **Science** | Text layer, section = discipline, well-formed question types, clear internal choice. |
| 3 | **Social Science** | Partial text, image-heavy, four sub-subjects, map questions need special handling. |
| 4 | **Maths** | No text layer, 4-up imposition, and mathematical notation in the stems. |
| 5 — hardest | **Hindi** | No text layer, Devanagari handwriting and print, and rubric-scored long answers. |

**Recommendation: build and prove the pipeline on English and Science first.** They exercise every
mechanism — sections, sub-parts, internal choice, multiple question types, the verification
equations — without also fighting imposition and Devanagari OCR. Maths and Hindi then need only the
two extra front-end steps (de-imposition, Devanagari normalisation), not a new pipeline.

---

## 6. What this analysis changes in the plan

1. **Vision-first is confirmed, not a preference.** Two of five papers have no text at all.
2. **Add a de-imposition step** to Stage A. It was not in the earlier plan and Maths needs it.
3. **Add language de-duplication** to Stage A. Without it, every gate fails on four of five papers.
4. **Change the Q-matrix key** from question number to the full address. This is a schema change and
   it should land before any extraction code is written.
5. **Add `NOT OFFERED` as a first-class mark state**, distinct from zero and from absent. Three
   states, not two.
6. **English and Hindi need a skills taxonomy plus rubric criteria**, not a chapter list. That is
   taxonomy authoring work that can start immediately, in a spreadsheet, in parallel with the build.
7. **Extract the General Instructions block as structured data.** It contains the question count,
   the section marks, the question types and their word limits — the verification equations are
   printed on page 1 of every paper, and we should be reading them.
