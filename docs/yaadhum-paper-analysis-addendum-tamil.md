# Addendum — Tamil Paper, and One Important Correction

Measured on `Tamil_QP.pdf`, using the same extraction as the earlier five papers. It adds four new
structural cases, and it corrects one thing I told you earlier in your favour.

---

## 1. The Tamil paper

| Property | Value |
|---|---|
| Q.P. Code | 10 · Set 4 · Series G7DEF |
| PDF pages | 6 |
| **Logical pages** | **12** — the PDF is **2-up imposed** |
| Text layer | **None** — zero characters on all six pages |
| Maximum marks | 80 · 3 hours |
| Questions | **14** |
| Sections | **Five**: A (Q1–2), B (Q3–6), C (Q7–10), D (Q11), E (Q12–14) |
| Language | Questions Tamil-only; General Instructions bilingual Tamil + English |
| Orientation | **Rotated 90°** — content printed sideways on a portrait page |
| Marks notation | Arithmetic expressions: `3 × 1 = 3`, plus section headers like `SECTION – B (Grammar) 12 Marks` |

It repeats the two instructions we already rely on:

> "Attempt as per specific instructions for each question."
> "Please write down the **Serial no. of the question** in the answer book before attempting it."

---

## 2. The correction — and it is good news

I told you earlier that Hindi and Maths "have no text layer, so they are scanned images". **That was
half right.** They have no text layer, but they are **not scans**.

| Paper | Vector drawings on one page | Raster images | What it actually is |
|---|---|---|---|
| Hindi | 756 | 1 (204 × 31 px — a barcode) | Vector PDF, **text converted to outlines** |
| Maths | 2,808 | 10 (largest 97 × 51 px) | Vector PDF, text converted to outlines |
| Tamil | 1,359 | 1 (31 × 203 px — a barcode) | Vector PDF, text converted to outlines |

The glyphs are vector paths, which is why text extraction returns nothing — but it also means
**there is no scanning noise, no skew, no JPEG artefacts and no resolution ceiling.**

**Consequence:** render these at 400 DPI and the OCR input is pristine — far better than a
photograph of a printed page. Expected question-paper extraction accuracy on Hindi, Maths and Tamil
is therefore *much higher* than my earlier note implied. The vision path is still required; it is
simply working on ideal input rather than degraded input.

This does not change anything about the **answer scripts** — those are genuinely photographs and
remain the hard problem.

---

## 3. Four new structural cases

### 3.1 Imposition is variable — build for N-up, not 4-up

Maths is **4-up** (7 PDF pages → 27 logical). Tamil is **2-up** (6 → 12). Assume nothing.

**Detection algorithm** (works for both, and for 1-up):
1. Count occurrences of the footer pattern `Page\s+(\d+)\s+of\s+(\d+)` per PDF page. *k* matches ⇒
   *k*-up.
2. Cross-check: `ceil(M / k)` must equal the PDF page count, where *M* is the printed total.
3. Cluster the footer bounding boxes to recover the tile grid, then crop on the dashed cut lines.
4. Order tiles by the **printed logical page number**, never by geometric position — imposition
   order is not always left-to-right.

### 3.2 Rotation is baked into the content, not declared

Every page reports `rotation = 0` in its metadata, yet the content is printed at 90°. **PDF metadata
cannot be trusted for orientation.**

Detect it from the content instead: render the page, run a horizontal projection profile at 0°, 90°,
180° and 270°, and choose the angle whose profile has the highest variance — text lines produce sharp
periodic peaks only when horizontal. Cheap, deterministic, and it also handles a phone photo taken
sideways, so the same routine serves both pipelines.

### 3.3 The mark label is not always a bare integer

The earlier papers print marks as a lone right-aligned integer. Tamil prints arithmetic:

```
3 × 1 = 3          # three sub-parts, one mark each, three marks total
5 × 2 = 10
SECTION – B (Grammar) 12 Marks
```

So the mark-label grammar must accept three forms:

| Form | Example | What we take | Bonus |
|---|---|---|---|
| Bare integer | `3` | 3 | — |
| Product | `3 × 1 = 3` | 3 | **Also tells us there are 3 sub-parts of 1 mark each** — free structure, and `a × b = c` is a self-check |
| Section header | `(Grammar) 12 Marks` | section total 12 | Another verification equation |

The product form is a gift: it states the sub-part count and the per-sub-part marks explicitly, which
is exactly the Q-matrix structure we would otherwise have to infer.

### 3.4 The Q.P. code is a decoy that looks exactly like a mark

This paper's Q.P. code is **10** — a perfectly plausible mark value — and it is printed as a bare
numeral in the page margin **on every page**.

**Rule:** any numeral appearing at the same normalised coordinates on three or more pages is page
furniture — Q.P. code, page number, set number — not a mark. Filter it before mark extraction.
Without this rule, this paper alone would inject a spurious "10" on all twelve pages.

---

## 4. Updated picture across all six subjects

| Subject | Text layer | Imposition | Rotation | Languages | Sections | Taxonomy shape |
|---|---|---|---|---|---|---|
| English | Yes, clean | 1-up | 0° | English | 3 | **Skills** + rubric criteria |
| Science | Yes | 1-up | 0° | Bilingual | 3 = disciplines | Discipline → chapter → sub-topic |
| Social Science | Partial | 1-up | 0° | Bilingual | 4 = sub-subjects | Sub-subject → chapter |
| Maths | None (vector) | **4-up** | 0° | Bilingual | 5 | Chapter → sub-topic |
| Hindi | None (vector) | 1-up | 0° | Hindi | — | **Skills** + rubric criteria |
| **Tamil** | **None (vector)** | **2-up** | **90°** | Tamil (bilingual instructions) | **5** | **Skills** + rubric criteria |

Every axis now has at least two values. That is the argument for making all of this **configuration
discovered per paper**, never hardcoded per subject: the ingest pipeline detects imposition,
rotation, language and section count from the document itself and records them on the
`assessment` row.

---

## 5. Tamil-specific notes

- **OCR**: Tamil is well supported by Tesseract (`tam`) and by PaddleOCR's multilingual models, and
  the vector-rendered input at 400 DPI is close to a best case. For the pilot, the vision model
  reads it directly; Tamil is not a reason to add a separate OCR engine.
- **Numerals**: Tamil digits (௧௨௩) may appear in older papers. Add a normalisation map alongside the
  Devanagari one — a fifteen-line lookup, not a model.
- **Taxonomy**: like English and Hindi, Tamil is a language paper — skills, not chapters. Sections
  give the first level free (Grammar is literally the section name). Long answers are rubric-scored,
  so each rubric criterion becomes a skill.
- **Advantage worth noting**: for the Tamil Nadu market this is the subject most schools care about
  and the one no competitor will have bothered to support properly. It is also, mechanically, no
  harder than Hindi.

---

## 6. What to change in the build

1. **Generalise de-imposition** to N-up with footer-pattern detection. *(Was 4-up-specific.)*
2. **Add content-based orientation detection** before any extraction. Reuse it for answer-script
   photos.
3. **Extend the mark-label grammar** to accept `a × b = c` and section-header totals, and use the
   product form to seed sub-part structure.
4. **Add the page-furniture filter** — repeated numerals at fixed coordinates are not marks.
5. **Render vector PDFs at 400 DPI**, not 300. There is no scanning noise to work around and the
   extra resolution is free.
6. **Store `imposition`, `rotation`, `languages`, `section_count` on the assessment row** as
   discovered properties, so nothing is hardcoded per subject.
